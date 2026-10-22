"""Pull account resources entered in the Telegram shards bot into this webapp.

Flow: user types /lienket in the bot -> gets a code -> pastes it here -> the app
GETs {bot}/api/accounts with that code, previews the changes, and only writes
after the user confirms (same preview + confirm rule as OCR).
"""
from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from services.account_service import load_accounts, save_accounts
from services.resource_service import append_resource_snapshots, build_resource_snapshot

DEFAULT_BOT_API_URL = "https://wildforest-shards-bot.firmstoney.workers.dev"
LINK_FILE = "telegram_link.json"
TELEGRAM_SOURCE = "telegram"
SNAPSHOT_NOTE = "Telegram bot sync"

ACTION_CREATE = "create"
ACTION_UPDATE = "update"
ACTION_UNCHANGED = "unchanged"
ACTION_SKIP_LIMIT = "skip_limit"

ACTION_LABELS = {
    ACTION_CREATE: "Tạo acc mới",
    ACTION_UPDATE: "Cập nhật resource",
    ACTION_UNCHANGED: "Không đổi",
    ACTION_SKIP_LIMIT: "Bỏ qua (đủ số acc tối đa)",
}


class TelegramSyncError(Exception):
    pass


def _key(value: object) -> str:
    return str(value or "").strip().casefold()


def load_link_code(store) -> str:
    rows = store.load_json(LINK_FILE, default=[])
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        return str(rows[0].get("code", "") or "")
    return ""


def save_link_code(store, code: str) -> None:
    store.save_json(LINK_FILE, [{"code": str(code or "").strip()}])


def fetch_bot_accounts(api_url: str, code: str, timeout: float = 15.0) -> list[dict]:
    code = str(code or "").strip()
    if not code:
        raise TelegramSyncError("Chưa nhập mã liên kết. Gõ /lienket trong bot để lấy mã.")
    request = Request(
        f"{api_url.rstrip('/')}/api/accounts",
        headers={"Authorization": f"Bearer {code}", "User-Agent": "WildforestTracker/telegram-sync"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        if error.code == 401:
            raise TelegramSyncError("Mã liên kết sai hoặc đã bị đổi/hủy. Gõ /lienket trong bot để lấy mã mới.") from error
        raise TelegramSyncError(f"Bot trả lỗi HTTP {error.code}.") from error
    except (URLError, TimeoutError, ValueError) as error:
        raise TelegramSyncError(f"Không kết nối được bot: {error}") from error
    accounts = payload.get("accounts") if isinstance(payload, dict) else None
    if not isinstance(accounts, list):
        raise TelegramSyncError("Dữ liệu bot trả về không đúng định dạng.")
    return [item for item in accounts if isinstance(item, dict) and str(item.get("name", "")).strip()]


def _find_account(accounts: list[dict], telegram_name: str) -> dict | None:
    key = _key(telegram_name)
    for account in accounts:
        if _key(account.get("telegram_name")) == key:
            return account
    for account in accounts:
        if _key(account.get("account_name")) == key:
            return account
    return None


def _to_int(value: object, default: int = 0) -> int:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def plan_telegram_import(
    accounts: list[dict],
    snapshot_map: dict[str, dict],
    bot_accounts: list[dict],
    max_new_accounts: int | None,
) -> list[dict]:
    """Pure preview: what would change. max_new_accounts=None means unlimited."""
    rows: list[dict] = []
    remaining = max_new_accounts
    for item in bot_accounts:
        name = str(item.get("name", "")).strip()
        shards_new = _to_int(item.get("shards"))
        gold_raw = item.get("gold")
        account = _find_account(accounts, name)
        if account is None:
            if remaining is not None and remaining <= 0:
                action = ACTION_SKIP_LIMIT
            else:
                action = ACTION_CREATE
                if remaining is not None:
                    remaining -= 1
            rows.append({
                "telegram_name": name,
                "account_id": "",
                "account_name": name,
                "action": action,
                "shards_old": None,
                "gold_old": None,
                "shards_new": shards_new,
                "gold_new": _to_int(gold_raw) if gold_raw is not None else 0,
                "wf": 0.0,
            })
            continue
        account_id = str(account.get("account_id", ""))
        snapshot = snapshot_map.get(account_id, {})
        shards_old = _to_int(snapshot.get("shards")) if snapshot else None
        gold_old = _to_int(snapshot.get("gold")) if snapshot else None
        # Bot may not know gold yet (null): keep the webapp's gold.
        gold_new = _to_int(gold_raw) if gold_raw is not None else (gold_old or 0)
        unchanged = snapshot and shards_old == shards_new and gold_old == gold_new
        rows.append({
            "telegram_name": name,
            "account_id": account_id,
            "account_name": str(account.get("account_name", "")),
            "action": ACTION_UNCHANGED if unchanged else ACTION_UPDATE,
            "shards_old": shards_old,
            "gold_old": gold_old,
            "shards_new": shards_new,
            "gold_new": gold_new,
            "wf": float(snapshot.get("wf", 0.0) or 0.0) if snapshot else 0.0,
        })
    return rows


def apply_telegram_import(store, rows: list[dict]) -> dict[str, int]:
    """Write the confirmed preview: one accounts save + one snapshots save."""
    accounts = load_accounts(store)
    accounts_changed = False
    new_snapshots: list[dict] = []
    created = updated = 0
    for row in rows:
        action = row.get("action")
        if action not in (ACTION_CREATE, ACTION_UPDATE):
            continue
        if action == ACTION_CREATE:
            account = _find_account(accounts, row["telegram_name"])
            if account is None:
                account = {
                    "account_id": str(uuid4()),
                    "account_name": row["telegram_name"],
                    "wallet_address": "",
                    "active": True,
                    "note": "",
                    "source": TELEGRAM_SOURCE,
                    "telegram_name": row["telegram_name"],
                }
                accounts.append(account)
                accounts_changed = True
            created += 1
        else:
            account = next((a for a in accounts if str(a.get("account_id", "")) == row["account_id"]), None)
            if account is None:
                continue
            if not account.get("telegram_name"):
                account["telegram_name"] = row["telegram_name"]
                accounts_changed = True
            updated += 1
        new_snapshots.append(
            build_resource_snapshot(
                str(account["account_id"]),
                int(row["gold_new"]),
                int(row["shards_new"]),
                float(row.get("wf", 0.0) or 0.0),
                note=SNAPSHOT_NOTE,
                source=TELEGRAM_SOURCE,
            )
        )
    if accounts_changed:
        save_accounts(store, accounts)
    append_resource_snapshots(store, new_snapshots)
    return {"created": created, "updated": updated}
