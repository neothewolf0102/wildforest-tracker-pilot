from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from engines.level_cost_engine import MISSING_LEVEL_COST_MESSAGE, MissingLevelCostConfigurationError
from engines.ticket_engine import DEFAULT_TICKET_DURATION_DAYS, days_until_expiry, ticket_status
from services.account_service import ACCOUNT_LIMIT_MESSAGE, MAX_ACCOUNTS_PER_USER, active_accounts, load_accounts, upsert_account
from services.daily_action_service import load_daily_actions, upsert_daily_action
from services.kpi_service import build_kpi_summary
from services.level_service import NO_RESOURCE_SNAPSHOT_MESSAGE, PLACEHOLDER_COST_WARNING, NoResourceSnapshotError, build_level_plan, load_level_cost_config
from services.resource_service import latest_snapshot_by_account, load_resource_snapshots, upsert_manual_resource_snapshot
from services.ticket_service import load_tickets, ticket_by_account, upsert_ticket
from ui.pilot_auth import current_store, render_login_gate, render_user_bar

st.set_page_config(page_title="Wildforest Tracker Pilot 01", page_icon="🌲", layout="wide")

if not render_login_gate():
    st.stop()
render_user_bar()

store = current_store()

st.title("Wildforest Tracker")
st.caption("Pilot global build. Same local-style tab workflow with locked pilot-only exclusions.")

TAB_NAMES = [
    "Account setup",
    "Ticket dashboard",
    "Event earning input",
    "Weekly KPI",
    "Monthly projection",
    "Level + Battle Pass Calculator",
]

tabs = st.tabs(TAB_NAMES)
tab_map = dict(zip(TAB_NAMES, tabs))


def load_earnings() -> list[dict]:
    return list(store.load_json("earnings.json", default=[]))


def save_earnings(rows: list[dict]) -> None:
    store.save_json("earnings.json", rows)


def account_name_by_id(accounts: list[dict]) -> dict[str, str]:
    return {str(item.get("account_id")): str(item.get("account_name", "")) for item in accounts}


with tab_map["Account setup"]:
    st.subheader("Account setup")
    accounts = load_accounts(store)
    snapshots = load_resource_snapshots(store)
    snapshot_map = latest_snapshot_by_account(snapshots)

    cols = st.columns(4)
    cols[0].metric("Accounts", len(accounts))
    cols[1].metric("Capacity", f"{len(accounts)}/{MAX_ACCOUNTS_PER_USER}")
    cols[2].metric("Total gold", f"{sum(int(item.get('gold', 0) or 0) for item in snapshot_map.values()):,}")
    cols[3].metric("Total shards", f"{sum(int(item.get('shards', 0) or 0) for item in snapshot_map.values()):,}")

    if len(accounts) >= MAX_ACCOUNTS_PER_USER:
        st.warning(ACCOUNT_LIMIT_MESSAGE)

    with st.form("account_form"):
        account_name = st.text_input("Account name")
        wallet_address = st.text_input("Wallet address")
        active = st.checkbox("Active", value=True)
        note = st.text_input("Note")
        submitted = st.form_submit_button("Save account", type="primary", disabled=len(accounts) >= MAX_ACCOUNTS_PER_USER)
        if submitted:
            try:
                upsert_account(store, account_name, wallet_address, active, note)
                st.success("Account saved.")
                st.rerun()
            except Exception as error:
                st.error(f"Save failed: {error}")

    if accounts:
        account_rows = []
        for account in accounts:
            snapshot = snapshot_map.get(str(account.get("account_id")), {})
            account_rows.append({
                "Account": account.get("account_name", ""),
                "Wallet": account.get("wallet_address", ""),
                "Active": account.get("active", True),
                "Gold": snapshot.get("gold", 0),
                "Shards": snapshot.get("shards", 0),
                "WF": snapshot.get("wf", 0.0),
                "Note": account.get("note", ""),
            })
        st.dataframe(pd.DataFrame(account_rows), use_container_width=True, hide_index=True)
    else:
        st.info("No accounts yet.")

    st.divider()
    st.subheader("Resource Snapshot")
    active = active_accounts(accounts)
    if not active:
        st.info("Add an active account before saving resources.")
    else:
        account_options = {item["account_name"]: item["account_id"] for item in active}
        with st.form("resource_snapshot_form"):
            resource_account = st.selectbox("Account", list(account_options.keys()))
            gold = st.number_input("Gold", min_value=0, step=1)
            shards = st.number_input("Shards", min_value=0, step=1)
            wf = st.number_input("WF", min_value=0.0, step=0.01, format="%.2f")
            resource_note = st.text_input("Resource note")
            if st.form_submit_button("Save resource snapshot", type="primary"):
                upsert_manual_resource_snapshot(store, account_options[resource_account], int(gold), int(shards), float(wf), resource_note)
                st.success("Resource snapshot saved.")
                st.rerun()

