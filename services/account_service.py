from __future__ import annotations

from uuid import uuid4

ACCOUNTS_FILE = "accounts.json"
MAX_ACCOUNTS_PER_USER = 10
ACCOUNT_LIMIT_MESSAGE = "Pilot limit reached: maximum 10 accounts per user."
DUPLICATE_ACCOUNT_NAME_MESSAGE = "Account name already exists. Each account name must be unique."
DUPLICATE_WALLET_MESSAGE = "Wallet address already exists. One wallet can only map to one account."


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
        raise ValueError("Account name is required.")
    if not clean_wallet:
        raise ValueError("Wallet address is required.")

    accounts = load_accounts(store)
    existing_index = next((index for index, item in enumerate(accounts) if str(item.get("account_id", "")) == str(account_id or "")), None)
    if existing_index is None and len(accounts) >= MAX_ACCOUNTS_PER_USER:
        raise ValueError(ACCOUNT_LIMIT_MESSAGE)

    validate_account_unique(accounts, clean_name, clean_wallet, account_id)

    account = {
        "account_id": account_id or str(uuid4()),
        "account_name": clean_name,
        "wallet_address": clean_wallet,
        "active": bool(active),
        "note": _normalize_text(note),
    }
    if existing_index is None:
        accounts.append(account)
    else:
        accounts[existing_index] = account
    save_accounts(store, accounts)
    return account


def delete_account(store, account_id: str) -> bool:
    accounts = load_accounts(store)
    target_id = str(account_id or "")
    remaining = [item for item in accounts if str(item.get("account_id", "")) != target_id]
    if len(remaining) == len(accounts):
        return False
    save_accounts(store, remaining)
    return True
