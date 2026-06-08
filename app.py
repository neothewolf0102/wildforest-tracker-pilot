from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from engines.level_cost_engine import MISSING_LEVEL_COST_MESSAGE, MissingLevelCostConfigurationError
from engines.ticket_engine import DEFAULT_TICKET_DURATION_DAYS, days_until_expiry, ticket_status
from services.account_service import ACCOUNT_LIMIT_MESSAGE, MAX_ACCOUNTS_PER_USER, active_accounts, load_accounts, upsert_account
from services.daily_action_service import load_daily_actions, upsert_daily_action
from services.kpi_service import build_kpi_summary
from services.level_service import (
    PLACEHOLDER_COST_WARNING,
    build_multi_account_upgrade_plan,
    load_level_cost_config,
)
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


def format_int(value: int | float | str) -> str:
    return f"{int(float(value or 0)):,}"


def format_float(value: int | float | str, decimals: int = 2) -> str:
    return f"{float(value or 0):,.{decimals}f}"


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
    st.markdown("### Level + Battle Pass Calculator")
    st.caption("Plan progress, calculate costs, and choose account moves. Level Simulation Mixer and export are locked for Pilot 01.")
    accounts = active_accounts(load_accounts(store))
    snapshots = load_resource_snapshots(store)
    level_cost_config = load_level_cost_config()
    if level_cost_config.get("placeholder", False):
        st.warning(PLACEHOLDER_COST_WARNING)

    with st.container(border=True):
        st.markdown("**Leveling Units**")
        unit_cols = st.columns([2, 1, 1, 2, 1])
        unit_name = unit_cols[0].text_input("Unit label/name", value=st.session_state.get("pilot_unit_name", "Unit 1"), key="pilot_unit_name")
        current_level = unit_cols[1].number_input("Current level", min_value=1, max_value=59, value=int(st.session_state.get("pilot_current_level", 10)), step=1, key="pilot_current_level")
        target_level = unit_cols[2].number_input("Target level", min_value=2, max_value=60, value=max(int(st.session_state.get("pilot_target_level", 60)), 2), step=1, key="pilot_target_level")
        unit_note = unit_cols[3].text_input("Note", key="pilot_unit_note")
        save_unit = unit_cols[4].checkbox("Save unit", value=True, key="pilot_save_unit")
        units = [{"unit_name": unit_name or "Unit 1", "current_level": int(current_level), "target_level": int(target_level), "note": unit_note}] if save_unit else []

    with st.container(border=True):
        st.markdown("**Market Price Settings**")
        ron_per_100_shards = st.number_input("RON per 100 shards", min_value=0.0, value=1.4, step=0.1, format="%.2f")
        st.caption("Market price only values shards. Golds are not included in market shard cost unless a gold market price is added later.")

    with st.container(border=True):
        st.markdown("**Battle Pass config**")
        bp_cols = st.columns(4)
        battle_pass_cost_wf = bp_cols[0].number_input("Battle Pass cost per account", min_value=0.0, value=400.0, step=10.0, format="%.2f")
        shards_per_account = bp_cols[1].number_input("Shards earned per account per cycle", min_value=0, value=4500, step=100)
        golds_per_account = bp_cols[2].number_input("Golds earned per account per cycle", min_value=0, value=28000, step=1000)
        bp_levels_per_cycle = bp_cols[3].number_input("Battle Pass levels farmed per cycle", min_value=0, value=28, step=1)
        bp_date_cols = st.columns(2)
        cycle_start = bp_date_cols[0].date_input("Cycle start date", value=date.today())
        cycle_duration_days = bp_date_cols[1].number_input("Cycle duration days", min_value=1, value=14, step=1)
        st.caption("Cycle starts on the configured date. Battle Pass farming is trigger-based and not passive.")
        cycle_end = cycle_start + timedelta(days=int(cycle_duration_days))
        days_remaining = max((cycle_end - date.today()).days, 0)
        st.dataframe(pd.DataFrame([{"Cycle start": cycle_start.isoformat(), "Cycle end": cycle_end.isoformat(), "Days remaining": days_remaining, "BP levels/cycle": int(bp_levels_per_cycle)}]), hide_index=True, use_container_width=True)

    active_count = max(len(accounts), 1)
    total_bp_cost_wf = battle_pass_cost_wf * active_count
    total_bp_shards = shards_per_account * active_count
    total_bp_golds = golds_per_account * active_count

    if accounts and units:
        try:
            plan = build_multi_account_upgrade_plan(accounts, snapshots, units, level_cost_config, mode=st.session_state.get("pilot_calc_mode", "Best Fit / Least Waste"), use_all_active_accounts=True)
        except (MissingLevelCostConfigurationError, ValueError) as error:
            plan = None
            st.error(MISSING_LEVEL_COST_MESSAGE if isinstance(error, MissingLevelCostConfigurationError) else str(error))
    else:
        plan = None
        if not accounts:
            st.warning("Add an active account first.")
        if not units:
            st.warning("Save at least one unit to calculate the plan.")

    st.markdown("**Summary**")
    summary = plan["summary"] if plan else {
        "number_of_units": len(units), "account_jump_required": 0, "enough_resource": False,
        "required_shards": 0, "required_golds": 0, "available_shards": 0, "available_golds": 0,
        "remaining_shards": 0, "remaining_golds": 0, "wf_reference_balance": 0.0,
    }
    req_shards = int(summary["required_shards"])
    req_golds = int(summary["required_golds"])
    market_shard_cost_ron = req_shards / 100 * float(ron_per_100_shards)
    bp_cost_ron = total_bp_cost_wf * 0.0318
    card_cols = st.columns(5)
    card_cols[0].metric("Required shards", format_int(req_shards), help="Total shards required by saved units")
    card_cols[0].metric("Required golds", format_int(req_golds))
    card_cols[1].metric("Accounts by shards", format_int(summary.get("account_jump_required", 0)))
    card_cols[1].metric("Accounts to cover both", format_int(summary.get("account_jump_required", 0)))
    card_cols[2].metric("Battle Pass cost WF", format_float(total_bp_cost_wf))
    card_cols[2].metric("Battle Pass cost RON", format_float(bp_cost_ron))
    card_cols[3].metric("Market shard cost RON", format_float(market_shard_cost_ron))
    card_cols[3].metric("Market shard cost USD", format_float(market_shard_cost_ron * 0.064))
    card_cols[4].metric("Surplus shards", format_int(max(int(summary.get("available_shards", 0)) + total_bp_shards - req_shards, 0)))
    card_cols[4].metric("Surplus golds", format_int(max(int(summary.get("available_golds", 0)) + total_bp_golds - req_golds, 0)))

    st.markdown("**Level Planner**")
    use_all_accounts = st.checkbox("Use all active accounts", value=True, key="pilot_use_all_active_accounts")
    calc_mode = st.radio("Calculation mode", ["Minimum Accounts", "Best Fit / Least Waste", "Manual Priority"], index=1, horizontal=True, key="pilot_calc_mode")
    if st.button("Calculate Level Planner", type="primary", disabled=not accounts or not units):
        try:
            st.session_state["pilot_level_plan"] = build_multi_account_upgrade_plan(accounts, snapshots, units, level_cost_config, mode=calc_mode, use_all_active_accounts=use_all_accounts)
        except MissingLevelCostConfigurationError:
            st.error(MISSING_LEVEL_COST_MESSAGE)
        except ValueError as error:
            st.error(str(error))

    plan = st.session_state.get("pilot_level_plan") or plan
    if plan:
        summary = plan["summary"]
        metric_cols = st.columns(5)
        metric_cols[0].metric("Number of Units", format_int(summary["number_of_units"]))
        metric_cols[1].metric("Account Jump Required", format_int(summary["account_jump_required"]))
        metric_cols[2].metric("Enough Resource", "Yes" if summary["enough_resource"] else "No")
        metric_cols[3].metric("Required Shards", format_int(summary["required_shards"]))
        metric_cols[4].metric("Required Golds", format_int(summary["required_golds"]))
        metric_cols_2 = st.columns(5)
        metric_cols_2[0].metric("Available Shards", format_int(summary["available_shards"]))
        metric_cols_2[1].metric("Available Golds", format_int(summary["available_golds"]))
        metric_cols_2[2].metric("Remaining Shards", format_int(summary["remaining_shards"]))
        metric_cols_2[3].metric("Remaining Golds", format_int(summary["remaining_golds"]))
        metric_cols_2[4].metric("WF Reference Balance", format_float(summary["wf_reference_balance"]))

        if summary["enough_resource"]:
            st.success("All saved units can be completed with selected account resources. Saved balances are not modified.")
        else:
            st.warning("Incomplete units remain. Account resources are only simulated here; saved balances are not modified.")

        st.markdown("**Unit Upgrade Plan**")
        st.dataframe(pd.DataFrame(plan["unit_summary"]), hide_index=True, use_container_width=True)

        st.markdown("**Recommended Account Moves**")
        moves_df = pd.DataFrame(plan["recommended_moves"])
        if moves_df.empty:
            st.info("No account move can complete the next pending level with current resources.")
        else:
            st.dataframe(moves_df, hide_index=True, use_container_width=True)

        with st.expander("Advanced details", expanded=False):
            st.markdown("**Raw unit summary**")
            st.dataframe(pd.DataFrame(plan["raw_unit_summary"]), hide_index=True, use_container_width=True)
            st.markdown("**Detailed allocation**")
            st.dataframe(pd.DataFrame(plan["allocation_detail"]), hide_index=True, use_container_width=True)
            st.markdown("**Skipped / unused accounts**")
            st.dataframe(pd.DataFrame(plan["skipped_accounts"]), hide_index=True, use_container_width=True)
            st.caption(plan["earning_assumption"])

    st.caption("Level Simulation Mixer, slider allocation, anchor mode, best-fit simulation pool, custom optimization, OCR, payment, admin dashboard, and export are locked for Pilot 01.")
