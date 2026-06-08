from __future__ import annotations

import json
from pathlib import Path

from engines.level_cost_engine import (
    calculate_max_feasible_level,
    calculate_missing_resources,
    calculate_required_resources,
    estimate_days_needed,
)
from models.level_plan import LevelPlan
from services.resource_service import latest_snapshot_by_account, load_resource_snapshots

NO_RESOURCE_SNAPSHOT_MESSAGE = "No resource snapshot found for this account. Please add resources first."
PLACEHOLDER_COST_WARNING = "Level cost table is using placeholder values. Please configure real Wildforest level costs before production use."
BASE_GOLD_WITHOUT_LORD_PER_DAY = 260
SIGNAL_FIRE_WAVES_PER_DAY = 2
SIGNAL_FIRE_GOLD_PER_WAVE = 150
SIGNAL_FIRE_MAX_GOLD_PER_DAY = SIGNAL_FIRE_WAVES_PER_DAY * SIGNAL_FIRE_GOLD_PER_WAVE
DAILY_GOLD_EARNING_ASSUMPTION = BASE_GOLD_WITHOUT_LORD_PER_DAY + SIGNAL_FIRE_MAX_GOLD_PER_DAY
EARNING_ASSUMPTION_TEXT = (
    "Estimated days use trigger-based gold earning assumptions: "
    "260 gold/day/account base without lord plus Signal Fire 2 waves/day at 150 gold per wave, "
    "max 300 Signal Fire gold/day/account if both waves are completed. This is not passive or guaranteed earning."
)


class NoResourceSnapshotError(ValueError):
    pass


def load_level_cost_config(config_path: str | Path = "config/level_costs.json") -> dict:
    path = Path(config_path)
    if not path.exists():
        return {"placeholder": True, "warning": PLACEHOLDER_COST_WARNING, "level_costs": []}
    return json.loads(path.read_text(encoding="utf-8"))


def get_latest_account_snapshot(store, account_id: str) -> dict:
    snapshot = latest_snapshot_by_account(load_resource_snapshots(store)).get(str(account_id))
    if not snapshot:
        raise NoResourceSnapshotError(NO_RESOURCE_SNAPSHOT_MESSAGE)
    return snapshot


def build_level_plan(store, account_id: str, unit_name: str, current_level: int, target_level: int, level_cost_config: dict | None = None) -> LevelPlan:
    if not unit_name.strip():
        raise ValueError("Unit name is required.")
    config = level_cost_config if level_cost_config is not None else load_level_cost_config()
    snapshot = get_latest_account_snapshot(store, account_id)
    required = calculate_required_resources(current_level, target_level, config)
    available_gold = int(snapshot.get("gold", 0) or 0)
    available_shards = int(snapshot.get("shards", 0) or 0)
    missing = calculate_missing_resources(required["required_gold"], required["required_shards"], available_gold, available_shards)
    return LevelPlan(
        account_id=account_id,
        unit_name=unit_name.strip(),
        current_level=int(current_level),
        target_level=int(target_level),
        required_gold=required["required_gold"],
        required_shards=required["required_shards"],
        available_gold=available_gold,
        available_shards=available_shards,
        missing_gold=int(missing["missing_gold"]),
        missing_shards=int(missing["missing_shards"]),
        can_upgrade_now=bool(missing["can_upgrade_now"]),
        estimated_days_needed=estimate_days_needed(int(missing["missing_gold"]), DAILY_GOLD_EARNING_ASSUMPTION),
        earning_assumption=EARNING_ASSUMPTION_TEXT,
        uses_placeholder_costs=bool(config.get("placeholder", False)),
    )


def build_account_jump_matrix(accounts: list[dict], resource_snapshots: list[dict], unit_name: str, current_level: int, target_level: int, level_cost_config: dict | None = None) -> dict:
    if not unit_name.strip():
        raise ValueError("Unit name is required.")
    config = level_cost_config if level_cost_config is not None else load_level_cost_config()
    required = calculate_required_resources(current_level, target_level, config)
    snapshot_map = latest_snapshot_by_account(resource_snapshots)
    rows: list[dict] = []

    for account in accounts:
        account_id = str(account.get("account_id", ""))
        account_name = str(account.get("account_name", account_id))
        snapshot = snapshot_map.get(account_id)
        if not snapshot:
            rows.append({
                "Account": account_name,
                "Unit": unit_name.strip(),
                "Current Level": int(current_level),
                "Target Level": int(target_level),
                "Max Jump Level": int(current_level),
                "Jump Levels": 0,
                "Can Reach Target": "No",
                "Available Gold": 0,
                "Available Shards": 0,
                "Required Gold": required["required_gold"],
                "Required Shards": required["required_shards"],
                "Missing Gold": required["required_gold"],
                "Missing Shards": required["required_shards"],
                "Next Missing Gold": required["required_gold"],
                "Next Missing Shards": required["required_shards"],
                "Estimated Days": estimate_days_needed(required["required_gold"], DAILY_GOLD_EARNING_ASSUMPTION),
                "Status": NO_RESOURCE_SNAPSHOT_MESSAGE,
            })
            continue

        available_gold = int(snapshot.get("gold", 0) or 0)
        available_shards = int(snapshot.get("shards", 0) or 0)
        missing = calculate_missing_resources(required["required_gold"], required["required_shards"], available_gold, available_shards)
        feasible = calculate_max_feasible_level(current_level, target_level, available_gold, available_shards, config)
        can_reach_target = bool(missing["can_upgrade_now"])
        rows.append({
            "Account": account_name,
            "Unit": unit_name.strip(),
            "Current Level": int(current_level),
            "Target Level": int(target_level),
            "Max Jump Level": feasible["max_feasible_level"],
            "Jump Levels": feasible["jump_levels"],
            "Can Reach Target": "Yes" if can_reach_target else "No",
            "Available Gold": available_gold,
            "Available Shards": available_shards,
            "Required Gold": required["required_gold"],
            "Required Shards": required["required_shards"],
            "Missing Gold": int(missing["missing_gold"]),
            "Missing Shards": int(missing["missing_shards"]),
            "Next Missing Gold": feasible["next_missing_gold"],
            "Next Missing Shards": feasible["next_missing_shards"],
            "Estimated Days": estimate_days_needed(int(missing["missing_gold"]), DAILY_GOLD_EARNING_ASSUMPTION),
            "Status": "Ready" if can_reach_target else "Partial jump available" if feasible["jump_levels"] > 0 else "Insufficient resources",
        })

    rows.sort(key=lambda row: (row["Can Reach Target"] != "Yes", -int(row["Max Jump Level"]), int(row["Missing Gold"]), int(row["Missing Shards"]), row["Account"]))
    best = rows[0] if rows else None
    return {
        "unit_name": unit_name.strip(),
        "current_level": int(current_level),
        "target_level": int(target_level),
        "required_gold": required["required_gold"],
        "required_shards": required["required_shards"],
        "ready_accounts": sum(1 for row in rows if row["Can Reach Target"] == "Yes"),
        "best_account": best["Account"] if best else "None",
        "best_max_level": best["Max Jump Level"] if best else int(current_level),
        "rows": rows,
        "earning_assumption": EARNING_ASSUMPTION_TEXT,
        "uses_placeholder_costs": bool(config.get("placeholder", False)),
    }
