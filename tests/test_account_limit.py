from __future__ import annotations

import unittest

from services.account_service import ACCOUNT_LIMIT_MESSAGE, MAX_ACCOUNTS_PER_USER, upsert_account


class FakeStore:
    def __init__(self) -> None:
        self.files: dict[str, list[dict]] = {}

    def load_json(self, filename: str, default: list | None = None) -> list:
        return list(self.files.get(filename, default or []))

    def save_json(self, filename: str, data: list[dict]) -> None:
        self.files[filename] = list(data)


class AccountLimitTest(unittest.TestCase):
    def test_user_can_create_up_to_max_accounts(self) -> None:
        store = FakeStore()
        for index in range(MAX_ACCOUNTS_PER_USER):
            upsert_account(store, f"Account {index + 1}", f"0x{index + 1:040d}")
        self.assertEqual(len(store.files["accounts.json"]), MAX_ACCOUNTS_PER_USER)
        self.assertEqual(MAX_ACCOUNTS_PER_USER, 10)

    def test_next_account_is_blocked_with_required_message(self) -> None:
        store = FakeStore()
        for index in range(MAX_ACCOUNTS_PER_USER):
            upsert_account(store, f"Account {index + 1}", f"0x{index + 1:040d}")
        with self.assertRaisesRegex(ValueError, ACCOUNT_LIMIT_MESSAGE):
            upsert_account(store, "Account 11", "0x9999999999999999999999999999999999999999")


if __name__ == "__main__":
    unittest.main()
