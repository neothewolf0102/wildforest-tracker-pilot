from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

RESOURCES_FILE = "resource_snapshots.json"


def load_resource_snapshots(store) -> list[dict]:
    return list(store.load_json(RESOURCES_FILE, default=[]))


def latest_snapshot_by_account(snapshots: list[dict]) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    for item in snapshots:
        latest[str(item.get("account_id"))] = item
    return latest


def upsert_manual_resource_snapshot(
    store,
    account_id: str,
    gold: int,
    shards: int,
    wf: float,
    note: str = "",
    source: str = "manual",
    raw_paste_text: str = "",
) -> dict:
    snapshots = load_resource_snapshots(store)
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    snapshot = {
        "snapshot_id": str(uuid4()),
        "account_id": account_id,
        "snapshot_datetime": timestamp,
        "snapshot_time": timestamp,
        "gold": int(gold),
        "shards": int(shards),
        "wf": float(wf),
        "gold_balance": int(gold),
        "wild_shards_balance": int(shards),
        "wf_balance": float(wf),
        "source": source,
        "raw_paste_text": raw_paste_text,
        "created_at": timestamp,
        "note": note.strip(),
    }
    snapshots.append(snapshot)
    store.save_json(RESOURCES_FILE, snapshots)
    return snapshot
