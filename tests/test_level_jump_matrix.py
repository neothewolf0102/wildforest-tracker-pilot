from __future__ import annotations

import unittest

from services.level_service import build_account_jump_matrix, build_multi_account_upgrade_plan


LEVEL_CONFIG = {
    "placeholder": False,
    "level_costs": [
        {"level": 2, "gold": 100, "shards": 10},
        {"level": 3, "gold": 200, "shards": 20},
        {"level": 4, "gold": 300, "shards": 30},
    ],
}

ACCOUNTS = [
    {"account_id": "a1", "account_name": "Ready", "active": True},
    {"account_id": "a2", "account_name": "Partial", "active": True},
    {"account_id": "a3", "account_name": "Empty", "active": True},
]


class LevelJumpMatrixTest(unittest.TestCase):
    def test_ready_account_can_reach_target_and_sorts_first(self) -> None:
        snapshots = [
            {"account_id": "a1", "gold": 600, "shards": 60},
            {"account_id": "a2", "gold": 250, "shards": 25},
        ]
        matrix = build_account_jump_matrix(ACCOUNTS, snapshots, "Rogue", 1, 4, LEVEL_CONFIG)
        self.assertEqual(matrix["ready_accounts"], 1)
        self.assertEqual(matrix["best_account"], "Ready")
        self.assertEqual(matrix["rows"][0]["Can Reach Target"], "Yes")
        self.assertEqual(matrix["rows"][0]["Max Jump Level"], 4)

    def test_partial_account_reports_max_feasible_level(self) -> None:
        snapshots = [{"account_id": "a2", "gold": 250, "shards": 25}]
        matrix = build_account_jump_matrix([ACCOUNTS[1]], snapshots, "Rogue", 1, 4, LEVEL_CONFIG)
        row = matrix["rows"][0]
        self.assertEqual(row["Can Reach Target"], "No")
        self.assertEqual(row["Max Jump Level"], 2)
        self.assertEqual(row["Status"], "Partial jump available")

    def test_account_without_snapshot_has_clear_status(self) -> None:
        matrix = build_account_jump_matrix([ACCOUNTS[2]], [], "Rogue", 1, 4, LEVEL_CONFIG)
        row = matrix["rows"][0]
        self.assertEqual(row["Max Jump Level"], 1)
        self.assertIn("No resource snapshot found", row["Status"])

    def test_multi_account_plan_outputs_moves_and_detail(self) -> None:
        snapshots = [
            {"account_id": "a1", "gold": 300, "shards": 30, "wf": 10},
            {"account_id": "a2", "gold": 300, "shards": 30, "wf": 5},
        ]
        plan = build_multi_account_upgrade_plan(
            ACCOUNTS[:2],
            snapshots,
            [{"unit_name": "Rogue", "current_level": 1, "target_level": 4}],
            LEVEL_CONFIG,
            mode="Best Fit / Least Waste",
        )
        self.assertEqual(plan["summary"]["required_shards"], 60)
        self.assertEqual(plan["summary"]["required_golds"], 600)
        self.assertTrue(plan["summary"]["enough_resource"])
        self.assertGreaterEqual(len(plan["recommended_moves"]), 1)
        self.assertEqual(len(plan["allocation_detail"]), 3)
        self.assertEqual(plan["unit_summary"][0]["Max Reached"], 4)


if __name__ == "__main__":
    unittest.main()
