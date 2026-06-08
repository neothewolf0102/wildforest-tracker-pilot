from __future__ import annotations

import streamlit as st

from services.account_service import MAX_ACCOUNTS_PER_USER, load_accounts
from services.daily_action_service import load_daily_actions
from services.kpi_service import build_kpi_summary
from services.resource_service import load_resource_snapshots
from services.ticket_service import load_tickets
from ui.pilot_auth import current_store, render_login_gate, render_user_bar

st.set_page_config(page_title="Wildforest Tracker Pilot 01", page_icon="🌲", layout="wide")

if not render_login_gate():
    st.stop()
render_user_bar()

st.title("Wildforest Tracker Pilot 01")
st.caption("Web pilot dashboard. Data is isolated per Google account and prepared for that user's Google Drive storage.")

store = current_store()
accounts = load_accounts(store)
tickets = load_tickets(store)
snapshots = load_resource_snapshots(store)
daily_actions = load_daily_actions(store)
summary = build_kpi_summary(accounts, tickets, snapshots, daily_actions)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Active Accounts", summary["active_accounts"])
col2.metric("Account Capacity", f"{len(accounts)}/{MAX_ACCOUNTS_PER_USER}")
col3.metric("Gold", f"{summary['total_gold']:,}")
col4.metric("Shards", f"{summary['total_shards']:,}")

col5, col6, col7, col8 = st.columns(4)
col5.metric("WF", f"{summary['total_wf']:,.2f}")
col6.metric("Valid Tickets", summary["valid_tickets"])
col7.metric("Daily Completion", f"{summary['daily_completion_rate']:.2f}%")
col8.metric("Simple ROI", f"{summary['simple_roi_usdt']:.2f} USDT", summary["roi_status"])

st.info("Use the sidebar pages for Accounts, Tickets, Resources, Daily Actions, and KPI Dashboard.")

with st.expander("Pilot scope"):
    st.write(
        "- Enabled: Google login gate, accounts, tickets, manual resources, daily checklist, KPI/ROI, export.\n"
        "- Pilot 01 capacity: 4 Google test users operationally, up to 5 Wildforest accounts per user.\n"
        "- Hidden for Pilot 01: OCR, Level Simulation, AI Assistant, Payment, Admin dashboard."
    )
