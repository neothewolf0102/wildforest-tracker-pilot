from __future__ import annotations

from datetime import datetime, timezone

from services.admin_service import log_activity, log_system_error

RESOURCES_FILE = "resource_snapshots.json"


def _store_email(store) -> str:
    context = getattr(store, "context", None)
    user = getattr(context, "user", None)
    email = getattr(user, "email", "") if user else ""
    return str(email or getattr(store, "namespace", "") or "")


def _safe_log_activity(store, action_type: str, action_label: str = "", metadata: dict | None = None) -> None:
    try:
        log_activity(_store_email(store), "Resources", action_type, action_label, metadata)
    except Exception:
        pass


def _safe_log_error(store, action_type: str, error: Exception | str) -> None:
    try:
        log_system_error(_store_email(store), "Resources", action_type, error, severity="error")
    except Exception:
        pass


def load_resource_snapshots(store) -> list[dict]:
    return list(store.load_json(RESOURCES_FILE, default=[]))


def latest_snapshot_by_account(snapshots: list[dict]) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    for item in snapshots:
        latest[str(item.get("account_id"))] = item
    return latest


def upsert_manual_resource_snapshot(store, account_id: str, gold: int, shards: int, wf: float, note: str = "") -> dict:
    snapshots = load_resource_snapshots(store)
    snapshot = {
        "account_id": account_id,
        "snapshot_datetime": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "gold": int(gold),
        "shards": int(shards),
        "wf": float(wf),
        "source": "manual",
        "note": note.strip(),
    }
    snapshots.append(snapshot)
    try:
        store.save_json(RESOURCES_FILE, snapshots)
    except Exception as error:
        _safe_log_error(store, "storage_save_failed", error)
        raise
    _safe_log_activity(store, "resource_snapshot_saved", str(account_id), {"account_id": account_id, "gold": int(gold), "shards": int(shards), "wf": float(wf)})
    return snapshot
