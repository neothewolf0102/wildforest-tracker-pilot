from __future__ import annotations

from datetime import date, timedelta

TICKETS_FILE = "tickets.json"


def load_tickets(store) -> list[dict]:
    return list(store.load_json(TICKETS_FILE, default=[]))


def ticket_by_account(tickets: list[dict]) -> dict[str, dict]:
    return {str(item.get("account_id")): item for item in tickets}


def upsert_ticket(store, account_id: str, purchase_date: date, ticket_price: float, duration_days: int = 14) -> dict:
    tickets = load_tickets(store)
    expiry = purchase_date + timedelta(days=duration_days)
    ticket = {
        "account_id": account_id,
        "ticket_purchase_date": purchase_date.isoformat(),
        "ticket_expiry_date": expiry.isoformat(),
        "ticket_price_usdt": float(ticket_price),
    }
    filtered = [item for item in tickets if item.get("account_id") != account_id]
    filtered.append(ticket)
    store.save_json(TICKETS_FILE, filtered)
    return ticket
