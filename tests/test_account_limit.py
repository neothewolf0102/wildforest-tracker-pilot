from __future__ import annotations

import unittest

from services.account_service import (
    ACCOUNT_LIMIT_MESSAGE,
    DUPLICATE_ACCOUNT_NAME_MESSAGE,
    DUPLICATE_WALLET_MESSAGE,
    MAX_ACCOUNTS_PER_USER,
    delete_account,
    upsert_account,
)


class FakeStore:
    def __init__(self) -> None:
        self.files: dict[str, list[dict]] = {}

    def load_json(self, filename: str, default: list | None = None) -> list:
        return list(self.files.get(filename, default or []))

    def save_json(self, filename: str, data: list[dict]) -> None:
        self.files[filename] = list(data)


class AccountLimitTest(unittest.TestCase):
    def test_user_can_create_up_to_five_accounts(self) -> None:
        store = FakeStore()
        for index in range(MAX_ACCOUNTS_PER_USER):
            upsert_account(store, f"Account {index + 1}", f"0x{index + 1:040d}")
        self.assertEqual(len(store.files["accounts.json"]), MAX_ACCOUNTS_PER_USER)

    def test_sixth_account_is_blocked_with_required_message(self) -> None:
        store = FakeStore()
        for index in range(MAX_ACCOUNTS_PER_USER):
            upsert_account(store, f"Account {index + 1}", f"0x{index + 1:040d}")
        with self.assertRaisesRegex(ValueError, ACCOUNT_LIMIT_MESSAGE):
            upsert_account(store, "Account 6", "0x9999999999999999999999999999999999999999")

    def test_duplicate_account_name_is_blocked(self) -> None:
        store = FakeStore()
        upsert_account(store, "Main", "0x1111111111111111111111111111111111111111")
        with self.assertRaisesRegex(ValueError, DUPLICATE_ACCOUNT_NAME_MESSAGE):
            upsert_account(store, "main", "0x2222222222222222222222222222222222222222")

    def test_duplicate_wallet_is_blocked(self) -> None:
        store = FakeStore()
        upsert_account(store, "Main", "0x1111111111111111111111111111111111111111")
        with self.assertRaisesRegex(ValueError, DUPLICATE_WALLET_MESSAGE):
            upsert_account(store, "Alt", "0x1111111111111111111111111111111111111111")

    def test_wallet_address_is_required(self) -> None:
        store = FakeStore()
        with self.assertRaisesRegex(ValueError, "Wallet address is required"):
            upsert_account(store, "Main", "")

    def test_can_delete_selected_account(self) -> None:
        store = FakeStore()
        account = upsert_account(store, "Main", "0x1111111111111111111111111111111111111111")
        self.assertTrue(delete_account(store, account["account_id"]))
        self.assertEqual(store.files["accounts.json"], [])

    def test_delete_missing_account_is_safe_noop(self) -> None:
        store = FakeStore()
        upsert_account(store, "Main", "0x1111111111111111111111111111111111111111")
        self.assertFalse(delete_account(store, "missing-account-id"))
        self.assertEqual(len(store.files["accounts.json"]), 1)


if __name__ == "__main__":
    unittest.main()
