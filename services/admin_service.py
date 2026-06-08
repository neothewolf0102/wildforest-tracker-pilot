from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

import streamlit as st

SUPER_ADMIN_EMAIL = "firmstoney@gmail.com"
ALLOW_MODE_OPEN = "open_except_blocked"
ALLOW_MODE_CLOSED = "allowlist_only"
ADMIN_ACCESS_FILE = "admin/access_control.json"
ADMIN_AUDIT_FILE = "admin/audit_logs.json"
ADMIN_SYSTEM_FILE = "admin/system_errors.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def default_access_state() -> dict[str, Any]:
    return {
        "mode": ALLOW_MODE_OPEN,
        "allowed_emails": [SUPER_ADMIN_EMAIL],
        "blocked_emails": [],
        "updated_at": now_iso(),
    }


@st.cache_resource
def _admin_state() -> dict[str, Any]:
    return {
        "access": default_access_state(),
        "audit_logs": [],
        "system_logs": [],
        "sessions": {},
        "store": None,
        "hydrated": False,
    }


def normalize_email(email: str) -> str:
    return str(email or "").strip().lower()


def is_super_admin(email: str) -> bool:
    return normalize_email(email) == SUPER_ADMIN_EMAIL


def configure_admin_store(store) -> None:
    state = _admin_state()
    state["store"] = store
    hydrate_admin_state(store)


def hydrate_admin_state(store) -> None:
    state = _admin_state()
    if state.get("hydrated"):
        return
    try:
        access = store.load_json(ADMIN_ACCESS_FILE, default=default_access_state())
        if isinstance(access, dict):
            access.setdefault("allowed_emails", [])
            access.setdefault("blocked_emails", [])
            access.setdefault("mode", ALLOW_MODE_OPEN)
            access.setdefault("updated_at", now_iso())
            if SUPER_ADMIN_EMAIL not in access["allowed_emails"]:
                access["allowed_emails"].append(SUPER_ADMIN_EMAIL)
            state["access"] = access
        audit_logs = store.load_json(ADMIN_AUDIT_FILE, default=[])
        if isinstance(audit_logs, list):
            state["audit_logs"] = audit_logs[-1000:]
        system_logs = store.load_json(ADMIN_SYSTEM_FILE, default=[])
        if isinstance(system_logs, list):
            state["system_logs"] = system_logs[-500:]
        state["hydrated"] = True
    except Exception as error:
        state["system_logs"].append({"timestamp": now_iso(), "email": SUPER_ADMIN_EMAIL, "feature": "Admin", "error": f"Admin storage hydrate failed: {error}"})


def persist_admin_state() -> None:
    state = _admin_state()
    store = state.get("store")
    if store is None:
        return
    try:
        store.save_json(ADMIN_ACCESS_FILE, state["access"])
        store.save_json(ADMIN_AUDIT_FILE, state["audit_logs"][-1000:])
        store.save_json(ADMIN_SYSTEM_FILE, state["system_logs"][-500:])
    except Exception as error:
        state["system_logs"].append({"timestamp": now_iso(), "email": SUPER_ADMIN_EMAIL, "feature": "Admin", "error": f"Admin storage persist failed: {error}"})


def get_access_state() -> dict[str, Any]:
    return _admin_state()["access"]


def set_access_mode(mode: str) -> None:
    if mode not in {ALLOW_MODE_OPEN, ALLOW_MODE_CLOSED}:
        raise ValueError("Invalid access mode.")
    state = get_access_state()
    state["mode"] = mode
    state["updated_at"] = now_iso()
    persist_admin_state()


def set_email_access(email: str, allowed: bool) -> None:
    email = normalize_email(email)
    if not email:
        raise ValueError("Email is required.")
    state = get_access_state()
    allowed_set = set(state.get("allowed_emails", []))
    blocked_set = set(state.get("blocked_emails", []))
    if allowed:
        allowed_set.add(email)
        blocked_set.discard(email)
    else:
        blocked_set.add(email)
        allowed_set.discard(email)
    allowed_set.add(SUPER_ADMIN_EMAIL)
    state["allowed_emails"] = sorted(allowed_set)
    state["blocked_emails"] = sorted(blocked_set)
    state["updated_at"] = now_iso()
    persist_admin_state()


def is_email_allowed(email: str) -> bool:
    email = normalize_email(email)
    if is_super_admin(email):
        return True
    state = get_access_state()
    if email in set(state.get("blocked_emails", [])):
        return False
    if state.get("mode") == ALLOW_MODE_CLOSED:
        return email in set(state.get("allowed_emails", []))
    return bool(email)


def log_event(email: str, feature: str, action: str, detail: str = "") -> None:
    email = normalize_email(email) or "anonymous"
    state = _admin_state()
    session = state["sessions"].setdefault(email, {"first_seen": now_iso(), "last_seen": now_iso(), "events": 0})
    session["last_seen"] = now_iso()
    session["events"] = int(session.get("events", 0)) + 1
    state["audit_logs"].append({"timestamp": now_iso(), "email": email, "feature": feature, "action": action, "detail": detail})
    del state["audit_logs"][:-1000]
    persist_admin_state()


def log_system_error(email: str, feature: str, error: Exception | str) -> None:
    _admin_state()["system_logs"].append({"timestamp": now_iso(), "email": normalize_email(email), "feature": feature, "error": str(error)})
    del _admin_state()["system_logs"][:-500]
    persist_admin_state()


def get_audit_logs() -> list[dict[str, Any]]:
    return list(_admin_state()["audit_logs"])


def get_system_logs() -> list[dict[str, Any]]:
    return list(_admin_state()["system_logs"])


def get_usage_summary() -> list[dict[str, Any]]:
    logs = get_audit_logs()
    by_user = defaultdict(list)
    feature_counter = defaultdict(Counter)
    for item in logs:
        by_user[item["email"]].append(item)
        feature_counter[item["email"]][item["feature"]] += 1
    rows = []
    for email, user_logs in by_user.items():
        timestamps = [datetime.fromisoformat(item["timestamp"]) for item in user_logs]
        first_seen = min(timestamps)
        last_seen = max(timestamps)
        duration_hours = max((last_seen - first_seen).total_seconds() / 3600, 0)
        events = len(user_logs)
        flags = []
        if events > 200:
            flags.append("High event frequency")
        if duration_hours > 8:
            flags.append("Long session")
        if feature_counter[email].get("System", 0) > 10:
            flags.append("Repeated system errors")
        rows.append(
            {
                "email": email,
                "first_seen": first_seen.isoformat(timespec="seconds"),
                "last_seen": last_seen.isoformat(timespec="seconds"),
                "duration_hours": round(duration_hours, 2),
                "events": events,
                "top_feature": feature_counter[email].most_common(1)[0][0] if feature_counter[email] else "",
                "suspicious_flags": ", ".join(flags),
            }
        )
    return sorted(rows, key=lambda row: row["last_seen"], reverse=True)


def notification_recommendations() -> list[str]:
    return [
        "Notify when a non-allowlisted Gmail attempts access while allowlist mode is enabled.",
        "Notify when a user is blocked but continues trying to access the app.",
        "Notify when a user creates or edits data unusually often in a short window.",
        "Notify when system errors spike for one user or one feature.",
        "Notify when a session exceeds expected daily usage, for example more than 8 hours.",
        "Notify before Pilot account capacity is reached for a user.",
    ]
