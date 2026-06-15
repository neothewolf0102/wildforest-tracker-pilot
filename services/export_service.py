from __future__ import annotations

import io

import pandas as pd

from services.account_display import account_display_lookup, account_display_name
from services.account_service import load_accounts
from services.daily_action_service import load_daily_actions
from services.resource_service import load_resource_snapshots
from services.ticket_service import load_tickets

ACCOUNT_DISPLAY_COLUMN = "account_display"


def _accounts_frame(accounts: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(accounts)
    if not frame.empty:
        frame.insert(0, ACCOUNT_DISPLAY_COLUMN, [account_display_name(account) for account in accounts])
    return frame


def _with_account_display(rows: list[dict], display_by_id: dict[str, str]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    if not frame.empty and "account_id" in frame.columns:
        labels = frame["account_id"].map(lambda value: display_by_id.get(str(value), str(value or "")))
        frame.insert(0, ACCOUNT_DISPLAY_COLUMN, labels)
    return frame


def export_csv_reports(store) -> list[str]:
    accounts = load_accounts(store)
    display_by_id = account_display_lookup(accounts)
    datasets = {
        "accounts.csv": _accounts_frame(accounts),
        "tickets.csv": _with_account_display(load_tickets(store), display_by_id),
        "resource_snapshots.csv": _with_account_display(load_resource_snapshots(store), display_by_id),
        "daily_actions.csv": _with_account_display(load_daily_actions(store), display_by_id),
    }
    return [store.save_report_text(filename, frame.to_csv(index=False)) for filename, frame in datasets.items()]


def export_excel_report(store) -> str:
    accounts = load_accounts(store)
    display_by_id = account_display_lookup(accounts)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        _accounts_frame(accounts).to_excel(writer, sheet_name="Accounts", index=False)
        _with_account_display(load_tickets(store), display_by_id).to_excel(writer, sheet_name="Tickets", index=False)
        _with_account_display(load_resource_snapshots(store), display_by_id).to_excel(writer, sheet_name="Resources", index=False)
        _with_account_display(load_daily_actions(store), display_by_id).to_excel(writer, sheet_name="Daily Actions", index=False)
    return store.save_report_bytes("wildforest_tracker_report.xlsx", output.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
