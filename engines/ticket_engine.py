from __future__ import annotations

from datetime import date

DEFAULT_TICKET_DURATION_DAYS = 14


def days_until_expiry(expiry_date: str) -> int:
    if not expiry_date:
        return 0
    try:
        return (date.fromisoformat(expiry_date) - date.today()).days
    except ValueError:
        return 0


def ticket_status(expiry_date: str) -> str:
    days_left = days_until_expiry(expiry_date)
    if days_left < 0:
        return "Expired"
    if days_left <= 2:
        return "Expiring Soon"
    return "Valid"