with tab_map["Ticket dashboard"]:
    st.subheader("Ticket dashboard")
    accounts = active_accounts(load_accounts(store))
    tickets = load_tickets(store)
    tickets_by_account = ticket_by_account(tickets)
    if not accounts:
        st.warning("Add an active account first.")
    else:
        account_options = {item["account_name"]: item["account_id"] for item in accounts}
        with st.form("ticket_form"):
            account_name = st.selectbox("Account", list(account_options.keys()))
            purchase_date = st.date_input("Ticket purchase date", value=date.today())
            ticket_price = st.number_input("Ticket price USDT", min_value=0.0, value=1.0, step=0.5, format="%.2f")
            if st.form_submit_button("Save ticket", type="primary"):
                upsert_ticket(store, account_options[account_name], purchase_date, ticket_price, DEFAULT_TICKET_DURATION_DAYS)
                st.success("Ticket saved.")
                st.rerun()
        rows = []
        for account in accounts:
            ticket = tickets_by_account.get(str(account.get("account_id")), {})
            expiry = str(ticket.get("ticket_expiry_date", ""))
            rows.append({
                "Account": account.get("account_name", ""),
                "Purchase Date": ticket.get("ticket_purchase_date", ""),
                "Expiry Date": expiry,
                "Status": ticket_status(expiry),
                "Days Left": days_until_expiry(expiry),
                "Price USDT": ticket.get("ticket_price_usdt", 0.0),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

with tab_map["Event earning input"]:
    st.subheader("Event earning input")
    accounts = active_accounts(load_accounts(store))
    earnings = load_earnings()
    if not accounts:
        st.warning("Add an active account first.")
    else:
        account_options = {item["account_name"]: item["account_id"] for item in accounts}
        with st.form("earning_form"):
            earning_date = st.date_input("Event date", value=date.today())
            account_name = st.selectbox("Account", list(account_options.keys()), key="earning_account")
            leaderboard_wf = st.number_input("Leaderboard WF", min_value=0.0, step=0.01, format="%.2f")
            pve_wf = st.number_input("PvE WF", min_value=0.0, step=0.01, format="%.2f")
            bounty_wf = st.number_input("Bounty WF", min_value=0.0, step=0.01, format="%.2f")
            if st.form_submit_button("Save event earnings", type="primary"):
                earnings.append({
                    "event_date": earning_date.isoformat(),
                    "account_id": account_options[account_name],
                    "leaderboard_wf": float(leaderboard_wf),
                    "pve_wf": float(pve_wf),
                    "bounty_wf": float(bounty_wf),
                    "total_wf": float(leaderboard_wf) + float(pve_wf) + float(bounty_wf),
                })
                save_earnings(earnings)
                st.success("Event earnings saved.")
                st.rerun()
    if earnings:
        names = account_name_by_id(load_accounts(store))
        table = pd.DataFrame(earnings)
        table["Account"] = table["account_id"].map(names).fillna(table["account_id"])
        st.dataframe(table[["event_date", "Account", "leaderboard_wf", "pve_wf", "bounty_wf", "total_wf"]], use_container_width=True, hide_index=True)
    else:
        st.info("No event earnings saved yet.")

with tab_map["Weekly KPI"]:
    st.subheader("Weekly KPI")
    earnings = pd.DataFrame(load_earnings())
    if earnings.empty:
        st.info("No earnings saved yet.")
    else:
        earnings["event_date"] = pd.to_datetime(earnings["event_date"], errors="coerce")
        earnings["week"] = earnings["event_date"].dt.strftime("%G-W%V")
        weekly = earnings.groupby("week", as_index=False)[["leaderboard_wf", "pve_wf", "bounty_wf", "total_wf"]].sum()
        st.dataframe(weekly, use_container_width=True, hide_index=True)
        st.bar_chart(weekly.set_index("week")[["total_wf"]])

with tab_map["Monthly projection"]:
    st.subheader("Monthly projection")
    earnings = pd.DataFrame(load_earnings())
    wf_price = st.number_input("Manual WF price USDT for projection", min_value=0.0, value=0.0, step=0.0001, format="%.6f")
    if earnings.empty:
        st.info("No monthly data yet.")
    else:
        earnings["event_date"] = pd.to_datetime(earnings["event_date"], errors="coerce")
        earnings["month"] = earnings["event_date"].dt.strftime("%Y-%m")
        monthly = earnings.groupby("month", as_index=False)[["leaderboard_wf", "pve_wf", "bounty_wf", "total_wf"]].sum()
        monthly["estimated_usdt"] = monthly["total_wf"] * float(wf_price)
        st.dataframe(monthly, use_container_width=True, hide_index=True)
        st.bar_chart(monthly.set_index("month")[["total_wf"]])

with tab_map["Level + Battle Pass Calculator"]:
    st.subheader("Level + Battle Pass Calculator")
    st.caption("Pilot build includes the basic level and Battle Pass calculator only. Level simulation is locked.")
    accounts = active_accounts(load_accounts(store))
    snapshots = load_resource_snapshots(store)
    snapshot_map = latest_snapshot_by_account(snapshots)
    level_cost_config = load_level_cost_config()
    if level_cost_config.get("placeholder", False):
        st.warning(PLACEHOLDER_COST_WARNING)
    if not accounts:
        st.warning("Add an active account first.")
    else:
        account_options = {item["account_name"]: item["account_id"] for item in accounts}
        with st.form("level_planner_form"):
            account_name = st.selectbox("Account", list(account_options.keys()), key="level_account")
            account_id = account_options[account_name]
            unit_name = st.text_input("Unit name")
            current_level = st.number_input("Current level", min_value=1, value=1, step=1)
            target_level = st.number_input("Target level", min_value=1, value=2, step=1)
            submitted = st.form_submit_button("Calculate upgrade plan", type="primary")
        snapshot = snapshot_map.get(str(account_id))
        if snapshot:
            cols = st.columns(2)
            cols[0].metric("Available gold", f"{int(snapshot.get('gold', 0) or 0):,}")
            cols[1].metric("Available shards", f"{int(snapshot.get('shards', 0) or 0):,}")
        else:
            st.info(NO_RESOURCE_SNAPSHOT_MESSAGE)
        if submitted:
            try:
                plan = build_level_plan(store, account_id, unit_name, int(current_level), int(target_level), level_cost_config)
                st.metric("Can upgrade now?", "Yes" if plan.can_upgrade_now else "No")
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Required gold", f"{plan.required_gold:,}")
                col2.metric("Required shards", f"{plan.required_shards:,}")
                col3.metric("Available gold", f"{plan.available_gold:,}")
                col4.metric("Available shards", f"{plan.available_shards:,}")
                col5, col6, col7 = st.columns(3)
                col5.metric("Missing gold", f"{plan.missing_gold:,}")
                col6.metric("Missing shards", f"{plan.missing_shards:,}")
                col7.metric("Estimated days needed", plan.estimated_days_needed)
                st.caption(plan.earning_assumption)
            except NoResourceSnapshotError:
                st.error(NO_RESOURCE_SNAPSHOT_MESSAGE)
            except MissingLevelCostConfigurationError:
                st.error(MISSING_LEVEL_COST_MESSAGE)
            except ValueError as error:
                st.error(str(error))

    st.divider()
    st.markdown("### Battle Pass quick calculator")
    bp_cols = st.columns(4)
    battle_pass_cost_wf = bp_cols[0].number_input("Battle Pass cost per account", min_value=0.0, value=0.0, step=10.0, format="%.2f")
    shards_per_account = bp_cols[1].number_input("Shards earned per account per cycle", min_value=0, value=0, step=100)
    golds_per_account = bp_cols[2].number_input("Gold earned per account per cycle", min_value=0, value=0, step=1000)
    account_count = bp_cols[3].number_input("Accounts", min_value=1, value=max(len(accounts), 1), step=1)
    st.metric("Total Battle Pass cost WF", f"{battle_pass_cost_wf * account_count:,.2f}")
    st.metric("Total shards per cycle", f"{shards_per_account * account_count:,}")
    st.metric("Total gold per cycle", f"{golds_per_account * account_count:,}")
