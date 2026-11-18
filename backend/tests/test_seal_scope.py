"""钉扎粒度全局互斥（按活动分批钉）的行为核对。

运行：cd backend && python -m unittest discover -s tests -v
全部用例共用一个临时 DATA_DIR，每个用例开始前清空事实/批次/事件。
"""
from __future__ import annotations

import os
import tempfile
import threading
import unittest


def _bootstrap() -> None:
    tmp = tempfile.mkdtemp(prefix="vouchpin-test-")
    os.environ["DATA_DIR"] = tmp
    os.environ.setdefault("VOUCHPIN_TEST_DATA", tmp)


_bootstrap()

from fastapi import HTTPException  # noqa: E402
from app.seed import seed_if_empty  # noqa: E402
from app.db import connect  # noqa: E402
from app.repositories import settings as settings_repo  # noqa: E402
from app.services import event_service, redeem_service  # noqa: E402


def _reset(day: str) -> None:
    seed_if_empty()
    conn = connect()
    try:
        # 清空核销事实与批次，保留活动目录
        conn.execute("DELETE FROM redeem_facts")
        conn.execute("DELETE FROM redeem_batches")
        conn.execute("DELETE FROM coupon_events")
        settings_repo.set_(conn, "business_day", day)
        conn.commit()
    finally:
        conn.close()


def _redeem(coupon: str, campaign: str, amount: float, day: str | None = None) -> dict:
    body = {
        "event_type": "redeem",
        "coupon_code": coupon,
        "campaign_code": campaign,
        "amount": amount,
    }
    if day:
        body["business_day"] = day
    return event_service.add_event(body)


