from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from services.account_service import active_accounts, load_accounts
from services.daily_action_service import load_daily_actions, upsert_daily_action
from ui.pilot_auth import current_store, render_login_gate, render_user_bar

st.set_page_config(page_title="Daily Actions | Wildforest Tracker", page_icon="✅", layout="wide")

if not render_login_gate():
    st.stop()
render_user_bar()

st.title("Daily Action Checklist")
st.caption("Track PvE, Signal Fire, and Bounty Hunter per account.")

store = current_store()
accounts = active_accounts(load_accounts(store))
actions = load_daily_actions(store)

if not accounts:
    st.warning("Add an active account first.")
    st.stop()

selected_date = st.date_input("Date", value=date.today()).isoformat()
account_options = {item["account_name"]: item["account_id"] for item in accounts}
with st.form("daily_action_form"):
    account_name = st.selectbox("Account", list(account_options.keys()))
    pve_done = st.checkbox("PvE done")
    signal_fire_done = st.checkbox("Signal Fire done")
    bounty_hunter_done = st.checkbox("Bounty Hunter done")
    note = st.text_input("Note")
    submitted = st.form_submit_button("Save daily action", type="primary")
    if submitted:
        upsert_daily_action(store, account_options[account_name], selected_date, pve_done, signal_fire_done, bounty_hunter_done, note)
        st.success("Daily action saved.")
        st.rerun()

name_by_id = {item["account_id"]: item["account_name"] for item in accounts}
rows = [{"Date": item.get("action_date", ""), "Account": name_by_id.get(item.get("account_id"), item.get("account_id", "")), "PvE": item.get("pve_done", False), "Signal Fire": item.get("signal_fire_done", False), "Bounty Hunter": item.get("bounty_hunter_done", False), "Note": item.get("note", "")} for item in actions]
st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
