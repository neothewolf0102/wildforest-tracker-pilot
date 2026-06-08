from __future__ import annotations

import pandas as pd
import streamlit as st

from services.account_service import load_accounts
from services.daily_action_service import load_daily_actions
from services.export_service import export_csv_reports, export_excel_report
from services.kpi_service import build_kpi_summary
from services.resource_service import load_resource_snapshots
from services.ticket_service import load_tickets
from ui.pilot_auth import current_store, render_login_gate, render_user_bar

st.set_page_config(page_title="KPI Dashboard | Wildforest Tracker", page_icon="📊", layout="wide")

if not render_login_gate():
    st.stop()
render_user_bar()

st.title("Basic KPI / ROI Dashboard")
st.caption("Pilot 01 dashboard. ROI is simple estimated WF value minus ticket cost.")

store = current_store()
accounts = load_accounts(store)
tickets = load_tickets(store)
snapshots = load_resource_snapshots(store)
daily_actions = load_daily_actions(store)
wf_price = st.number_input("Manual WF price USDT", min_value=0.0, value=0.0, step=0.0001, format="%.6f")
summary = build_kpi_summary(accounts, tickets, snapshots, daily_actions, wf_price)

cols = st.columns(4)
cols[0].metric("Active Accounts", summary["active_accounts"])
cols[1].metric("Valid Tickets", summary["valid_tickets"])
cols[2].metric("Ticket Cost", f"{summary['ticket_cost_usdt']:.2f} USDT")
cols[3].metric("Daily Completion", f"{summary['daily_completion_rate']:.2f}%")

cols = st.columns(4)
cols[0].metric("Gold", f"{summary['total_gold']:,}")
cols[1].metric("Shards", f"{summary['total_shards']:,}")
cols[2].metric("WF", f"{summary['total_wf']:,.2f}")
cols[3].metric("Simple ROI", f"{summary['simple_roi_usdt']:.2f} USDT", summary["roi_status"])

with st.expander("Data preview"):
    st.dataframe(pd.DataFrame(accounts), use_container_width=True)
    st.dataframe(pd.DataFrame(tickets), use_container_width=True)
    st.dataframe(pd.DataFrame(snapshots), use_container_width=True)
    st.dataframe(pd.DataFrame(daily_actions), use_container_width=True)

st.subheader("Export")
left, right = st.columns(2)
with left:
    if st.button("Export CSV reports", type="primary"):
        st.success(f"CSV reports exported. Files: {len(export_csv_reports(store))}")
with right:
    if st.button("Export Excel report"):
        export_excel_report(store)
        st.success("Excel report exported.")
