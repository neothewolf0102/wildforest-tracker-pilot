from __future__ import annotations

import pandas as pd
import streamlit as st

from services.account_service import active_accounts, load_accounts
from services.resource_service import latest_snapshot_by_account, load_resource_snapshots, upsert_manual_resource_snapshot
from ui.pilot_auth import current_store, render_login_gate, render_user_bar

st.set_page_config(page_title="Resources | Wildforest Tracker", page_icon="💰", layout="wide")

if not render_login_gate():
    st.stop()
render_user_bar()

st.title("Manual Resource Snapshot")
st.caption("Pilot 01 uses manual gold, shards, and WF input. OCR is locked for this pilot.")

store = current_store()
accounts = active_accounts(load_accounts(store))
snapshots = load_resource_snapshots(store)
snapshot_map = latest_snapshot_by_account(snapshots)

if not accounts:
    st.warning("Add an active account first.")
    st.stop()

account_options = {item["account_name"]: item["account_id"] for item in accounts}
with st.form("resource_form"):
    account_name = st.selectbox("Account", list(account_options.keys()))
    gold = st.number_input("Gold", min_value=0, step=1)
    shards = st.number_input("Shards", min_value=0, step=1)
    wf = st.number_input("WF", min_value=0.0, step=0.01, format="%.2f")
    note = st.text_input("Note")
    submitted = st.form_submit_button("Save resource snapshot", type="primary")
    if submitted:
        upsert_manual_resource_snapshot(store, account_options[account_name], int(gold), int(shards), float(wf), note)
        st.success("Resource snapshot saved.")
        st.rerun()

rows = []
for account in accounts:
    snapshot = snapshot_map.get(str(account.get("account_id")), {})
    rows.append({"Account": account.get("account_name", ""), "Gold": snapshot.get("gold", 0), "Shards": snapshot.get("shards", 0), "WF": snapshot.get("wf", 0.0), "Updated": snapshot.get("snapshot_datetime", ""), "Note": snapshot.get("note", "")})
st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
