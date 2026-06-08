from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class Ticket:
    account_id: str
    ticket_purchase_date: str
    ticket_expiry_date: str
    ticket_price_usdt: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)
