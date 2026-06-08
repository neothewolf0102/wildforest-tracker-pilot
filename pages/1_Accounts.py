from __future__ import annotations

import pandas as pd
import streamlit as st

from services.account_service import ACCOUNT_LIMIT_MESSAGE, MAX_ACCOUNTS_PER_USER, load_accounts, upsert_account
from ui.pilot_auth import current_store, render_login_gate, render_user_bar

st.set_page_config(page_title="Accounts | Wildforest Tracker", page_icon="👤", layout="wide")

if not render_login_gate():
    st.stop()
render_user_bar()

st.title("Accounts")
st.caption("Add wallet/account records. Pilot 01 allows up to five accounts per Google user.")

store = current_store()
accounts = load_accounts(store)
account_count = len(accounts)
st.metric("Pilot account capacity", f"{account_count}/{MAX_ACCOUNTS_PER_USER}")
if account_count >= MAX_ACCOUNTS_PER_USER:
    st.warning(ACCOUNT_LIMIT_MESSAGE)

with st.form("account_form"):
    account_name = st.text_input("Account name")
    wallet_address = st.text_input("Wallet address")
    active = st.checkbox("Active", value=True)
    note = st.text_input("Note")
    submitted = st.form_submit_button("Save account", type="primary", disabled=account_count >= MAX_ACCOUNTS_PER_USER)
    if submitted:
        try:
            upsert_account(store, account_name, wallet_address, active, note)
            st.success("Account saved.")
            st.rerun()
        except Exception as error:
            st.error(f"Save failed: {error}")

if accounts:
    st.dataframe(pd.DataFrame(accounts), use_container_width=True, hide_index=True)
else:
    st.info("No accounts yet.")
