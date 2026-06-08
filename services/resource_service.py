from __future__ import annotations

from datetime import datetime, timezone

RESOURCES_FILE = "resource_snapshots.json"


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
    store.save_json(RESOURCES_FILE, snapshots)
    return snapshot
