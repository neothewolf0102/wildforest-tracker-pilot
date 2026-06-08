from __future__ import annotations

DAILY_ACTIONS_FILE = "daily_actions.json"


def load_daily_actions(store) -> list[dict]:
    return list(store.load_json(DAILY_ACTIONS_FILE, default=[]))


def upsert_daily_action(store, account_id: str, action_date: str, pve_done: bool, signal_fire_done: bool, bounty_hunter_done: bool, note: str = "") -> dict:
    actions = [item for item in load_daily_actions(store) if not (item.get("account_id") == account_id and item.get("action_date") == action_date)]
    action = {
        "account_id": account_id,
        "action_date": action_date,
        "pve_done": bool(pve_done),
        "signal_fire_done": bool(signal_fire_done),
        "bounty_hunter_done": bool(bounty_hunter_done),
        "note": note.strip(),
    }
    actions.append(action)
    store.save_json(DAILY_ACTIONS_FILE, actions)
    return action
