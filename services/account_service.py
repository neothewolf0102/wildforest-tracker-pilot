from __future__ import annotations

from uuid import uuid4

from services.admin_service import DUPLICATE_ACCOUNT_NAME_MESSAGE as _unused  # type: ignore[attr-defined]
from services.admin_service import log_activity, log_system_error, log_validation_failed

ACCOUNTS_FILE = "accounts.json"
MAX_ACCOUNTS_PER_USER = 5
ACCOUNT_LIMIT_MESSAGE = "Pilot limit reached: maximum 5 accounts per user."
DUPLICATE_ACCOUNT_NAME_MESSAGE = "Account name already exists. Each account name must be unique."
DUPLICATE_WALLET_MESSAGE = "Wallet address already exists. One wallet can only map to one account."


def _store_email(store) -> str:
    context = getattr(store, "context", None)
    user = getattr(context, "user", None)
    email = getattr(user, "email", "") if user else ""
    return str(email or getattr(store, "namespace", "") or "")


def _safe_log_activity(store, action_type: str, action_label: str = "", metadata: dict | None = None, status: str = "success", severity: str = "info") -> None:
    try:
        log_activity(_store_email(store), "Account Setup", action_type, action_label, metadata, status=status, severity=severity)
    except Exception:
        pass


def _safe_log_validation(store, action_label: str, metadata: dict | None = None) -> None:
    try:
        log_validation_failed(_store_email(store), "Account Setup", action_label, metadata)
    except Exception:
        pass


def _safe_log_error(store, action_type: str, error: Exception | str) -> None:
    try:
        log_system_error(_store_email(store), "Account Setup", action_type, error, severity="error")
    except Exception:
        pass


def load_accounts(store) -> list[dict]:
    return list(store.load_json(ACCOUNTS_FILE, default=[]))


def save_accounts(store, accounts: list[dict]) -> None:
    store.save_json(ACCOUNTS_FILE, accounts)


def active_accounts(accounts: list[dict]) -> list[dict]:
    return [item for item in accounts if item.get("active", True)]


def _normalize_text(value: str) -> str:
    return str(value or "").strip()


def _normalize_key(value: str) -> str:
    return _normalize_text(value).casefold()


def _normalize_wallet(value: str) -> str:
    return _normalize_text(value).casefold()


def validate_account_unique(accounts: list[dict], account_name: str, wallet_address: str, account_id: str | None = None) -> None:
    account_name_key = _normalize_key(account_name)
    wallet_key = _normalize_wallet(wallet_address)
    for item in accounts:
        existing_id = str(item.get("account_id", ""))
        if account_id and existing_id == str(account_id):
            continue
        if _normalize_key(item.get("account_name", "")) == account_name_key:
            raise ValueError(DUPLICATE_ACCOUNT_NAME_MESSAGE)
        if wallet_key and _normalize_wallet(item.get("wallet_address", "")) == wallet_key:
            raise ValueError(DUPLICATE_WALLET_MESSAGE)


def upsert_account(store, account_name: str, wallet_address: str, active: bool = True, note: str = "", account_id: str | None = None) -> dict:
    clean_name = _normalize_text(account_name)
    clean_wallet = _normalize_text(wallet_address)
    if not clean_name:
        _safe_log_validation(store, "Account name is required.")
        raise ValueError("Account name is required.")
    if not clean_wallet:
        _safe_log_validation(store, "Wallet address is required.")
        raise ValueError("Wallet address is required.")

    accounts = load_accounts(store)
    existing_index = next((index for index, item in enumerate(accounts) if str(item.get("account_id", "")) == str(account_id or "")), None)
    is_create = existing_index is None
    if is_create and len(accounts) >= MAX_ACCOUNTS_PER_USER:
        _safe_log_validation(store, ACCOUNT_LIMIT_MESSAGE, {"account_name": clean_name})
        raise ValueError(ACCOUNT_LIMIT_MESSAGE)

    try:
        validate_account_unique(accounts, clean_name, clean_wallet, account_id)
    except ValueError as error:
        action_type = "duplicate_account_name_blocked" if str(error) == DUPLICATE_ACCOUNT_NAME_MESSAGE else "duplicate_wallet_blocked" if str(error) == DUPLICATE_WALLET_MESSAGE else "validation_failed"
        _safe_log_activity(store, action_type, str(error), {"account_name": clean_name, "wallet_address": clean_wallet}, status="blocked", severity="warning")
        raise

    account = {
        "account_id": account_id or str(uuid4()),
        "account_name": clean_name,
        "wallet_address": clean_wallet,
        "active": bool(active),
        "note": _normalize_text(note),
    }
    if is_create:
        accounts.append(account)
    else:
        accounts[existing_index] = account
    try:
        save_accounts(store, accounts)
    except Exception as error:
        _safe_log_error(store, "account_save_failed", error)
        raise
    _safe_log_activity(store, "account_created" if is_create else "account_updated", clean_name, {"account_id": account["account_id"]})
    return account


def delete_account(store, account_id: str) -> bool:
    accounts = load_accounts(store)
    target_id = str(account_id or "")
    remaining = [item for item in accounts if str(item.get("account_id", "")) != target_id]
    if len(remaining) == len(accounts):
        return False
    try:
        save_accounts(store, remaining)
    except Exception as error:
        _safe_log_error(store, "account_save_failed", error)
        raise
    _safe_log_activity(store, "account_deleted", target_id, {"account_id": target_id})
    return True
