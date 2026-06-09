from __future__ import annotations

import secrets as py_secrets
from datetime import date

import pandas as pd
import streamlit as st

from adapters.google_drive_adapter import GoogleDriveRestClient
from adapters.google_oauth_adapter import exchange_auth_code, fetch_google_user
from services.admin_service import (
    DISABLED_MESSAGE,
    NOT_INVITED_MESSAGE,
    SUPER_ADMIN_EMAIL,
    configure_access_config,
    configure_admin_store,
    get_access_decision,
    get_activity_logs,
    get_notifications,
    get_suspicious_flags,
    get_system_logs,
    get_usage_summary,
    is_super_admin,
    log_activity,
    log_system_error,
    mark_all_notifications_read,
    mark_login_success,
    mark_notification_read,
    parse_email_config,
    remove_email_from_allowlist,
    set_email_access,
    upsert_allowed_user,
)
from services.auth_service import GOOGLE_DRIVE_FILE_SCOPE, OPENID_SCOPES, GoogleOAuthConfig, build_google_login_url, validate_minimum_drive_scope
from services.google_drive_service import DriveJsonStore, build_drive_user_context
from services.session_store import SessionJsonStore

SESSION_USER = "wf_user"
SESSION_STORE = "wf_store"
SESSION_OAUTH_STATE = "wf_oauth_state"


def parse_scopes(value: object) -> tuple[str, ...]:
    if not value:
        return (*OPENID_SCOPES, GOOGLE_DRIVE_FILE_SCOPE)
    if isinstance(value, str):
        return tuple(part.strip() for part in value.replace(",", " ").split() if part.strip())
    return tuple(str(part).strip() for part in value if str(part).strip())


def configure_admin_from_secrets() -> None:
    super_admins = parse_email_config(st.secrets.get("SUPER_ADMIN_EMAILS", SUPER_ADMIN_EMAIL), (SUPER_ADMIN_EMAIL,))
    allowed = parse_email_config(st.secrets.get("PILOT_ALLOWED_EMAILS", ""), super_admins)
    configure_access_config(super_admins, allowed)


def oauth_config_from_secrets() -> GoogleOAuthConfig:
    return GoogleOAuthConfig(
        client_id=str(st.secrets.get("GOOGLE_CLIENT_ID", "")),
        redirect_uri=str(st.secrets.get("GOOGLE_REDIRECT_URI", "")),
        scopes=parse_scopes(st.secrets.get("GOOGLE_SCOPES", "")),
    )


def app_folder_name_from_secrets(email: str) -> str:
    if is_super_admin(email):
        return str(st.secrets.get("APP_ADMIN_DRIVE_FOLDER_NAME", "Wildforest Tracker Admin"))
    return str(st.secrets.get("APP_DRIVE_FOLDER_NAME", "Wildforest Tracker"))


def current_store():
    if SESSION_STORE not in st.session_state:
        st.session_state[SESSION_STORE] = SessionJsonStore(namespace=current_user_email() or "pilot-local")
    return st.session_state[SESSION_STORE]


def current_user_email() -> str:
    user = st.session_state.get(SESSION_USER, {})
    return str(user.get("email", "")) if isinstance(user, dict) else ""


def _block_login(email: str, reason: str) -> None:
    if reason == "disabled":
        log_activity(email, "Access", "login_blocked_disabled", "Disabled Gmail attempted login", status="blocked", severity="warning")
        st.error(DISABLED_MESSAGE)
    else:
        log_activity(email, "Access", "login_blocked_not_allowlisted", "Non-allowlisted Gmail attempted login", status="blocked", severity="warning")
        st.error(NOT_INVITED_MESSAGE)


def handle_google_callback() -> bool:
    configure_admin_from_secrets()
    params = st.query_params
    code = params.get("code")
    state = params.get("state")
    if not code:
        return False
    expected_state = st.session_state.get(SESSION_OAUTH_STATE)
    if expected_state and state != expected_state:
        log_system_error("", "Access", "oauth_login_failed", "OAuth state did not match", severity="warning")
        st.error("Google login failed because OAuth state did not match.")
        return False
    try:
        config = oauth_config_from_secrets()
        token_set = exchange_auth_code(config, str(st.secrets.get("GOOGLE_CLIENT_SECRET", "")), str(code))
        google_user = fetch_google_user(token_set.access_token)
        email = google_user.email.strip().lower()
        decision = get_access_decision(email)
        if not decision["allowed"]:
            _block_login(email, decision["reason"])
            return False
        client = GoogleDriveRestClient(token_set.access_token)
        context = build_drive_user_context(google_user, token_set.access_token, client, app_folder_name_from_secrets(email))
        st.session_state[SESSION_USER] = {
            "email": email,
            "display_name": google_user.display_name,
            "user_id": google_user.user_id,
            "drive_folder_name": context.folder_name,
            "drive_folder_id": context.root_folder_id,
        }
        st.session_state[SESSION_STORE] = DriveJsonStore(client=client, context=context)
        if is_super_admin(email):
            configure_admin_store(st.session_state[SESSION_STORE])
        mark_login_success(email)
        st.query_params.clear()
        st.rerun()
        return True
    except Exception as error:
        log_system_error("", "Access", "oauth_login_failed", error, severity="critical")
        st.error(f"Google login failed: {error}")
        return False


