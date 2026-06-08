from __future__ import annotations

import unittest

from engines.level_cost_engine import MISSING_LEVEL_COST_MESSAGE, MissingLevelCostConfigurationError
from services.level_service import NO_RESOURCE_SNAPSHOT_MESSAGE, NoResourceSnapshotError, build_level_plan


class FakeStore:
    def __init__(self, snapshots: list[dict] | None = None) -> None:
        self.snapshots = snapshots or []

    def load_json(self, filename: str, default: list | None = None) -> list:
        if filename == "resource_snapshots.json":
            return list(self.snapshots)
        return list(default or [])


TEST_COSTS = {
    "placeholder": False,
    "level_costs": [
        {"level": 2, "gold": 100, "shards": 5},
        {"level": 3, "gold": 200, "shards": 10},
    ],
}


class LevelPlannerTest(unittest.TestCase):
    def test_enough_resources(self) -> None:
        plan = build_level_plan(FakeStore([{"account_id": "acct_1", "gold": 500, "shards": 30}]), "acct_1", "Archer", 1, 3, TEST_COSTS)
        self.assertTrue(plan.can_upgrade_now)
        self.assertEqual(plan.required_gold, 300)
        self.assertEqual(plan.required_shards, 15)

    def test_missing_gold(self) -> None:
        plan = build_level_plan(FakeStore([{"account_id": "acct_1", "gold": 250, "shards": 30}]), "acct_1", "Archer", 1, 3, TEST_COSTS)
        self.assertFalse(plan.can_upgrade_now)
        self.assertEqual(plan.missing_gold, 50)
        self.assertEqual(plan.missing_shards, 0)

    def test_missing_shards(self) -> None:
        plan = build_level_plan(FakeStore([{"account_id": "acct_1", "gold": 500, "shards": 10}]), "acct_1", "Archer", 1, 3, TEST_COSTS)
        self.assertFalse(plan.can_upgrade_now)
        self.assertEqual(plan.missing_gold, 0)
        self.assertEqual(plan.missing_shards, 5)

    def test_target_level_must_be_greater_than_current_level(self) -> None:
        with self.assertRaisesRegex(ValueError, "Target level must be greater"):
            build_level_plan(FakeStore([{"account_id": "acct_1", "gold": 500, "shards": 30}]), "acct_1", "Archer", 3, 3, TEST_COSTS)

    def test_account_with_no_resource_snapshot(self) -> None:
        with self.assertRaisesRegex(NoResourceSnapshotError, NO_RESOURCE_SNAPSHOT_MESSAGE):
            build_level_plan(FakeStore(), "acct_1", "Archer", 1, 3, TEST_COSTS)

    def test_missing_level_cost_configuration(self) -> None:
        with self.assertRaisesRegex(MissingLevelCostConfigurationError, MISSING_LEVEL_COST_MESSAGE):
            build_level_plan(FakeStore([{"account_id": "acct_1", "gold": 500, "shards": 30}]), "acct_1", "Archer", 1, 4, TEST_COSTS)


if __name__ == "__main__":
    unittest.main()
