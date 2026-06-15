from __future__ import annotations

import unittest

from services.account_display import account_display_lookup, account_display_name
from services.export_service import export_csv_reports


class FakeStore:
    def __init__(self) -> None:
        self.files = {
            "accounts.json": [
                {
                    "account_id": "acct_1",
                    "account_name": "incheon",
                    "wallet_address": "0x1111111111111111111111111111111111111111",
                    "active": True,
                    "note": "firm",
                }
            ],
            "tickets.json": [{"account_id": "acct_1", "ticket_price_usdt": 1.0}],
            "resource_snapshots.json": [{"account_id": "acct_1", "gold": 100, "shards": 10, "wf": 1.5}],
            "daily_actions.json": [{"account_id": "acct_1", "action_date": "2026-06-15", "pve_done": True}],
        }
        self.reports: dict[str, str] = {}

    def load_json(self, filename: str, default: list | None = None) -> list:
        return list(self.files.get(filename, default or []))

    def save_report_text(self, filename: str, content: str) -> str:
        self.reports[filename] = content
        return filename


class AccountDisplayTest(unittest.TestCase):
    def test_account_display_uses_note_label(self) -> None:
        self.assertEqual(account_display_name({"account_name": "incheon", "note": "firm"}), "incheon (firm)")

    def test_blank_note_falls_back_to_account_name(self) -> None:
        self.assertEqual(account_display_name({"account_name": "incheon", "note": "  "}), "incheon")

    def test_lookup_keeps_account_id_as_key(self) -> None:
        labels = account_display_lookup([{"account_id": "acct_1", "account_name": "incheon", "note": "firm"}])
        self.assertEqual(labels, {"acct_1": "incheon (firm)"})
        self.assertNotIn("incheon (firm)", labels)

    def test_exports_include_display_column_without_replacing_account_id(self) -> None:
        store = FakeStore()
        report_paths = export_csv_reports(store)

        self.assertIn("accounts.csv", report_paths)
        self.assertIn("account_display,account_id,account_name", store.reports["accounts.csv"])
        self.assertIn("incheon (firm),acct_1,incheon", store.reports["accounts.csv"])
        self.assertIn("account_display,account_id,ticket_price_usdt", store.reports["tickets.csv"])
        self.assertIn("incheon (firm),acct_1,1.0", store.reports["tickets.csv"])


if __name__ == "__main__":
    unittest.main()
