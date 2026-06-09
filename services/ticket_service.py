from __future__ import annotations

from datetime import date, timedelta

from services.admin_service import log_activity, log_system_error

TICKETS_FILE = "tickets.json"


def _store_email(store) -> str:
    context = getattr(store, "context", None)
    user = getattr(context, "user", None)
    email = getattr(user, "email", "") if user else ""
    return str(email or getattr(store, "namespace", "") or "")


def _safe_log_activity(store, action_type: str, action_label: str = "", metadata: dict | None = None) -> None:
    try:
        log_activity(_store_email(store), "Tickets", action_type, action_label, metadata)
    except Exception:
        pass


def _safe_log_error(store, action_type: str, error: Exception | str) -> None:
    try:
        log_system_error(_store_email(store), "Tickets", action_type, error, severity="error")
    except Exception:
        pass


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
    try:
        store.save_json(TICKETS_FILE, filtered)
    except Exception as error:
        _safe_log_error(store, "storage_save_failed", error)
        raise
    _safe_log_activity(store, "ticket_saved", str(account_id), {"account_id": account_id, "ticket_price_usdt": float(ticket_price), "duration_days": int(duration_days)})
    return ticket
