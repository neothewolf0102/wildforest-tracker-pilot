from __future__ import annotations

from dataclasses import dataclass

MISSING_LEVEL_COST_MESSAGE = "Missing level cost configuration for this level range."
PLACEHOLDER_MAX_LEVEL = 60


class MissingLevelCostConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class LevelCost:
    level: int
    gold: int
    shards: int


def placeholder_level_cost(level: int) -> LevelCost:
    level = int(level)
    return LevelCost(level=level, gold=100 + level * level * 12, shards=max(1, level * 3))


def normalize_level_cost_table(level_costs: dict | list[dict]) -> tuple[dict[int, LevelCost], bool]:
    is_placeholder = bool(level_costs.get("placeholder", False)) if isinstance(level_costs, dict) else False
    raw_costs = level_costs.get("level_costs", level_costs) if isinstance(level_costs, dict) else level_costs
    table: dict[int, LevelCost] = {}
    if isinstance(raw_costs, dict):
        for level, cost in raw_costs.items():
            table[int(level)] = LevelCost(level=int(level), gold=int(cost.get("gold", 0)), shards=int(cost.get("shards", 0)))
    else:
        for item in raw_costs:
            level = int(item["level"])
            table[level] = LevelCost(level=level, gold=int(item.get("gold", 0)), shards=int(item.get("shards", 0)))
    if is_placeholder:
        for level in range(2, PLACEHOLDER_MAX_LEVEL + 1):
            table.setdefault(level, placeholder_level_cost(level))
    return table, is_placeholder


def validate_level_range(current_level: int, target_level: int) -> None:
    if int(current_level) <= 0 or int(target_level) <= 0:
        raise ValueError("Current level and target level must be positive integers.")
    if int(target_level) <= int(current_level):
        raise ValueError("Target level must be greater than current level.")


def _cost_for_level(table: dict[int, LevelCost], is_placeholder: bool, level: int) -> LevelCost:
    cost = table.get(int(level))
    if cost is None or (is_placeholder and int(level) > PLACEHOLDER_MAX_LEVEL):
        raise MissingLevelCostConfigurationError(MISSING_LEVEL_COST_MESSAGE)
    return cost


def calculate_required_resources(current_level: int, target_level: int, level_costs: dict | list[dict]) -> dict[str, int]:
    validate_level_range(current_level, target_level)
    table, is_placeholder = normalize_level_cost_table(level_costs)
    required_gold = 0
    required_shards = 0
    for level in range(int(current_level) + 1, int(target_level) + 1):
        cost = _cost_for_level(table, is_placeholder, level)
        required_gold += cost.gold
        required_shards += cost.shards
    return {"required_gold": required_gold, "required_shards": required_shards}


def calculate_missing_resources(required_gold: int, required_shards: int, available_gold: int, available_shards: int) -> dict[str, int | bool]:
    missing_gold = max(int(required_gold) - int(available_gold), 0)
    missing_shards = max(int(required_shards) - int(available_shards), 0)
    return {"missing_gold": missing_gold, "missing_shards": missing_shards, "can_upgrade_now": missing_gold == 0 and missing_shards == 0}


def calculate_max_feasible_level(current_level: int, target_level: int, available_gold: int, available_shards: int, level_costs: dict | list[dict]) -> dict[str, int]:
    validate_level_range(current_level, target_level)
    table, is_placeholder = normalize_level_cost_table(level_costs)
    used_gold = 0
    used_shards = 0
    max_feasible_level = int(current_level)
    next_missing_gold = 0
    next_missing_shards = 0

    for level in range(int(current_level) + 1, int(target_level) + 1):
        cost = _cost_for_level(table, is_placeholder, level)
        projected_gold = used_gold + cost.gold
        projected_shards = used_shards + cost.shards
        if projected_gold <= int(available_gold) and projected_shards <= int(available_shards):
            used_gold = projected_gold
            used_shards = projected_shards
            max_feasible_level = level
            continue
        next_missing_gold = max(projected_gold - int(available_gold), 0)
        next_missing_shards = max(projected_shards - int(available_shards), 0)
        break

    return {
        "max_feasible_level": max_feasible_level,
        "jump_levels": max_feasible_level - int(current_level),
        "used_gold": used_gold,
        "used_shards": used_shards,
        "remaining_gold": max(int(available_gold) - used_gold, 0),
        "remaining_shards": max(int(available_shards) - used_shards, 0),
        "next_missing_gold": next_missing_gold,
        "next_missing_shards": next_missing_shards,
    }


def estimate_days_needed(missing_gold: int, daily_gold_earning: int) -> int:
    if int(missing_gold) <= 0:
        return 0
    if int(daily_gold_earning) <= 0:
        raise ValueError("Daily gold earning assumption must be greater than zero.")
    return (int(missing_gold) + int(daily_gold_earning) - 1) // int(daily_gold_earning)
