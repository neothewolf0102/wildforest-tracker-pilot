from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from services.account_service import load_accounts, upsert_account
from services.resource_service import latest_snapshot_by_account, load_resource_snapshots
from services.telegram_sync_service import (
    ACTION_CREATE,
    ACTION_SKIP_LIMIT,
    ACTION_UNCHANGED,
    ACTION_UPDATE,
    TelegramSyncError,
    apply_telegram_import,
    fetch_bot_accounts,
    load_link_code,
    plan_telegram_import,
    save_link_code,
)


class FakeStore:
    def __init__(self) -> None:
        self.files: dict[str, list[dict]] = {}
        self.saves: list[str] = []

    def load_json(self, filename: str, default: list | None = None) -> list:
        return json.loads(json.dumps(self.files.get(filename, default or [])))

    def save_json(self, filename: str, data: list[dict]) -> None:
        self.saves.append(filename)
        self.files[filename] = json.loads(json.dumps(data))


def preview(store: FakeStore, bot_accounts: list[dict], max_new: int | None = None) -> list[dict]:
    accounts = load_accounts(store)
    snapshots = latest_snapshot_by_account(load_resource_snapshots(store))
    return plan_telegram_import(accounts, snapshots, bot_accounts, max_new)


class TelegramSyncPlanTest(unittest.TestCase):
    def setUp(self) -> None:
        self.store = FakeStore()
        upsert_account(self.store, "Moo", "0x0909eabCE8e59dC2C79E6565017453c9793C5C28", note="0330")
        moo_id = load_accounts(self.store)[0]["account_id"]
        self.store.files["resource_snapshots.json"] = [
            {"account_id": moo_id, "snapshot_datetime": "2026-06-01T00:00:00+00:00", "shards": 100, "gold": 5000, "wf": 12.5}
        ]

    def test_new_account_created_with_blank_wallet_and_existing_matched_by_name(self) -> None:
        rows = preview(self.store, [
            {"name": "moo", "shards": 1607, "gold": 89230},
            {"name": "Higg.", "shards": 3511, "gold": None},
        ])
        self.assertEqual([r["action"] for r in rows], [ACTION_UPDATE, ACTION_CREATE])
        result = apply_telegram_import(self.store, rows)
        self.assertEqual(result, {"created": 1, "updated": 1})

        accounts = {a["account_name"]: a for a in load_accounts(self.store)}
        self.assertEqual(accounts["Higg."]["wallet_address"], "")
        self.assertEqual(accounts["Higg."]["source"], "telegram")
        self.assertEqual(accounts["Moo"]["telegram_name"], "moo")
        self.assertEqual(accounts["Moo"]["wallet_address"], "0x0909eabCE8e59dC2C79E6565017453c9793C5C28")

        latest = latest_snapshot_by_account(load_resource_snapshots(self.store))
        moo = latest[accounts["Moo"]["account_id"]]
        self.assertEqual((moo["shards"], moo["gold"], moo["wf"], moo["source"]), (1607, 89230, 12.5, "telegram"))
        higg = latest[accounts["Higg."]["account_id"]]
        self.assertEqual((higg["shards"], higg["gold"], higg["wf"]), (3511, 0, 0.0))

    def test_single_write_per_file(self) -> None:
        rows = preview(self.store, [{"name": f"A{i}", "shards": i, "gold": i} for i in range(6)])
        self.store.saves.clear()
        apply_telegram_import(self.store, rows)
        self.assertEqual(sorted(self.store.saves), ["accounts.json", "resource_snapshots.json"])

    def test_second_sync_is_unchanged(self) -> None:
        bot = [{"name": "Moo", "shards": 1607, "gold": 89230}]
        apply_telegram_import(self.store, preview(self.store, bot))
        rows = preview(self.store, bot)
        self.assertEqual(rows[0]["action"], ACTION_UNCHANGED)

    def test_null_gold_keeps_webapp_gold(self) -> None:
        rows = preview(self.store, [{"name": "Moo", "shards": 900, "gold": None}])
        self.assertEqual((rows[0]["gold_old"], rows[0]["gold_new"]), (5000, 5000))

    def test_renamed_webapp_account_still_matches_by_telegram_name(self) -> None:
        apply_telegram_import(self.store, preview(self.store, [{"name": "Moo", "shards": 200, "gold": 1}]))
        account = load_accounts(self.store)[0]
        upsert_account(self.store, "Moo main", account["wallet_address"], account_id=account["account_id"])
        rows = preview(self.store, [{"name": "Moo", "shards": 300, "gold": 1}])
        self.assertEqual(rows[0]["action"], ACTION_UPDATE)
        self.assertEqual(rows[0]["account_name"], "Moo main")

    def test_account_limit_respected_for_non_admin(self) -> None:
        rows = preview(self.store, [{"name": f"N{i}", "shards": 1, "gold": 1} for i in range(3)], max_new=2)
        self.assertEqual([r["action"] for r in rows], [ACTION_CREATE, ACTION_CREATE, ACTION_SKIP_LIMIT])
        apply_telegram_import(self.store, rows)
        self.assertEqual(len(load_accounts(self.store)), 3)

    def test_link_code_roundtrip(self) -> None:
        self.assertEqual(load_link_code(self.store), "")
        save_link_code(self.store, " WF-ABC ")
        self.assertEqual(load_link_code(self.store), "WF-ABC")


class AccountServiceCompatTest(unittest.TestCase):
    def test_edit_keeps_telegram_fields_and_allows_blank_wallet(self) -> None:
        store = FakeStore()
        apply_telegram_import(store, plan_telegram_import([], {}, [{"name": "Zed", "shards": 1, "gold": 1}], None))
        account = load_accounts(store)[0]
        upsert_account(store, "Zed", "", note="alt", account_id=account["account_id"], allow_blank_wallet=True)
        edited = load_accounts(store)[0]
        self.assertEqual((edited["source"], edited["telegram_name"], edited["note"]), ("telegram", "Zed", "alt"))

    def test_manual_account_still_requires_wallet(self) -> None:
        with self.assertRaisesRegex(ValueError, "Wallet address is required."):
            upsert_account(FakeStore(), "Manual", "")


class _BotHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.headers.get("Authorization") != "Bearer WF-GOOD":
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b'{"error":"invalid_code"}')
            return
        body = json.dumps({"accounts": [{"name": "Moo", "shards": 1, "gold": None}, {"name": " ", "shards": 2}]}).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:
        pass


class FetchBotAccountsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = HTTPServer(("127.0.0.1", 0), _BotHandler)
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()

    def test_good_code(self) -> None:
        self.assertEqual(fetch_bot_accounts(self.url, "WF-GOOD"), [{"name": "Moo", "shards": 1, "gold": None}])

    def test_bad_code(self) -> None:
        with self.assertRaisesRegex(TelegramSyncError, "/lienket"):
            fetch_bot_accounts(self.url, "WF-BAD")

    def test_empty_code(self) -> None:
        with self.assertRaisesRegex(TelegramSyncError, "Chưa nhập"):
            fetch_bot_accounts(self.url, "")


if __name__ == "__main__":
    unittest.main()
