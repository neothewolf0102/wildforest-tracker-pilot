from __future__ import annotations

from collections.abc import Iterable, Mapping
from math import isnan


BLANK_DISPLAY_VALUES = {"", "nan", "nat", "none", "<na>"}


def clean_display_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and isnan(value):
        return ""
    text = str(value).strip()
    if text.casefold() in BLANK_DISPLAY_VALUES:
        return ""
    return text


def _read_value(account: object, field: str) -> object:
    if isinstance(account, Mapping):
        return account.get(field, "")
    return getattr(account, field, "")


def account_display_name(account: object) -> str:
    account_name = clean_display_text(_read_value(account, "account_name"))
    note = clean_display_text(_read_value(account, "note"))
    fallback = clean_display_text(_read_value(account, "account_id"))

    if account_name and note:
        return f"{account_name} ({note})"
    return account_name or fallback or note


def account_display_lookup(accounts: Iterable[object], key_field: str = "account_id") -> dict[str, str]:
    labels: dict[str, str] = {}
    for account in accounts:
        key = clean_display_text(_read_value(account, key_field))
        if key:
            labels[key] = account_display_name(account)
    return labels
