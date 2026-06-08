from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from engines.ticket_engine import DEFAULT_TICKET_DURATION_DAYS, days_until_expiry, ticket_status
from services.account_service import active_accounts, load_accounts
from services.ticket_service import load_tickets, ticket_by_account, upsert_ticket
from ui.pilot_auth import current_store, render_login_gate, render_user_bar

st.set_page_config(page_title="Tickets | Wildforest Tracker", page_icon="🎟️", layout="wide")

if not render_login_gate():
    st.stop()
render_user_bar()

st.title("Ticket Tracking")
st.caption("Ticket duration defaults to 14 days. One current ticket state per account.")

store = current_store()
accounts = active_accounts(load_accounts(store))
tickets = load_tickets(store)
tickets_by_account = ticket_by_account(tickets)

if not accounts:
    st.warning("Add an active account first.")
    st.stop()

account_options = {item["account_name"]: item["account_id"] for item in accounts}
with st.form("ticket_form"):
    account_name = st.selectbox("Account", list(account_options.keys()))
    purchase_date = st.date_input("Ticket purchase date", value=date.today())
    ticket_price = st.number_input("Ticket price USDT", min_value=0.0, value=1.0, step=0.5, format="%.2f")
    submitted = st.form_submit_button("Save ticket", type="primary")
    if submitted:
        upsert_ticket(store, account_options[account_name], purchase_date, ticket_price, DEFAULT_TICKET_DURATION_DAYS)
        st.success("Ticket saved.")
        st.rerun()

rows = []
for account in accounts:
    ticket = tickets_by_account.get(str(account.get("account_id")), {})
    expiry = str(ticket.get("ticket_expiry_date", ""))
    rows.append({"Account": account.get("account_name", ""), "Purchase Date": ticket.get("ticket_purchase_date", ""), "Expiry Date": expiry, "Status": ticket_status(expiry), "Days Left": days_until_expiry(expiry), "Price USDT": ticket.get("ticket_price_usdt", 0.0)})
st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
