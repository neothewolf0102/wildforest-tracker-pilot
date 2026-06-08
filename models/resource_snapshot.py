from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class ResourceSnapshot:
    account_id: str
    snapshot_datetime: str
    gold: int = 0
    shards: int = 0
    wf: float = 0.0
    source: str = "manual"
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)
