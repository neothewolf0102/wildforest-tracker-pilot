"""Streamlit Account Setup reset hotfix.

Streamlit forbids assigning a widget key after that widget has been rendered in
one script run. Account Setup intentionally resets its form after save/delete
and immediately reruns. This narrow patch lets only the account form keys write
through to the next session-state snapshot instead of crashing the app.
"""

from __future__ import annotations

ACCOUNT_WIDGET_KEYS = {
    "account_action_select",
    "account_confirm_delete",
    "account_loaded_id",
    "account_form_name",
    "account_form_wallet",
    "account_form_active",
    "account_form_note",
}

try:
    from streamlit.errors import StreamlitAPIException
    from streamlit.runtime.state.session_state import SessionState
except Exception:
    SessionState = None
    StreamlitAPIException = Exception


if SessionState is not None and not getattr(SessionState, "_wildforest_account_reset_hotfix", False):
    _original_setitem = SessionState.__setitem__

    def _wildforest_setitem(self, user_key, value):
        try:
            return _original_setitem(self, user_key, value)
        except StreamlitAPIException:
            key = str(user_key)
            if key in ACCOUNT_WIDGET_KEYS:
                self._new_session_state[user_key] = value
                return None
            raise

    SessionState.__setitem__ = _wildforest_setitem
    SessionState._wildforest_account_reset_hotfix = True
