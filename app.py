from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd
import streamlit as st

from engines.level_cost_engine import MISSING_LEVEL_COST_MESSAGE, MissingLevelCostConfigurationError
from engines.ticket_engine import DEFAULT_TICKET_DURATION_DAYS, days_until_expiry, ticket_status
from services.account_service import ACCOUNT_LIMIT_MESSAGE, MAX_ACCOUNTS_PER_USER, active_accounts, delete_account, load_accounts, upsert_account
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

PRICE_REFRESH_SECONDS = 1800
BANGKOK_TZ = timezone(timedelta(hours=7), name="UTC+7")
WF_TOKEN_ADDRESS = "0x03affae7e23fd11c85d0c90cc40510994d49e175"
WF_GECKOTERMINAL_URL = (
    "https://api.geckoterminal.com/api/v2/networks/ronin/tokens/"
    f"{WF_TOKEN_ADDRESS}"
)
RON_COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price?ids=ronin&vs_currencies=usd&include_24hr_change=true"

st.set_page_config(page_title="Wildforest Tracker Pilot 01", page_icon="🌲", layout="wide")

if not render_login_gate():
    st.stop()
render_user_bar()

store = current_store()

st.title("Wildforest Tracker")
st.caption("Pilot global build. Level Mixer stays locked; multi-unit Level Planner and WF/RON prices are enabled.")

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


def now_utc7() -> datetime:
    return datetime.now(BANGKOK_TZ)


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


def safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value or default)
    except (TypeError, ValueError):
        return default


@st.cache_data(ttl=PRICE_REFRESH_SECONDS)
def fetch_wf_price_api() -> dict:
    raw_text = ""
    try:
        request = Request(WF_GECKOTERMINAL_URL, headers={"accept": "application/json", "user-agent": "wildforest-tracker-pilot"})
        with urlopen(request, timeout=10) as response:
            raw_text = response.read().decode("utf-8")
        payload = json.loads(raw_text)
        attributes = payload.get("data", {}).get("attributes", {}) if isinstance(payload, dict) else {}
        for field in ("token_price_usd", "price_usd", "base_token_price_usd", "quote_token_price_usd"):
            value = safe_float(attributes.get(field), 0.0)
            if value > 0:
                return {
                    "ok": True,
                    "symbol": "WF/USDT",
                    "price": value,
                    "source": "GeckoTerminal",
                    "updated_at": now_utc7().isoformat(timespec="seconds"),
                }
        return {"ok": False, "symbol": "WF/USDT", "error": "WF price not found in API response.", "raw_excerpt": raw_text[:300]}
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, TypeError, ValueError) as error:
        return {"ok": False, "symbol": "WF/USDT", "error": str(error), "raw_excerpt": raw_text[:300]}


@st.cache_data(ttl=PRICE_REFRESH_SECONDS)
def fetch_ron_price_api() -> dict:
    raw_text = ""
    try:
        request = Request(RON_COINGECKO_URL, headers={"accept": "application/json", "user-agent": "wildforest-tracker-pilot"})
        with urlopen(request, timeout=10) as response:
            raw_text = response.read().decode("utf-8")
        payload = json.loads(raw_text)
        ron_payload = payload.get("ronin", {}) if isinstance(payload, dict) else {}
        price = safe_float(ron_payload.get("usd"), 0.0)
        if price > 0:
            return {
                "ok": True,
                "symbol": "RON/USDT",
                "price": price,
                "source": "CoinGecko",
                "updated_at": now_utc7().isoformat(timespec="seconds"),
            }
        return {"ok": False, "symbol": "RON/USDT", "error": "RON price not found in API response.", "raw_excerpt": raw_text[:300]}
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, TypeError, ValueError) as error:
        return {"ok": False, "symbol": "RON/USDT", "error": str(error), "raw_excerpt": raw_text[:300]}


def load_price_state() -> dict:
    return dict(store.load_json("price_state.json", default={}))


