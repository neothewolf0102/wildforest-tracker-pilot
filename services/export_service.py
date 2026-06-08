from __future__ import annotations

import io

import pandas as pd

from services.account_service import load_accounts
from services.daily_action_service import load_daily_actions
from services.resource_service import load_resource_snapshots
from services.ticket_service import load_tickets


def export_csv_reports(store) -> list[str]:
    datasets = {
        "accounts.csv": load_accounts(store),
        "tickets.csv": load_tickets(store),
        "resource_snapshots.csv": load_resource_snapshots(store),
        "daily_actions.csv": load_daily_actions(store),
    }
    return [store.save_report_text(filename, pd.DataFrame(rows).to_csv(index=False)) for filename, rows in datasets.items()]


def export_excel_report(store) -> str:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(load_accounts(store)).to_excel(writer, sheet_name="Accounts", index=False)
        pd.DataFrame(load_tickets(store)).to_excel(writer, sheet_name="Tickets", index=False)
        pd.DataFrame(load_resource_snapshots(store)).to_excel(writer, sheet_name="Resources", index=False)
        pd.DataFrame(load_daily_actions(store)).to_excel(writer, sheet_name="Daily Actions", index=False)
    return store.save_report_bytes("wildforest_tracker_report.xlsx", output.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
