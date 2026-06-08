from __future__ import annotations

import pandas as pd
import streamlit as st

from services.admin_service import (
    ALLOW_MODE_CLOSED,
    ALLOW_MODE_OPEN,
    SUPER_ADMIN_EMAIL,
    configure_admin_store,
    get_access_state,
    get_audit_logs,
    get_system_logs,
    get_usage_summary,
    is_email_allowed,
    is_super_admin,
    log_event,
    notification_recommendations,
    set_access_mode,
    set_email_access,
)
from services.auth_service import GOOGLE_DRIVE_FILE_SCOPE, OPENID_SCOPES, GoogleOAuthConfig, build_google_login_url, validate_minimum_drive_scope
from services.session_store import SessionJsonStore

SESSION_USER = "wf_user"
SESSION_STORE = "wf_store"


def parse_scopes(value: object) -> tuple[str, ...]:
    if not value:
        return (*OPENID_SCOPES, GOOGLE_DRIVE_FILE_SCOPE)
    if isinstance(value, str):
        return tuple(part.strip() for part in value.replace(",", " ").split() if part.strip())
    return tuple(str(part).strip() for part in value if str(part).strip())


def oauth_config_from_secrets() -> GoogleOAuthConfig:
    return GoogleOAuthConfig(
        client_id=str(st.secrets.get("GOOGLE_CLIENT_ID", "")),
        redirect_uri=str(st.secrets.get("GOOGLE_REDIRECT_URI", "")),
        scopes=parse_scopes(st.secrets.get("GOOGLE_SCOPES", "")),
    )


def current_store() -> SessionJsonStore:
    if SESSION_STORE not in st.session_state:
        st.session_state[SESSION_STORE] = SessionJsonStore(namespace=current_user_email() or "pilot-local")
    return st.session_state[SESSION_STORE]


def current_user_email() -> str:
    user = st.session_state.get(SESSION_USER, {})
    return str(user.get("email", "")) if isinstance(user, dict) else ""


def render_login_gate() -> bool:
    if SESSION_USER in st.session_state:
        email = current_user_email()
        if is_super_admin(email):
            configure_admin_store(current_store())
        if not is_email_allowed(email):
            log_event(email, "Access", "blocked", "User is blocked or not allowlisted.")
            st.error("Your Gmail is not active for this pilot. Please contact the pilot admin.")
            return False
        log_event(email, "Session", "page_view", "App rerun/page view")
        return True
    st.title("Wildforest Tracker")
    st.caption("Pilot 01 web app. Configure Google OAuth in Streamlit secrets before external pilot use.")
    try:
        config = oauth_config_from_secrets()
        if not validate_minimum_drive_scope(config.scopes):
            st.error("GOOGLE_SCOPES must include https://www.googleapis.com/auth/drive.file")
            return False
        if config.client_id and config.redirect_uri:
            st.link_button("Login with Google", build_google_login_url(config, state="pilot01"), type="primary")
        else:
            st.info("Google OAuth secrets are not configured yet. Using local pilot preview session.")
        preview_email = st.text_input("Pilot preview Gmail", value="pilot-preview@example.com")
        if st.button("Start pilot preview", type="primary"):
            email = preview_email.strip().lower()
            if email == SUPER_ADMIN_EMAIL:
                st.session_state[SESSION_USER] = {"email": email, "drive_folder_name": "Wildforest Tracker Admin"}
                st.session_state[SESSION_STORE] = SessionJsonStore(namespace=email)
                configure_admin_store(st.session_state[SESSION_STORE])
                log_event(email, "Access", "admin_preview_login", "Super admin preview session started")
                st.rerun()
            if not is_email_allowed(email):
                log_event(email, "Access", "blocked_preview", "Blocked preview login attempt")
                st.error("This Gmail is not active for this pilot.")
                return False
            st.session_state[SESSION_USER] = {"email": email, "drive_folder_name": "Wildforest Tracker"}
            st.session_state[SESSION_STORE] = SessionJsonStore(namespace=email)
            log_event(email, "Access", "login", "Preview session started")
            st.rerun()
    except Exception as error:
        st.error(f"Google login is not configured: {error}")
    return False


def render_user_bar() -> None:
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
            log_event(email, "Access", "logout", "User logged out")
            st.session_state.pop(SESSION_USER, None)
            st.session_state.pop(SESSION_STORE, None)
            st.rerun()
    if is_super_admin(email):
        render_super_admin_panel()


def render_super_admin_panel() -> None:
    with st.expander("Super Admin", expanded=False):
        st.caption(f"Only {SUPER_ADMIN_EMAIL} can see this panel. Admin config/log files are saved through the signed-in admin storage boundary.")
        access_tab, usage_tab, errors_tab, notify_tab = st.tabs(["Access", "Usage Logs", "System Errors", "Notifications"])

        with access_tab:
            state = get_access_state()
            mode_label = "Open except blocked" if state.get("mode") == ALLOW_MODE_OPEN else "Allowlist only"
            selected_mode = st.radio(
                "Pilot access mode",
                ["Open except blocked", "Allowlist only"],
                index=0 if mode_label == "Open except blocked" else 1,
                horizontal=True,
            )
            next_mode = ALLOW_MODE_OPEN if selected_mode == "Open except blocked" else ALLOW_MODE_CLOSED
            if next_mode != state.get("mode"):
                set_access_mode(next_mode)
                log_event(SUPER_ADMIN_EMAIL, "Admin", "set_access_mode", next_mode)
                st.success("Access mode updated.")
                st.rerun()

            target_email = st.text_input("Gmail to activate/deactivate")
            col1, col2 = st.columns(2)
            if col1.button("Activate Gmail"):
                set_email_access(target_email, True)
                log_event(SUPER_ADMIN_EMAIL, "Admin", "activate_email", target_email)
                st.success("Gmail activated.")
                st.rerun()
            if col2.button("Deactivate Gmail"):
                set_email_access(target_email, False)
                log_event(SUPER_ADMIN_EMAIL, "Admin", "deactivate_email", target_email)
                st.warning("Gmail deactivated.")
                st.rerun()

            access_rows = [
                {"status": "allowed", "email": item} for item in get_access_state().get("allowed_emails", [])
            ] + [
                {"status": "blocked", "email": item} for item in get_access_state().get("blocked_emails", [])
            ]
            st.dataframe(pd.DataFrame(access_rows), use_container_width=True, hide_index=True)

        with usage_tab:
            st.markdown("#### Suspicious behavior overview")
            summary = get_usage_summary()
            if summary:
                st.dataframe(pd.DataFrame(summary), use_container_width=True, hide_index=True)
            else:
                st.info("No usage logs yet.")
            st.markdown("#### Raw audit log")
            logs = get_audit_logs()
            if logs:
                st.dataframe(pd.DataFrame(logs), use_container_width=True, hide_index=True)
            else:
                st.info("No audit events yet.")

        with errors_tab:
            errors = get_system_logs()
            if errors:
                st.dataframe(pd.DataFrame(errors), use_container_width=True, hide_index=True)
            else:
                st.info("No system errors logged yet.")

        with notify_tab:
            st.markdown("#### Recommended admin notifications")
            for item in notification_recommendations():
                st.write(f"- {item}")
            st.info("Production notification delivery can be wired to email, Telegram, Discord, or Google Chat after you choose the channel.")
