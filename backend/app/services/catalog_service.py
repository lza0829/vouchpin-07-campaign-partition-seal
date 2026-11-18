from __future__ import annotations
from typing import Any
from app.db import connect
from app.repositories import settings as settings_repo
from app.repositories import facts as fact_repo
from app.repositories import batches as batch_repo
from app.repositories import events as event_repo
from app.services import redeem_service


def dashboard() -> dict[str, Any]:
    conn = connect()
    try:
        day = settings_repo.get(conn, "business_day")
        facts = fact_repo.list_facts(conn, day)
        open_n = sum(1 for f in facts if f["status"] == "open")
        sealed_n = sum(1 for f in facts if f["status"] == "sealed")
        total = round(sum(float(f["amount"]) for f in facts), 2)
        events = event_repo.list_events(conn, day)
        batches = batch_repo.list_batches(conn)
        campaign_batches = batch_repo.list_campaign_batches(conn, day)
        day_sealed = bool(batch_repo.day_scope_batches(conn, day))
        _, ledger = redeem_service.campaign_ledger(conn, day)
        return {
            "business_day": day,
            "seal_scope": redeem_service.SEAL_SCOPE,
            "event_count": len(events),
            "fact_count": len(facts),
            "open_fact_count": open_n,
            "sealed_fact_count": sealed_n,
            "redeem_total_today": total,
            "batch_count": len(batches),
            "campaign_batch_count": len(campaign_batches),
            "sealed_campaign_count": len(campaign_batches),
            "day_sealed": day_sealed,
            "day_scope_batch_count": len(batch_repo.day_scope_batches(conn, day)),
            "ledger": ledger,
        }
    finally:
        conn.close()