def render_login_gate() -> bool:
    configure_admin_from_secrets()
    if SESSION_USER in st.session_state:
        email = current_user_email()
        if is_super_admin(email):
            configure_admin_store(current_store())
        decision = get_access_decision(email)
        if not decision["allowed"]:
            _block_login(email, decision["reason"])
            return False
        log_activity(email, "Session", "page_view", "App rerun/page view")
        return True

    if handle_google_callback():
        return False

    st.title("Wildforest Tracker")
    st.caption("Pilot 01 web app. Sign in with Gmail. User data is stored in that user's Google Drive app folder.")
    try:
        config = oauth_config_from_secrets()
        if not validate_minimum_drive_scope(config.scopes):
            st.error("GOOGLE_SCOPES must include https://www.googleapis.com/auth/drive.file")
            return False
        if config.client_id and config.redirect_uri and st.secrets.get("GOOGLE_CLIENT_SECRET", ""):
            state = py_secrets.token_urlsafe(24)
            st.session_state[SESSION_OAUTH_STATE] = state
            st.link_button("Login with Google", build_google_login_url(config, state=state), type="primary")
        else:
            st.info("Google OAuth secrets are not configured yet. Using local pilot preview session.")
            preview_email = st.text_input("Pilot preview Gmail", value=SUPER_ADMIN_EMAIL)
            if st.button("Start pilot preview", type="primary"):
                email = preview_email.strip().lower()
                decision = get_access_decision(email)
                if not decision["allowed"]:
                    _block_login(email, decision["reason"])
                    return False
                folder_name = "Wildforest Tracker Admin" if is_super_admin(email) else "Wildforest Tracker"
                st.session_state[SESSION_USER] = {"email": email, "drive_folder_name": folder_name}
                st.session_state[SESSION_STORE] = SessionJsonStore(namespace=email)
                if is_super_admin(email):
                    configure_admin_store(st.session_state[SESSION_STORE])
                mark_login_success(email)
                st.rerun()
    except Exception as error:
        log_system_error("", "Access", "oauth_login_failed", error, severity="critical")
        st.error(f"Google login is not configured: {error}")
    return False


def render_user_bar() -> None:
    configure_admin_from_secrets()
    user = st.session_state.get(SESSION_USER, {})
    email = current_user_email()
    if is_super_admin(email):
        configure_admin_store(current_store())
    left, right = st.columns([3, 1])
    with left:
        role = "Super Admin" if is_super_admin(email) else "Pilot User"
        st.caption(f"Signed in as {user.get('email', '')} | Role: {role} | Drive folder: {user.get('drive_folder_name', 'Wildforest Tracker')}")
    with right:
        if st.button("Logout"):
            log_activity(email, "Access", "logout", "User logged out")
            st.session_state.pop(SESSION_USER, None)
            st.session_state.pop(SESSION_STORE, None)
            st.session_state.pop(SESSION_OAUTH_STATE, None)
            st.rerun()
    if is_super_admin(email):
        render_super_admin_panel()


def _filter_rows(rows: list[dict], email: str, type_key: str, selected_type: str, severity: str, start_date: date | None, end_date: date | None) -> list[dict]:
    filtered = []
    for row in rows:
        row_email = str(row.get("user_email") or row.get("email") or "")
        row_type = str(row.get(type_key) or "")
        row_severity = str(row.get("severity") or "")
        row_date = str(row.get("timestamp") or "")[:10]
        if email and email.lower() not in row_email.lower():
            continue
        if selected_type and row_type != selected_type:
            continue
        if severity and row_severity != severity:
            continue
        if start_date and row_date and row_date < start_date.isoformat():
            continue
        if end_date and row_date and row_date > end_date.isoformat():
            continue
        filtered.append(row)
    return filtered[:100]


def _show_log_table(rows: list[dict], empty_message: str) -> None:
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info(empty_message)


