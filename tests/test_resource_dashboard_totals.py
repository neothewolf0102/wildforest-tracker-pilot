from __future__ import annotations

import unittest

from services.resource_service import latest_snapshot_by_account


def dashboard_totals_for_current_accounts(accounts: list[dict], snapshots: list[dict]) -> dict[str, float]:
    snapshot_map = latest_snapshot_by_account(snapshots)
    current_account_ids = {str(account.get("account_id", "") or "") for account in accounts}
    current_latest_snapshots = [
        snapshot_map[account_id]
        for account_id in current_account_ids
        if account_id in snapshot_map
    ]
    return {
        "gold": sum(int(snapshot.get("gold", snapshot.get("gold_balance", 0)) or 0) for snapshot in current_latest_snapshots),
        "shards": sum(int(snapshot.get("shards", snapshot.get("wild_shards_balance", 0)) or 0) for snapshot in current_latest_snapshots),
        "wf": sum(float(snapshot.get("wf", snapshot.get("wf_balance", 0.0)) or 0.0) for snapshot in current_latest_snapshots),
    }


class ResourceDashboardTotalsTest(unittest.TestCase):
    def test_latest_snapshot_uses_newest_timestamp_per_account(self) -> None:
        snapshots = [
            {"account_id": "a1", "snapshot_datetime": "2026-06-14T10:00:00+00:00", "gold": 500, "shards": 50, "wf": 5.5},
            {"account_id": "a1", "snapshot_datetime": "2026-06-14T09:00:00+00:00", "gold": 100, "shards": 10, "wf": 1.0},
        ]
        latest = latest_snapshot_by_account(snapshots)
        self.assertEqual(latest["a1"]["gold"], 500)

    def test_dashboard_totals_use_latest_snapshot_per_current_account_only(self) -> None:
        accounts = [{"account_id": "a1"}, {"account_id": "a2"}]
        snapshots = [
            {"account_id": "a1", "snapshot_datetime": "2026-06-14T08:00:00+00:00", "gold": 100, "shards": 10, "wf": 1.0},
            {"account_id": "a1", "snapshot_datetime": "2026-06-14T10:00:00+00:00", "gold": 300, "shards": 30, "wf": 3.5},
            {"account_id": "a2", "snapshot_datetime": "2026-06-14T09:00:00+00:00", "gold_balance": 200, "wild_shards_balance": 20, "wf_balance": 2.25},
            {"account_id": "deleted", "snapshot_datetime": "2026-06-14T11:00:00+00:00", "gold": 999, "shards": 999, "wf": 99.0},
        ]
        totals = dashboard_totals_for_current_accounts(accounts, snapshots)
        self.assertEqual(totals["gold"], 500)
        self.assertEqual(totals["shards"], 50)
        self.assertEqual(totals["wf"], 5.75)


if __name__ == "__main__":
    unittest.main()
