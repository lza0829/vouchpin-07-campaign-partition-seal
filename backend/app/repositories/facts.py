from __future__ import annotations
import sqlite3
from typing import Any


def list_facts(conn: sqlite3.Connection, business_day: str | None = None) -> list[dict[str, Any]]:
    if business_day:
        rows = conn.execute(
            "SELECT * FROM redeem_facts WHERE business_day=? ORDER BY id",
            (business_day,),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM redeem_facts ORDER BY id DESC LIMIT 200").fetchall()
    return [dict(r) for r in rows]


def insert_fact(conn: sqlite3.Connection, **fields: Any) -> int:
    cur = conn.execute(
        "INSERT INTO redeem_facts(coupon_code, campaign_code, amount, business_day, event_id, status) VALUES(?,?,?,?,?,?)",
        (
            fields["coupon_code"],
            fields["campaign_code"],
            float(fields["amount"]),
            fields["business_day"],
            int(fields["event_id"]),
            fields.get("status") or "open",
        ),
    )
    return int(cur.lastrowid)


def open_facts_for_day(conn: sqlite3.Connection, business_day: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM redeem_facts WHERE business_day=? AND status='open' ORDER BY id",
        (business_day,),
    ).fetchall()
    return [dict(r) for r in rows]


def open_facts_for_campaign(
    conn: sqlite3.Connection, business_day: str, campaign_code: str
) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM redeem_facts WHERE business_day=? AND campaign_code=? AND status='open' ORDER BY id",
        (business_day, campaign_code),
    ).fetchall()
    return [dict(r) for r in rows]


def campaign_day_totals(conn: sqlite3.Connection, business_day: str) -> dict[str, dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT campaign_code,
               COUNT(*) AS fact_count,
               SUM(CASE WHEN status='open' THEN 1 ELSE 0 END) AS open_count,
               SUM(CASE WHEN status='sealed' THEN 1 ELSE 0 END) AS sealed_count,
               COALESCE(SUM(amount), 0) AS total_amount,
               COALESCE(SUM(CASE WHEN status='open' THEN amount ELSE 0 END), 0) AS open_total,
               COALESCE(SUM(CASE WHEN status='sealed' THEN amount ELSE 0 END), 0) AS sealed_total
          FROM redeem_facts
         WHERE business_day=?
         GROUP BY campaign_code
         ORDER BY campaign_code
        """,
        (business_day,),
    ).fetchall()
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        out[str(r["campaign_code"])] = {
            "fact_count": int(r["fact_count"]),
            "open_count": int(r["open_count"] or 0),
            "sealed_count": int(r["sealed_count"] or 0),
            "total_amount": round(float(r["total_amount"] or 0), 2),
            "open_total": round(float(r["open_total"] or 0), 2),
            "sealed_total": round(float(r["sealed_total"] or 0), 2),
        }
    return out


def mark_batched(conn: sqlite3.Connection, fact_ids: list[int], batch_id: int) -> None:
    """Seal open facts; only open rows may be claimed by a batch."""
    conn.executemany(
        "UPDATE redeem_facts SET status='sealed', batch_id=? WHERE id=? AND status='open'",
        [(batch_id, fid) for fid in fact_ids],
    )


def count_claimed(conn: sqlite3.Connection, fact_ids: list[int], batch_id: int) -> int:
    if not fact_ids:
        return 0
    qmarks = ",".join("?" for _ in fact_ids)
    row = conn.execute(
        f"SELECT COUNT(*) AS c FROM redeem_facts WHERE batch_id=? AND id IN ({qmarks})",
        [batch_id, *fact_ids],
    ).fetchone()
    return int(row["c"])
