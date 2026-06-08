from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class LevelPlan:
    account_id: str
    unit_name: str
    current_level: int
    target_level: int
    required_gold: int
    required_shards: int
    available_gold: int
    available_shards: int
    missing_gold: int
    missing_shards: int
    can_upgrade_now: bool
    estimated_days_needed: int
    earning_assumption: str
    uses_placeholder_costs: bool = False

    def to_dict(self) -> dict:
        return asdict(self)
