from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class DailyAction:
    account_id: str
    action_date: str
    pve_done: bool = False
    signal_fire_done: bool = False
    bounty_hunter_done: bool = False
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)
