from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

RESOURCES_FILE = "resource_snapshots.json"


def load_resource_snapshots(store) -> list[dict]:
    return list(store.load_json(RESOURCES_FILE, default=[]))


def _snapshot_timestamp(snapshot: dict) -> datetime | None:
    for field in ("snapshot_datetime", "snapshot_time", "created_at"):
        raw_value = str(snapshot.get(field, "") or "").strip()
        if not raw_value:
            continue
        try:
            parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                return parsed.astimezone(timezone.utc).replace(tzinfo=None)
            return parsed
        except ValueError:
            continue
    return None


def _with_balance_aliases(snapshot: dict) -> dict:
    normalized = dict(snapshot)
    if normalized.get("gold") in (None, ""):
        normalized["gold"] = normalized.get("gold_balance", 0)
    if normalized.get("shards") in (None, ""):
        normalized["shards"] = normalized.get("wild_shards_balance", 0)
    if normalized.get("wf") in (None, ""):
        normalized["wf"] = normalized.get("wf_balance", 0.0)
    return normalized


def latest_snapshot_by_account(snapshots: list[dict]) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    latest_meta: dict[str, tuple[datetime | None, int]] = {}
    for index, item in enumerate(snapshots):
        account_id = str(item.get("account_id", "") or "")
        if not account_id:
            continue
        timestamp = _snapshot_timestamp(item)
        current_meta = latest_meta.get(account_id)
        if current_meta is None:
            latest[account_id] = _with_balance_aliases(item)
            latest_meta[account_id] = (timestamp, index)
            continue

        current_timestamp, current_index = current_meta
        should_replace = False
        if timestamp is not None and current_timestamp is not None:
            should_replace = timestamp >= current_timestamp
        elif timestamp is not None:
            should_replace = True
        elif current_timestamp is None:
            should_replace = index >= current_index

        if should_replace:
            latest[account_id] = _with_balance_aliases(item)
            latest_meta[account_id] = (timestamp, index)
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
