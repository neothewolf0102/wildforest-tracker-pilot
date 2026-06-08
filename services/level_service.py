from __future__ import annotations

import json
from pathlib import Path

from engines.level_cost_engine import (
    calculate_max_feasible_level,
    calculate_missing_resources,
    calculate_required_resources,
    estimate_days_needed,
    get_level_upgrade_cost,
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


def _resource_accounts(accounts: list[dict], snapshots: list[dict]) -> list[dict]:
    snapshot_map = latest_snapshot_by_account(snapshots)
    rows: list[dict] = []
    for account in accounts:
        account_id = str(account.get("account_id", ""))
        snapshot = snapshot_map.get(account_id)
        if not snapshot:
            rows.append({
                "account_id": account_id,
                "account_name": str(account.get("account_name", account_id)),
                "latest_shards": 0,
                "latest_golds": 0,
                "latest_wf": 0.0,
                "has_snapshot": False,
            })
            continue
        rows.append({
            "account_id": account_id,
            "account_name": str(account.get("account_name", account_id)),
            "latest_shards": int(snapshot.get("shards", 0) or 0),
            "latest_golds": int(snapshot.get("gold", 0) or 0),
            "latest_wf": float(snapshot.get("wf", 0.0) or 0.0),
            "has_snapshot": True,
        })
    return rows


def _account_order(accounts: list[dict], mode: str) -> list[dict]:
    if mode == "Minimum Accounts":
        return sorted(accounts, key=lambda row: (row["latest_shards"] + row["latest_golds"]), reverse=True)
    if mode == "Manual Priority":
        return list(accounts)
    return sorted(accounts, key=lambda row: (row["latest_shards"], row["latest_golds"]), reverse=True)


def _choose_account(accounts: list[dict], cost_gold: int, cost_shards: int, mode: str, sticky_account_id: str | None) -> dict | None:
    candidates = [row for row in accounts if row["latest_golds"] >= cost_gold and row["latest_shards"] >= cost_shards]
    if not candidates:
        return None
    if mode == "Minimum Accounts" and sticky_account_id:
        sticky = next((row for row in candidates if row["account_id"] == sticky_account_id), None)
        if sticky:
            return sticky
    if mode == "Manual Priority":
        return candidates[0]
    return min(candidates, key=lambda row: ((row["latest_shards"] - cost_shards) + (row["latest_golds"] - cost_gold) / 1000, row["latest_shards"] - cost_shards, row["latest_golds"] - cost_gold))


def build_multi_account_upgrade_plan(
    accounts: list[dict],
    resource_snapshots: list[dict],
    units: list[dict],
    level_cost_config: dict | None = None,
    mode: str = "Best Fit / Least Waste",
    use_all_active_accounts: bool = True,
) -> dict:
    config = level_cost_config if level_cost_config is not None else load_level_cost_config()
    selected_accounts = _resource_accounts(accounts, resource_snapshots) if use_all_active_accounts else _resource_accounts(accounts[:1], resource_snapshots)
    working_accounts = _account_order([row for row in selected_accounts if row["has_snapshot"]], mode)
    skipped_accounts = [row for row in selected_accounts if not row["has_snapshot"]]

    clean_units: list[dict] = []
    total_required_shards = 0
    total_required_golds = 0
    for index, unit in enumerate(units, start=1):
        unit_name = str(unit.get("unit_name") or f"Unit {index}").strip() or f"Unit {index}"
        current_level = int(unit.get("current_level", 1))
        target_level = int(unit.get("target_level", current_level + 1))
        required = calculate_required_resources(current_level, target_level, config)
        total_required_shards += required["required_shards"]
        total_required_golds += required["required_gold"]
        clean_units.append({
            "unit_name": unit_name,
            "current_level": current_level,
            "target_level": target_level,
            "final_level_achieved": current_level,
            "levels_gained": 0,
            "required_shards": required["required_shards"],
            "required_golds": required["required_gold"],
            "completed": False,
        })

    available_shards = sum(row["latest_shards"] for row in working_accounts)
    available_golds = sum(row["latest_golds"] for row in working_accounts)
    available_wf = sum(float(row["latest_wf"]) for row in working_accounts)
    allocation_rows: list[dict] = []
    move_map: dict[tuple[int, str], dict] = {}
    sticky_account_id: str | None = None
    step = 0

    for unit in clean_units:
        for to_level in range(unit["current_level"] + 1, unit["target_level"] + 1):
            cost = get_level_upgrade_cost(to_level, config)
            account = _choose_account(working_accounts, cost.gold, cost.shards, mode, sticky_account_id)
            if account is None:
                break
            if mode == "Minimum Accounts":
                sticky_account_id = account["account_id"]
            step += 1
            from_level = to_level - 1
            account["latest_shards"] -= cost.shards
            account["latest_golds"] -= cost.gold
            unit["final_level_achieved"] = to_level
            unit["levels_gained"] += 1
            allocation_rows.append({
                "step": step,
                "account_name": account["account_name"],
                "unit_name": unit["unit_name"],
                "from_level": from_level,
                "to_level": to_level,
                "shards_used": cost.shards,
                "golds_used": cost.gold,
                "account_remaining_shards_after_task": account["latest_shards"],
                "account_remaining_golds_after_task": account["latest_golds"],
            })
            move_key = (step if mode == "Manual Priority" else len(move_map) + 1, account["account_name"])
            if move_key not in move_map:
                move_map[move_key] = {"Step": len(move_map) + 1, "Account": account["account_name"], "Shards Used": 0, "Gold Used": 0, "Levels": 0, "Units": set()}
            move_map[move_key]["Shards Used"] += cost.shards
            move_map[move_key]["Gold Used"] += cost.gold
            move_map[move_key]["Levels"] += 1
            move_map[move_key]["Units"].add(unit["unit_name"])
        unit["completed"] = unit["final_level_achieved"] >= unit["target_level"]
        if mode == "Minimum Accounts" and not unit["completed"]:
            sticky_account_id = None

    total_used_shards = sum(row["shards_used"] for row in allocation_rows)
    total_used_golds = sum(row["golds_used"] for row in allocation_rows)
    remaining_shards = max(available_shards - total_used_shards, 0)
    remaining_golds = max(available_golds - total_used_golds, 0)
    completed = all(unit["completed"] for unit in clean_units)
    used_account_names = {row["account_name"] for row in allocation_rows}

    unit_summary = [
        {
            "Unit": unit["unit_name"],
            "Current Level": unit["current_level"],
            "Target Level": unit["target_level"],
            "Max Reached": unit["final_level_achieved"],
            "Levels Gained": unit["levels_gained"],
            "Status": "Ready" if unit["completed"] else "Not Ready",
        }
        for unit in clean_units
    ]
    recommended_moves = []
    for move in move_map.values():
        recommended_moves.append({**move, "Units": ", ".join(sorted(move["Units"]))})
    recommended_moves.sort(key=lambda row: row["Step"])

    skipped_rows = []
    for account in selected_accounts:
        if account["account_name"] in used_account_names:
            continue
        skipped_rows.append({
            "account_name": account["account_name"],
            "latest_shards": account["latest_shards"],
            "latest_golds": account["latest_golds"],
            "latest_wf": account["latest_wf"],
            "reason_not_used": "No resource snapshot" if not account["has_snapshot"] else "Could not complete next pending task or not selected",
        })

    return {
        "summary": {
            "number_of_units": len(clean_units),
            "account_jump_required": len(used_account_names),
            "enough_resource": completed,
            "required_shards": total_required_shards,
            "required_golds": total_required_golds,
            "available_shards": available_shards,
            "available_golds": available_golds,
            "remaining_shards": remaining_shards,
            "remaining_golds": remaining_golds,
            "wf_reference_balance": available_wf,
            "missing_shards": max(total_required_shards - available_shards, 0),
            "missing_golds": max(total_required_golds - available_golds, 0),
        },
        "unit_summary": unit_summary,
        "recommended_moves": recommended_moves,
        "allocation_detail": allocation_rows,
        "skipped_accounts": skipped_rows,
        "raw_unit_summary": clean_units,
        "earning_assumption": EARNING_ASSUMPTION_TEXT,
        "uses_placeholder_costs": bool(config.get("placeholder", False)),
    }
