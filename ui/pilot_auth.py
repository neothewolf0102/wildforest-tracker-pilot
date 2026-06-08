from __future__ import annotations

import streamlit as st

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
        if st.button("Start pilot preview", type="primary"):
            st.session_state[SESSION_USER] = {"email": "pilot-preview@example.com", "drive_folder_name": "Wildforest Tracker"}
            st.session_state[SESSION_STORE] = SessionJsonStore(namespace="pilot-preview@example.com")
            st.rerun()
    except Exception as error:
        st.error(f"Google login is not configured: {error}")
    return False


def render_user_bar() -> None:
    user = st.session_state.get(SESSION_USER, {})
    left, right = st.columns([3, 1])
    with left:
        st.caption(f"Signed in as {user.get('email', '')} | Drive folder: {user.get('drive_folder_name', 'Wildforest Tracker')}")
    with right:
        if st.button("Logout"):
            st.session_state.pop(SESSION_USER, None)
            st.session_state.pop(SESSION_STORE, None)
            st.rerun()
