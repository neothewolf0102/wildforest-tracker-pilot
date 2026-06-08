from __future__ import annotations

from uuid import uuid4

ACCOUNTS_FILE = "accounts.json"
MAX_ACCOUNTS_PER_USER = 5
ACCOUNT_LIMIT_MESSAGE = "Pilot limit reached: maximum 5 accounts per user."


def load_accounts(store) -> list[dict]:
    return list(store.load_json(ACCOUNTS_FILE, default=[]))


def active_accounts(accounts: list[dict]) -> list[dict]:
    return [item for item in accounts if item.get("active", True)]


def upsert_account(store, account_name: str, wallet_address: str, active: bool = True, note: str = "", account_id: str | None = None) -> dict:
    if not account_name.strip():
        raise ValueError("Account name is required.")
    accounts = load_accounts(store)
    existing_index = next((index for index, item in enumerate(accounts) if item.get("account_id") == account_id), None)
    if existing_index is None and len(accounts) >= MAX_ACCOUNTS_PER_USER:
        raise ValueError(ACCOUNT_LIMIT_MESSAGE)
    account = {
        "account_id": account_id or str(uuid4()),
        "account_name": account_name.strip(),
        "wallet_address": wallet_address.strip(),
        "active": bool(active),
        "note": note.strip(),
    }
    if existing_index is None:
        accounts.append(account)
    else:
        accounts[existing_index] = account
    store.save_json(ACCOUNTS_FILE, accounts)
    return account
