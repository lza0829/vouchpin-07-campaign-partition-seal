from __future__ import annotations
import sqlite3
from typing import Any


def list_batches(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute("SELECT * FROM redeem_batches ORDER BY id DESC").fetchall()]


def list_campaign_batches(conn: sqlite3.Connection, business_day: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM redeem_batches WHERE business_day=? AND scope='campaign' AND status='sealed' ORDER BY id",
        (business_day,),
    ).fetchall()
    return [dict(r) for r in rows]


def campaign_batch_map(conn: sqlite3.Connection, business_day: str) -> dict[str, dict[str, Any]]:
    return {
        str(r["campaign_code"]): r
        for r in list_campaign_batches(conn, business_day)
        if r["campaign_code"]
    }


def get_campaign_batch(
    conn: sqlite3.Connection, business_day: str, campaign_code: str
) -> dict[str, Any] | None:
    row = conn.execute(
        """SELECT * FROM redeem_batches
            WHERE business_day=? AND scope='campaign' AND campaign_code=? AND status='sealed'
            LIMIT 1""",
        (business_day, campaign_code),
    ).fetchone()
    return dict(row) if row else None


def day_scope_batches(conn: sqlite3.Connection, business_day: str) -> list[dict[str, Any]]:
    """Legacy whole-day batches. Campaign-granularity sealing never creates these."""
    rows = conn.execute(
        "SELECT * FROM redeem_batches WHERE business_day=? AND scope='day' ORDER BY id",
        (business_day,),
    ).fetchall()
    return [dict(r) for r in rows]


def create_batch(conn: sqlite3.Connection, **fields: Any) -> int:
    cur = conn.execute(
        "INSERT INTO redeem_batches(business_day, scope, campaign_code, status, fact_count, total_amount, sealed_at, note) VALUES(?,?,?,?,?,?,?,?)",
        (
            fields["business_day"],
            fields.get("scope") or "campaign",
            fields.get("campaign_code"),
            fields.get("status") or "sealed",
            int(fields.get("fact_count") or 0),
            float(fields.get("total_amount") or 0),
            fields.get("sealed_at"),
            fields.get("note") or "",
        ),
    )
    return int(cur.lastrowid)