def render_super_admin_panel() -> None:
    with st.expander("Super Admin", expanded=False):
        st.caption("Only super admin users can see this panel. Admin metadata is stored through the admin Google Drive store; user gameplay data remains in each user's own storage.")
        users_tab, manage_tab, activity_tab, errors_tab, suspicious_tab, notify_tab = st.tabs([
            "Pilot Users",
            "Manage Access",
            "Activity Logs",
            "Error Logs",
            "Suspicious",
            "Notifications",
        ])

        with users_tab:
            summary = get_usage_summary()
            _show_log_table(summary, "No pilot users or activity yet.")
            st.caption("Account/resource totals are shown when available in admin metadata. Pilot 01 does not cross-read every user's private Drive files.")

        with manage_tab:
            summary = get_usage_summary()
            emails = [row["email"] for row in summary]
            selected = st.selectbox("Selected Gmail", options=emails or [""], index=0)
            target_email = st.text_input("Gmail", value=selected)
            admin_note = st.text_area("Internal admin note / reason", height=80)
            col1, col2, col3, col4 = st.columns(4)
            if col1.button("Add allowed Gmail"):
                upsert_allowed_user(target_email, active=True, admin_note=admin_note)
                log_activity(current_user_email(), "Admin", "allowlist_user_added", target_email)
                st.success("Gmail added to allowlist.")
                st.rerun()
            if col2.button("Activate Gmail"):
                set_email_access(target_email, True, admin_note)
                log_activity(current_user_email(), "Admin", "user_reactivated", target_email)
                st.success("Gmail activated.")
                st.rerun()
            if col3.button("Deactivate Gmail"):
                set_email_access(target_email, False, admin_note)
                log_activity(current_user_email(), "Admin", "user_deactivated", target_email, status="success", severity="warning")
                st.warning("Gmail deactivated. Gameplay data was not deleted.")
                st.rerun()
            if col4.button("Remove Gmail"):
                removed = remove_email_from_allowlist(target_email, admin_note)
                log_activity(current_user_email(), "Admin", "user_removed_from_allowlist", target_email, metadata={"removed": removed})
                st.warning("Gmail removed from allowlist. Gameplay data was not deleted." if removed else "Gmail was not in allowlist.")
                st.rerun()
            st.caption("Disabling or removing a Gmail does not delete user gameplay data in this pilot build.")

        with activity_tab:
            logs = get_activity_logs()
            action_types = sorted({str(row.get("action_type") or "") for row in logs if row.get("action_type")})
            severities = sorted({str(row.get("severity") or "") for row in logs if row.get("severity")})
            c1, c2, c3, c4 = st.columns(4)
            email_filter = c1.text_input("Filter user email", key="activity_email_filter")
            action_filter = c2.selectbox("Action type", [""] + action_types, key="activity_action_filter")
            severity_filter = c3.selectbox("Severity", [""] + severities, key="activity_severity_filter")
            date_range = c4.date_input("Date range", value=[], key="activity_date_filter")
            start_date = date_range[0] if isinstance(date_range, tuple) and len(date_range) > 0 else None
            end_date = date_range[1] if isinstance(date_range, tuple) and len(date_range) > 1 else None
            _show_log_table(_filter_rows(logs, email_filter, "action_type", action_filter, severity_filter, start_date, end_date), "No activity logs yet.")

        with errors_tab:
            errors = get_system_logs()
            error_types = sorted({str(row.get("error_type") or "") for row in errors if row.get("error_type")})
            severities = sorted({str(row.get("severity") or "") for row in errors if row.get("severity")})
            c1, c2, c3 = st.columns(3)
            email_filter = c1.text_input("Filter user email", key="error_email_filter")
            error_filter = c2.selectbox("Error type", [""] + error_types, key="error_type_filter")
            severity_filter = c3.selectbox("Severity", [""] + severities, key="error_severity_filter")
            _show_log_table(_filter_rows(errors, email_filter, "error_type", error_filter, severity_filter, None, None), "No system errors logged yet.")

        with suspicious_tab:
            flags = get_suspicious_flags()
            _show_log_table(flags[:100], "No suspicious behavior flagged yet.")
            flagged_emails = sorted({str(row.get("user_email") or "") for row in flags if row.get("user_email")})
            if flagged_emails:
                selected_email = st.selectbox("Flagged user", flagged_emails)
                reason = st.text_area("Deactivate reason", value="Suspicious behavior review", height=80)
                if st.button("Deactivate flagged user"):
                    set_email_access(selected_email, False, reason)
                    log_activity(current_user_email(), "Admin", "user_deactivated", selected_email, metadata={"reason": reason}, severity="warning")
                    st.warning("Flagged user deactivated. No gameplay data was deleted.")
                    st.rerun()

        with notify_tab:
            notifications = get_notifications()
            unread = [item for item in notifications if not item.get("read", False)]
            c1, c2 = st.columns(2)
            if c1.button("Mark all as read", disabled=not notifications):
                mark_all_notifications_read()
                st.rerun()
            selected_id = c2.selectbox("Notification to mark read", [""] + [item["id"] for item in unread])
            if st.button("Mark selected as read", disabled=not selected_id):
                mark_notification_read(selected_id)
                st.rerun()
            _show_log_table(notifications[:100], "No admin notifications yet.")
