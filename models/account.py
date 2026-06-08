from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class Account:
    account_id: str
    account_name: str
    wallet_address: str
    active: bool = True
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)