def save_price_state(price_state: dict) -> None:
    store.save_json("price_state.json", price_state)


def refresh_price_state(force: bool = False) -> dict:
    price_state = load_price_state()
    last_refresh = pd.to_datetime(price_state.get("last_refresh_at", ""), errors="coerce")
    is_stale = True
    if pd.notna(last_refresh):
        is_stale = datetime.now(timezone.utc).replace(tzinfo=None) >= last_refresh.to_pydatetime().replace(tzinfo=None) + timedelta(seconds=PRICE_REFRESH_SECONDS)

    if force or is_stale or not price_state:
        wf_result = fetch_wf_price_api()
        ron_result = fetch_ron_price_api()
        if wf_result.get("ok"):
            price_state["wf_usdt"] = wf_result["price"]
            price_state["wf_source"] = wf_result["source"]
            price_state["wf_updated_at"] = wf_result["updated_at"]
            price_state.pop("wf_error", None)
        else:
            price_state["wf_error"] = wf_result.get("error", "WF price API failed.")
        if ron_result.get("ok"):
            price_state["ron_usdt"] = ron_result["price"]
            price_state["ron_source"] = ron_result["source"]
            price_state["ron_updated_at"] = ron_result["updated_at"]
            price_state.pop("ron_error", None)
        else:
            price_state["ron_error"] = ron_result.get("error", "RON price API failed.")
        price_state["last_refresh_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        save_price_state(price_state)
    return price_state


def render_price_panel(price_state: dict) -> dict:
    st.markdown("**WF/RON Price Panel**")
    price_cols = st.columns([1, 1, 1, 1])
    wf_price = safe_float(price_state.get("wf_usdt"), 0.0)
    ron_price = safe_float(price_state.get("ron_usdt"), 0.0)
    price_cols[0].metric("WF/USDT", f"${wf_price:,.6f}" if wf_price > 0 else "Missing")
    price_cols[1].metric("RON/USDT", f"${ron_price:,.6f}" if ron_price > 0 else "Missing")
    price_cols[2].caption(f"WF source: {price_state.get('wf_source', 'manual/API pending')}")
    price_cols[2].caption(f"WF updated: {price_state.get('wf_updated_at', '-')}")
    price_cols[3].caption(f"RON source: {price_state.get('ron_source', 'manual/API pending')}")
    price_cols[3].caption(f"RON updated: {price_state.get('ron_updated_at', '-')}")

    if price_state.get("wf_error"):
        st.warning(f"WF price API issue: {price_state['wf_error']}")
    if price_state.get("ron_error"):
        st.warning(f"RON price API issue: {price_state['ron_error']}")

    action_cols = st.columns([1, 1, 2])
    if action_cols[0].button("Refresh prices", key="refresh_prices_button"):
        fetch_wf_price_api.clear()
        fetch_ron_price_api.clear()
        refresh_price_state(force=True)
        st.success("Price refresh requested.")
        st.rerun()

    with action_cols[2].expander("Manual price fallback", expanded=False):
        manual_wf = st.number_input("Manual WF/USDT", min_value=0.0, value=wf_price, step=0.0001, format="%.6f", key="manual_wf_price")
        manual_ron = st.number_input("Manual RON/USDT", min_value=0.0, value=ron_price, step=0.0001, format="%.6f", key="manual_ron_price")
        if st.button("Save manual prices", key="save_manual_prices"):
            price_state["wf_usdt"] = float(manual_wf)
            price_state["ron_usdt"] = float(manual_ron)
            price_state["wf_source"] = "manual"
            price_state["ron_source"] = "manual"
            now_text = now_utc7().isoformat(timespec="seconds")
            price_state["wf_updated_at"] = now_text
            price_state["ron_updated_at"] = now_text
            price_state["last_refresh_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            save_price_state(price_state)
            st.success("Manual prices saved.")
            st.rerun()

    if wf_price <= 0 or ron_price <= 0:
        st.warning("WF/RON prices are missing. Add manual prices or refresh API before using investment comparison.")
    return price_state


def ensure_level_unit_blocks() -> list[dict]:
    if "pilot_level_unit_blocks" not in st.session_state:
        st.session_state["pilot_level_unit_blocks"] = [
            {"unit_name": "Unit 1", "current_level": 10, "target_level": 60, "note": "", "saved": True}
        ]
    return st.session_state["pilot_level_unit_blocks"]


def add_level_unit() -> None:
    units = ensure_level_unit_blocks()
    next_index = len(units) + 1
    units.append({"unit_name": f"Unit {next_index}", "current_level": 10, "target_level": 60, "note": "", "saved": True})
    st.session_state["pilot_level_unit_blocks"] = units


def remove_level_unit(index: int) -> None:
    units = ensure_level_unit_blocks()
    if len(units) <= 1:
        return
    st.session_state["pilot_level_unit_blocks"] = [unit for idx, unit in enumerate(units) if idx != index]


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

    selected_account = None
    if accounts:
        selected_account_id = st.selectbox(
            "Select existing account",
            [str(item.get("account_id", "")) for item in accounts],
            format_func=lambda account_id: next((item.get("account_name", account_id) for item in accounts if str(item.get("account_id", "")) == str(account_id)), str(account_id)),
            key="selected_account_id",
        )
        selected_account = next((item for item in accounts if str(item.get("account_id", "")) == str(selected_account_id)), None)
    else:
        selected_account_id = ""
        st.info("No existing account selected. Add your first account below.")

    account_mode = st.radio("Account action", ["Add account", "Edit selected account"], horizontal=True, disabled=not accounts)
    editing = account_mode == "Edit selected account" and selected_account is not None
    form_title = "Edit account" if editing else "Add account"
    st.markdown(f"**{form_title}**")

    with st.form("account_form"):
        account_name = st.text_input("Account name", value=str(selected_account.get("account_name", "")) if editing else "")
        wallet_address = st.text_input("Wallet address", value=str(selected_account.get("wallet_address", "")) if editing else "")
        active = st.checkbox("Active", value=bool(selected_account.get("active", True)) if editing else True)
        note = st.text_input("Note", value=str(selected_account.get("note", "")) if editing else "")
        disabled_for_limit = not editing and len(accounts) >= MAX_ACCOUNTS_PER_USER
        submitted = st.form_submit_button("Save account", type="primary", disabled=disabled_for_limit)
        if submitted:
            try:
                upsert_account(
                    store,
                    account_name,
                    wallet_address,
                    active,
                    note,
                    account_id=str(selected_account.get("account_id")) if editing and selected_account else None,
                )
                st.success("Account saved.")
                st.rerun()
            except Exception as error:
                st.error(f"Save failed: {error}")

    if accounts and selected_account is not None:
        st.markdown("**Delete account**")
        st.caption("Deleting an account does not remove historical snapshots in this pilot build.")
        confirm_delete = st.checkbox(
            f"Confirm delete account: {selected_account.get('account_name', '')}",
            key="confirm_delete_account",
        )
        if st.button("Delete selected account", type="secondary", disabled=not confirm_delete):
            deleted = delete_account(store, str(selected_account.get("account_id", "")))
            if deleted:
                st.success("Account deleted.")
                st.rerun()
            else:
                st.warning("Selected account was not found. No changes were made.")

    if accounts:
        account_rows = []
        for account in load_accounts(store):
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
    active = active_accounts(load_accounts(store))
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
    price_state = refresh_price_state(force=False)
    wf_price = safe_float(price_state.get("wf_usdt"), 0.0)
    manual_projection_price = st.number_input("WF price USDT for projection", min_value=0.0, value=wf_price, step=0.0001, format="%.6f")
    if earnings.empty:
        st.info("No monthly data yet.")
    else:
        earnings["event_date"] = pd.to_datetime(earnings["event_date"], errors="coerce")
        earnings["month"] = earnings["event_date"].dt.strftime("%Y-%m")
        monthly = earnings.groupby("month", as_index=False)[["leaderboard_wf", "pve_wf", "bounty_wf", "total_wf"]].sum()
        monthly["estimated_usdt"] = monthly["total_wf"] * float(manual_projection_price)
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

    price_state = refresh_price_state(force=False)
    with st.container(border=True):
        price_state = render_price_panel(price_state)
    wf_price_usdt = safe_float(price_state.get("wf_usdt"), 0.0)
    ron_price_usdt = safe_float(price_state.get("ron_usdt"), 0.0)

    with st.container(border=True):
        header_cols = st.columns([3, 1])
        header_cols[0].markdown("**Leveling Units**")
        if header_cols[1].button("+ Add Unit", key="add_level_unit_button", type="primary"):
            add_level_unit()
            st.rerun()

        units_state = ensure_level_unit_blocks()
        units = []
        for idx, unit in enumerate(list(units_state)):
            row_cols = st.columns([2, 1, 1, 2, 1, 1])
            unit["unit_name"] = row_cols[0].text_input("Unit label/name", value=str(unit.get("unit_name") or f"Unit {idx + 1}"), key=f"pilot_unit_name_{idx}")
            unit["current_level"] = int(row_cols[1].number_input("Current level", min_value=1, max_value=59, value=int(unit.get("current_level", 10)), step=1, key=f"pilot_current_level_{idx}"))
            unit["target_level"] = int(row_cols[2].number_input("Target level", min_value=2, max_value=60, value=max(int(unit.get("target_level", 60)), 2), step=1, key=f"pilot_target_level_{idx}"))
            unit["note"] = row_cols[3].text_input("Note", value=str(unit.get("note", "")), key=f"pilot_unit_note_{idx}")
            unit["saved"] = bool(row_cols[4].checkbox("Save unit", value=bool(unit.get("saved", True)), key=f"pilot_save_unit_{idx}"))
            if row_cols[5].button("Remove", key=f"remove_level_unit_{idx}", disabled=len(units_state) <= 1):
                remove_level_unit(idx)
                st.rerun()
            if unit["saved"]:
                units.append({
                    "unit_name": unit["unit_name"] or f"Unit {idx + 1}",
                    "current_level": int(unit["current_level"]),
                    "target_level": int(unit["target_level"]),
                    "note": unit.get("note", ""),
                })
        st.session_state["pilot_level_unit_blocks"] = units_state
        st.caption("Add multiple units here. Planning is read-only and will not deduct saved resources.")

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
    market_shard_cost_usd = market_shard_cost_ron * ron_price_usdt
    bp_cost_usd = total_bp_cost_wf * wf_price_usdt
    bp_cost_ron = bp_cost_usd / ron_price_usdt if ron_price_usdt > 0 else 0.0

    card_cols = st.columns(5)
    card_cols[0].metric("Units", format_int(summary.get("number_of_units", len(units))))
    card_cols[0].metric("Required shards", format_int(req_shards), help="Total shards required by saved units")
    card_cols[0].metric("Required golds", format_int(req_golds))
    card_cols[1].metric("Accounts by shards", format_int(summary.get("account_jump_required", 0)))
    card_cols[1].metric("Accounts to cover both", format_int(summary.get("account_jump_required", 0)))
    card_cols[2].metric("Battle Pass cost WF", format_float(total_bp_cost_wf))
    card_cols[2].metric("Battle Pass cost RON", format_float(bp_cost_ron))
    card_cols[2].metric("Battle Pass cost USD", format_float(bp_cost_usd))
    card_cols[3].metric("Market shard cost RON", format_float(market_shard_cost_ron))
    card_cols[3].metric("Market shard cost USD", format_float(market_shard_cost_usd))
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

    st.caption("Level Simulation Mixer, slider allocation, anchor mode, custom optimization, OCR, payment, admin dashboard, and export are locked for Pilot 01.")
