from __future__ import annotations

import streamlit as st

from engines.level_cost_engine import MISSING_LEVEL_COST_MESSAGE, MissingLevelCostConfigurationError
from services.account_service import active_accounts, load_accounts
from services.level_service import NO_RESOURCE_SNAPSHOT_MESSAGE, PLACEHOLDER_COST_WARNING, NoResourceSnapshotError, build_level_plan, load_level_cost_config
from services.resource_service import latest_snapshot_by_account, load_resource_snapshots
from ui.pilot_auth import current_store, render_login_gate, render_user_bar

st.set_page_config(page_title="Level Planner | Wildforest Tracker", page_icon="📈", layout="wide")

if not render_login_gate():
    st.stop()
render_user_bar()

st.title("Level Planner")
st.caption("Plan one unit upgrade at a time. Level Mixer and full simulation are locked for Pilot 01.")

store = current_store()
accounts = active_accounts(load_accounts(store))
snapshots = load_resource_snapshots(store)
snapshot_map = latest_snapshot_by_account(snapshots)
level_cost_config = load_level_cost_config()

if level_cost_config.get("placeholder", False):
    st.warning(PLACEHOLDER_COST_WARNING)

if not accounts:
    st.warning("Add an active account first.")
    st.stop()

account_options = {item["account_name"]: item["account_id"] for item in accounts}
with st.form("level_planner_form"):
    account_name = st.selectbox("Account", list(account_options.keys()))
    account_id = account_options[account_name]
    unit_name = st.text_input("Unit name")
    current_level = st.number_input("Current level", min_value=1, value=1, step=1)
    target_level = st.number_input("Target level", min_value=1, value=2, step=1)
    submitted = st.form_submit_button("Calculate upgrade plan", type="primary")

snapshot = snapshot_map.get(str(account_options.get(account_name, ""))) if account_options else None
if snapshot:
    cols = st.columns(2)
    cols[0].metric("Available gold", f"{int(snapshot.get('gold', 0) or 0):,}")
    cols[1].metric("Available shards", f"{int(snapshot.get('shards', 0) or 0):,}")
else:
    st.info(NO_RESOURCE_SNAPSHOT_MESSAGE)

if submitted:
    try:
        plan = build_level_plan(store, account_id, unit_name, int(current_level), int(target_level), level_cost_config)
        st.subheader("Upgrade Plan")
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
        if plan.missing_shards > 0:
            st.info("Shard earning assumptions are not configured yet, so estimated days are based on missing gold only.")
    except NoResourceSnapshotError:
        st.error(NO_RESOURCE_SNAPSHOT_MESSAGE)
    except MissingLevelCostConfigurationError:
        st.error(MISSING_LEVEL_COST_MESSAGE)
    except ValueError as error:
        st.error(str(error))
