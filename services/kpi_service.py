from __future__ import annotations

from datetime import date


def build_kpi_summary(accounts: list[dict], tickets: list[dict], snapshots: list[dict], daily_actions: list[dict], wf_price_usdt: float = 0.0) -> dict:
    active_ids = {item.get("account_id") for item in accounts if item.get("active", True)}
    latest: dict[str, dict] = {}
    for item in snapshots:
        latest[str(item.get("account_id"))] = item
    total_gold = sum(int(item.get("gold", 0) or 0) for item in latest.values())
    total_shards = sum(int(item.get("shards", 0) or 0) for item in latest.values())
    total_wf = sum(float(item.get("wf", 0.0) or 0.0) for item in latest.values())
    today = date.today().isoformat()
    valid_tickets = sum(1 for item in tickets if str(item.get("ticket_expiry_date", "")) >= today)
    ticket_cost = sum(float(item.get("ticket_price_usdt", 0.0) or 0.0) for item in tickets)
    today_actions = [item for item in daily_actions if item.get("action_date") == today]
    completed = sum(bool(item.get("pve_done")) + bool(item.get("signal_fire_done")) + bool(item.get("bounty_hunter_done")) for item in today_actions)
    possible = max(len(active_ids) * 3, 1)
    roi = total_wf * float(wf_price_usdt) - ticket_cost
    return {
        "active_accounts": len(active_ids),
        "total_gold": total_gold,
        "total_shards": total_shards,
        "total_wf": total_wf,
        "valid_tickets": valid_tickets,
        "ticket_cost_usdt": ticket_cost,
        "daily_completion_rate": completed / possible * 100,
        "simple_roi_usdt": roi,
        "roi_status": "positive" if roi >= 0 else "negative",
    }
