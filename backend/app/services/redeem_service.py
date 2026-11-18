from __future__ import annotations
import sqlite3
from datetime import datetime
from typing import Any
from fastapi import HTTPException
from app.db import connect
from app.repositories import settings as settings_repo
from app.repositories import facts as fact_repo
from app.repositories import batches as batch_repo
from app.repositories import campaigns as camp_repo

# 全局唯一的钉扎范围粒度：按活动分批钉扎。
# 整日钉扎与之互斥，不允许在同一套数据上混用（混用会导致日级写闸漏拦、
# 或同一批事实被两次钉扎重复计合计）。
SEAL_SCOPE = "campaign"


def _day(conn: sqlite3.Connection, business_day: str | None) -> str:
    return business_day or settings_repo.get(conn, "business_day")


def campaign_ledger(
    conn: sqlite3.Connection,
    business_day: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build one consistent view: per-campaign rows + day-level totals/equation."""
    titles = {str(c["code"]): str(c["title"]) for c in camp_repo.list_all(conn)}
    totals = fact_repo.campaign_day_totals(conn, business_day)
    sealed_batches = batch_repo.campaign_batch_map(conn, business_day)
    legacy_day_batches = batch_repo.day_scope_batches(conn, business_day)
    day_sealed = bool(legacy_day_batches)

    codes = sorted(set(totals) | set(sealed_batches))
    rows: list[dict[str, Any]] = []
    for code in codes:
        t = totals.get(code, {})
        batch = sealed_batches.get(code)
        sealed = batch is not None
        open_count = int(t.get("open_count", 0))
        row = {
            "campaign_code": code,
            "campaign_title": titles.get(code, ""),
            "fact_count": int(t.get("fact_count", 0)),
            "open_count": open_count,
            "open_total": round(float(t.get("open_total", 0)), 2),
            "sealed_count": int(t.get("sealed_count", 0)),
            "sealed_total": round(float(t.get("sealed_total", 0)), 2),
            "sealed": sealed,
            "batch_id": int(batch["id"]) if batch else None,
            "batch_fact_count": int(batch["fact_count"]) if batch else 0,
            "batch_total_amount": round(float(batch["total_amount"]), 2) if batch else 0.0,
            "can_seal": open_count > 0 and not sealed and not day_sealed,
            "block_reason": (
                "" if (open_count > 0 and not sealed and not day_sealed)
                else (
                    f"业务日 {business_day} 已整日钉扎，不得再按活动补钉"
                    if day_sealed
                    else (
                        f"活动 {code} 已钉扎，禁止重复钉扎"
                        if sealed
                        else "无可钉扎的 open 核销事实"
                    )
                )
            ),
        }
        rows.append(row)

    day_total = round(sum(r["open_total"] + r["sealed_total"] for r in rows), 2)
    open_total = round(sum(r["open_total"] for r in rows), 2)
    sealed_fact_total = round(sum(r["sealed_total"] for r in rows), 2)
    batch_total = round(sum(r["batch_total_amount"] for r in rows), 2)
    legacy_total = round(
        sum(float(b["total_amount"]) for b in legacy_day_batches), 2
    )
    expected_sealed = round(batch_total + legacy_total, 2)
    balanced = (
        abs(day_total - round(open_total + sealed_fact_total, 2)) < 0.005
        and abs(sealed_fact_total - expected_sealed) < 0.005
    )
    ledger = {
        "day_total_amount": day_total,
        "open_total_amount": open_total,
        "sealed_fact_total_amount": sealed_fact_total,
        "campaign_batch_total_amount": batch_total,
        "legacy_day_batch_total_amount": legacy_total,
        "sealed_expected_total_amount": expected_sealed,
        "balanced": balanced,
        "equation": "日核销额 = open 合计 + 已钉活动批合计",
    }
    return rows, ledger


def list_facts(business_day: str | None = None) -> list[dict[str, Any]]:
    conn = connect()
    try:
        return fact_repo.list_facts(conn, _day(conn, business_day))
    finally:
        conn.close()


def preview(
    business_day: str | None = None, campaign_code: str | None = None
) -> dict[str, Any]:
    conn = connect()
    try:
        day = _day(conn, business_day)
        campaigns, ledger = campaign_ledger(conn, day)
        if campaign_code:
            campaigns = [c for c in campaigns if c["campaign_code"] == campaign_code]
        opens = fact_repo.open_facts_for_day(conn, day)
        if campaign_code:
            opens = [f for f in opens if f["campaign_code"] == campaign_code]
        legacies = batch_repo.day_scope_batches(conn, day)
        return {
            "business_day": day,
            "scope": SEAL_SCOPE,
            "campaign_code": campaign_code,
            "campaigns": campaigns,
            "open_count": len(opens),
            "open_total": round(sum(float(f["amount"]) for f in opens), 2),
            "day_sealed": bool(legacies),
            "facts": opens,
            # ledger 始终是「业务日」口径：活动明细可按 campaign_code 收窄，
            # 但合计等式只在一个日级口径下成立，避免二次累加或漏计。
            "ledger_scope": "day",
            "ledger": ledger,
        }
    finally:
        conn.close()


def seal(body: dict[str, Any]) -> dict[str, Any]:
    requested_scope = (body.get("scope") or SEAL_SCOPE).strip()
    campaign_code = (body.get("campaign_code") or "").strip()
    conn = connect(immediate=True)
    try:
        day = _day(conn, body.get("business_day"))
        if requested_scope != SEAL_SCOPE:
            raise HTTPException(
                409,
                f"钉扎粒度已全局固定为「按活动分批钉」，禁止混用整日钉扎（业务日 {day}）",
            )
        if not campaign_code:
            raise HTTPException(400, "按活动分批钉扎须指定 campaign_code")
        if batch_repo.day_scope_batches(conn, day):
            raise HTTPException(409, f"业务日 {day} 已整日钉扎，不得再按活动补钉")

        existing = batch_repo.get_campaign_batch(conn, day, campaign_code)
        if existing:
            raise HTTPException(
                409,
                f"活动 {campaign_code} 在业务日 {day} 已钉扎（批次 #{existing['id']}），禁止重复钉扎",
            )

        opens = fact_repo.open_facts_for_campaign(conn, day, campaign_code)
        if not opens:
            raise HTTPException(400, f"活动 {campaign_code} 无可钉扎的 open 核销事实")

        total = round(sum(float(f["amount"]) for f in opens), 2)
        sealed_at = datetime.now().replace(microsecond=0).isoformat()
        try:
            bid = batch_repo.create_batch(
                conn,
                business_day=day,
                scope="campaign",
                campaign_code=campaign_code,
                status="sealed",
                fact_count=len(opens),
                total_amount=total,
                sealed_at=sealed_at,
                note=body.get("note") or "",
            )
        except sqlite3.IntegrityError as e:
            raise HTTPException(
                409, f"活动 {campaign_code} 正被另一钉扎操作占用，请重试"
            ) from e

        fact_ids = [int(f["id"]) for f in opens]
        fact_repo.mark_batched(conn, fact_ids, bid)
        claimed = fact_repo.count_claimed(conn, fact_ids, bid)
        if claimed != len(fact_ids):
            raise HTTPException(
                409,
                f"活动 {campaign_code} 钉扎存在并发冲突（已认领 {claimed}/{len(fact_ids)}），请重试",
            )

        # 合计等式核对：批内金额 = 被钉事实金额，且批只含本活动本日事实。
        batch_total = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS s FROM redeem_facts WHERE batch_id=?",
            (bid,),
        ).fetchone()["s"]
        foreign = conn.execute(
            """SELECT COUNT(*) AS c FROM redeem_facts
                WHERE batch_id=? AND (business_day<>? OR campaign_code<>?)""",
            (bid, day, campaign_code),
        ).fetchone()["c"]
        if int(foreign) or abs(float(batch_total) - total) > 0.005:
            raise HTTPException(409, "活动钉扎合计核对失败，已回滚")

        conn.commit()
        return {
            "batch_id": bid,
            "business_day": day,
            "scope": "campaign",
            "campaign_code": campaign_code,
            "fact_count": len(opens),
            "total_amount": total,
            "status": "sealed",
        }
    finally:
        conn.close()


def list_batches() -> list[dict[str, Any]]:
    conn = connect()
    try:
        return batch_repo.list_batches(conn)
    finally:
        conn.close()