class SealScopeTest(unittest.TestCase):
    day = "2031-01-05"

    def setUp(self) -> None:
        _reset(self.day)

    def test_campaign_seal_claims_only_that_campaign(self) -> None:
        _redeem("T-1", "NEW10", 10)
        _redeem("T-2", "NEW10", 10)
        _redeem("T-3", "VIP20", 20)

        r = redeem_service.seal({"campaign_code": "NEW10"})
        self.assertEqual(r["scope"], "campaign")
        self.assertEqual(r["campaign_code"], "NEW10")
        self.assertEqual(r["fact_count"], 2)
        self.assertAlmostEqual(r["total_amount"], 20.0)

        p = redeem_service.preview()
        rows = {c["campaign_code"]: c for c in p["campaigns"]}
        self.assertTrue(rows["NEW10"]["sealed"])
        self.assertEqual(rows["NEW10"]["sealed_count"], 2)
        self.assertFalse(rows["VIP20"]["sealed"])
        self.assertEqual(rows["VIP20"]["open_count"], 1)
        # 未钉活动的 open 事实仍在，仍可钉扎
        self.assertTrue(rows["VIP20"]["can_seal"])

    def test_write_gate_blocks_only_sealed_campaign(self) -> None:
        _redeem("W-1", "NEW10", 10)
        redeem_service.seal({"campaign_code": "NEW10"})

        with self.assertRaises(HTTPException) as ctx:
            _redeem("W-2", "NEW10", 10)
        self.assertEqual(ctx.exception.status_code, 409)

        # 未钉活动仍可核销并进入 open
        _redeem("W-3", "VIP20", 20)
        rows = {c["campaign_code"]: c for c in redeem_service.preview()["campaigns"]}
        self.assertEqual(rows["VIP20"]["open_count"], 1)

        # issue/void 不受核销写闸影响
        event_service.add_event(
            {
                "event_type": "issue",
                "coupon_code": "W-4",
                "campaign_code": "NEW10",
                "amount": 0,
            }
        )

    def test_duplicate_campaign_seal_rejected(self) -> None:
        _redeem("D-1", "NEW10", 10)
        redeem_service.seal({"campaign_code": "NEW10"})
        _redeem("D-2", "VIP20", 20)

        with self.assertRaises(HTTPException) as ctx:
            redeem_service.seal({"campaign_code": "NEW10"})
        self.assertEqual(ctx.exception.status_code, 409)

        # 被拒后事实与批次都未被二次累加
        p = redeem_service.preview()
        self.assertEqual(len([b for b in redeem_service.list_batches() if b["business_day"] == self.day]), 1)
        new10 = [c for c in p["campaigns"] if c["campaign_code"] == "NEW10"][0]
        self.assertEqual(new10["sealed_count"], 1)
        self.assertAlmostEqual(p["ledger"]["sealed_fact_total_amount"], 10.0)

    def test_whole_day_reseal_after_one_campaign_is_blocked(self) -> None:
        _redeem("H-1", "NEW10", 10)
        _redeem("H-2", "VIP20", 20)
        redeem_service.seal({"campaign_code": "NEW10"})

        for body in (
            {"scope": "day"},
            {"scope": "day", "campaign_code": "VIP20"},
            {},  # 不指定活动：按活动粒度不可推断，拒绝
        ):
            with self.assertRaises(HTTPException) as ctx:
                redeem_service.seal(body)
            self.assertEqual(ctx.exception.status_code, 409 if body.get("scope") else 400)

        p = redeem_service.preview()
        self.assertFalse(p["day_sealed"])
        self.assertTrue(p["ledger"]["balanced"])
        # VIP20 仍 open，未被整日钉扎吞掉
        vip = [c for c in p["campaigns"] if c["campaign_code"] == "VIP20"][0]
        self.assertEqual(vip["open_count"], 1)
        self.assertFalse(vip["sealed"])

    def test_legacy_day_batch_blocks_campaign_supplement(self) -> None:
        """历史整日批：该日视为已整日封存，不得按活动补钉；写闸封整日；等式仍平。"""
        _redeem("L-1", "NEW10", 10)
        _redeem("L-2", "VIP20", 20)
        conn = connect()
        try:
            cur = conn.execute(
                """INSERT INTO redeem_batches(business_day, scope, campaign_code, status,
                                              fact_count, total_amount, sealed_at)
                   VALUES(?, 'day', NULL, 'sealed', 2, 30, '2020-01-01T00:00:00')""",
                (self.day,),
            )
            conn.execute(
                "UPDATE redeem_facts SET status='sealed', batch_id=? WHERE business_day=?",
                (int(cur.lastrowid), self.day),
            )
            conn.commit()
        finally:
            conn.close()

        p = redeem_service.preview()
        self.assertTrue(p["day_sealed"])
        self.assertTrue(all(not c["can_seal"] for c in p["campaigns"]))
        self.assertTrue(p["ledger"]["balanced"], p["ledger"])
        self.assertAlmostEqual(p["ledger"]["legacy_day_batch_total_amount"], 30.0)

        with self.assertRaises(HTTPException) as ctx:
            redeem_service.seal({"campaign_code": "VIP20"})
        self.assertEqual(ctx.exception.status_code, 409)

        for coupon, camp in (("L-3", "NEW10"), ("L-4", "VIP20")):
            with self.assertRaises(HTTPException) as ctx:
                _redeem(coupon, camp, 10)
            self.assertEqual(ctx.exception.status_code, 409)

    def test_equation_holds_across_multiple_campaign_batches(self) -> None:
        _redeem("E-1", "NEW10", 10)
        _redeem("E-2", "VIP20", 20)
        _redeem("E-3", "TEA5", 5)

        redeem_service.seal({"campaign_code": "NEW10"})
        redeem_service.seal({"campaign_code": "TEA5"})
        p = redeem_service.preview()
        led = p["ledger"]

        self.assertTrue(led["balanced"], led)
        self.assertAlmostEqual(led["day_total_amount"], 35.0)
        self.assertAlmostEqual(led["open_total_amount"], 20.0)
        self.assertAlmostEqual(led["sealed_fact_total_amount"], 15.0)
        self.assertAlmostEqual(led["campaign_batch_total_amount"], 15.0)
        self.assertAlmostEqual(
            led["day_total_amount"],
            led["open_total_amount"] + led["campaign_batch_total_amount"],
        )

        # 每家活动批 = 该活动已钉事实合计，且批内不含别家活动/别日事实
        conn = connect()
        try:
            for b in redeem_service.list_batches():
                if b["business_day"] != self.day:
                    continue
                self.assertEqual(b["scope"], "campaign")
                total = conn.execute(
                    "SELECT COALESCE(SUM(amount),0) s FROM redeem_facts WHERE batch_id=?",
                    (b["id"],),
                ).fetchone()["s"]
                self.assertAlmostEqual(float(total), float(b["total_amount"]))
                foreign = conn.execute(
                    """SELECT COUNT(*) c FROM redeem_facts
                        WHERE batch_id=? AND (business_day<>? OR campaign_code<>?)""",
                    (b["id"], b["business_day"], b["campaign_code"]),
                ).fetchone()["c"]
                self.assertEqual(int(foreign), 0)
        finally:
            conn.close()

    def test_preview_scope_matches_seal_scope(self) -> None:
        _redeem("P-1", "NEW10", 10)
        _redeem("P-2", "VIP20", 20)
        all_p = redeem_service.preview()
        one_p = redeem_service.preview(campaign_code="NEW10")

        self.assertEqual(all_p["scope"], redeem_service.SEAL_SCOPE)
        self.assertEqual(one_p["scope"], redeem_service.SEAL_SCOPE)
        self.assertEqual(one_p["open_count"], 1)
        self.assertEqual({f["campaign_code"] for f in one_p["facts"]}, {"NEW10"})
        self.assertEqual(one_p["ledger"], all_p["ledger"])

    def test_concurrent_seal_same_campaign_is_exclusive(self) -> None:
        for i in range(6):
            _redeem(f"C-{i}", "NEW10", 10)

        ok: list[dict] = []
        fail: list[HTTPException] = []
        barrier = threading.Barrier(6)

        def worker() -> None:
            barrier.wait()
            try:
                ok.append(redeem_service.seal({"campaign_code": "NEW10"}))
            except HTTPException as e:
                fail.append(e)
            except Exception as e:  # sqlite 锁等底层错误也不允许写入半批
                fail.append(HTTPException(500, str(e)))

        threads = [threading.Thread(target=worker) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(ok), 1, ok)
        self.assertEqual(len(fail), 5)
        self.assertTrue(all(e.status_code == 409 for e in fail), [e.status_code for e in fail])

        p = redeem_service.preview()
        led = p["ledger"]
        self.assertTrue(led["balanced"])
        self.assertAlmostEqual(led["sealed_fact_total_amount"], 60.0)
        self.assertAlmostEqual(led["campaign_batch_total_amount"], 60.0)
        batches = [b for b in redeem_service.list_batches() if b["business_day"] == self.day]
        self.assertEqual(len(batches), 1)
        self.assertEqual(batches[0]["fact_count"], 6)


if __name__ == "__main__":
    unittest.main(verbosity=2)
