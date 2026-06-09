from __future__ import annotations

import traceback
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import streamlit as st

SUPER_ADMIN_EMAIL = "firmstoney@gmail.com"
SUPER_ADMIN_EMAILS = (SUPER_ADMIN_EMAIL,)
PILOT_ALLOWED_EMAILS = (SUPER_ADMIN_EMAIL,)

ADMIN_USERS_FILE = "admin_users.json"
ACTIVITY_LOGS_FILE = "activity_logs.json"
SYSTEM_ERROR_LOGS_FILE = "system_error_logs.json"
SUSPICIOUS_FLAGS_FILE = "suspicious_flags.json"
ADMIN_NOTIFICATIONS_FILE = "admin_notifications.json"

# Legacy names retained for compatibility with older pilot_auth imports/tests.
ALLOW_MODE_OPEN = "open_except_blocked"
ALLOW_MODE_CLOSED = "allowlist_only"
ADMIN_ACCESS_FILE = ADMIN_USERS_FILE
ADMIN_AUDIT_FILE = ACTIVITY_LOGS_FILE
ADMIN_SYSTEM_FILE = SYSTEM_ERROR_LOGS_FILE

MAX_ACTIVITY_LOGS = 5000
MAX_ERROR_LOGS = 1000
MAX_FLAGS = 1000
MAX_NOTIFICATIONS = 1000

SUSPICIOUS_RULES = {
    "level_planner_calculated": (20, timedelta(minutes=5), "More than 20 level planner calculations within 5 minutes."),
    "resource_snapshot_saved": (10, timedelta(minutes=5), "More than 10 resource snapshot saves within 5 minutes."),
    "account_change": (5, timedelta(minutes=10), "More than 5 account create/delete actions within 10 minutes."),
    "validation_failed": (5, timedelta(minutes=10), "More than 5 blocked/failed validation events within 10 minutes."),
    "login_blocked": (5, timedelta(minutes=10), "More than 5 blocked login events within 10 minutes."),
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_ts(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def normalize_email(email: str) -> str:
    return str(email or "").strip().lower()


def is_super_admin(email: str) -> bool:
    return normalize_email(email) in set(_admin_state().get("super_admin_emails", SUPER_ADMIN_EMAILS))


def default_user_record(email: str, active: bool = True, note: str = "") -> dict[str, Any]:
    email = normalize_email(email)
    return {
        "email": email,
        "active": bool(active),
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "last_login_at": "",
        "last_activity_at": "",
        "admin_note": note,
    }


def default_access_state() -> dict[str, Any]:
    users = {email: default_user_record(email, active=True, note="Super admin") for email in SUPER_ADMIN_EMAILS}
    for email in PILOT_ALLOWED_EMAILS:
        users.setdefault(normalize_email(email), default_user_record(email, active=True))
    return {"mode": ALLOW_MODE_CLOSED, "users": users, "updated_at": now_iso()}


@st.cache_resource
def _admin_state() -> dict[str, Any]:
    return {
        "super_admin_emails": tuple(SUPER_ADMIN_EMAILS),
        "pilot_allowed_emails": tuple(PILOT_ALLOWED_EMAILS),
        "access": default_access_state(),
        "activity_logs": [],
        "system_error_logs": [],
        "suspicious_flags": [],
        "notifications": [],
        "store": None,
        "hydrated": False,
    }


def configure_admin_config(super_admin_emails: tuple[str, ...] | list[str] | None = None, pilot_allowed_emails: tuple[str, ...] | list[str] | None = None) -> None:
    state = _admin_state()
    if super_admin_emails is not None:
        state["super_admin_emails"] = tuple(sorted({normalize_email(email) for email in super_admin_emails if normalize_email(email)})) or tuple(SUPER_ADMIN_EMAILS)
    if pilot_allowed_emails is not None:
        state["pilot_allowed_emails"] = tuple(sorted({normalize_email(email) for email in pilot_allowed_emails if normalize_email(email)}))
    access = state["access"]
    users = access.setdefault("users", {})
    for email in state["super_admin_emails"]:
        record = users.setdefault(email, default_user_record(email, active=True, note="Super admin"))
        record["active"] = True
    for email in state["pilot_allowed_emails"]:
        users.setdefault(email, default_user_record(email, active=True))
    access["updated_at"] = now_iso()


def configure_admin_store(store) -> None:
    state = _admin_state()
    state["store"] = store
    hydrate_admin_state(store)


def hydrate_admin_state(store) -> None:
    state = _admin_state()
    if state.get("hydrated"):
        return
    try:
        access = store.load_json(ADMIN_USERS_FILE, default=default_access_state())
        if isinstance(access, dict):
            if "users" not in access:
                access = _migrate_legacy_access(access)
            state["access"] = access
        activity_logs = store.load_json(ACTIVITY_LOGS_FILE, default=[])
        if isinstance(activity_logs, list):
            state["activity_logs"] = activity_logs[-MAX_ACTIVITY_LOGS:]
        error_logs = store.load_json(SYSTEM_ERROR_LOGS_FILE, default=[])
        if isinstance(error_logs, list):
            state["system_error_logs"] = error_logs[-MAX_ERROR_LOGS:]
        flags = store.load_json(SUSPICIOUS_FLAGS_FILE, default=[])
        if isinstance(flags, list):
            state["suspicious_flags"] = flags[-MAX_FLAGS:]
        notifications = store.load_json(ADMIN_NOTIFICATIONS_FILE, default=[])
        if isinstance(notifications, list):
            state["notifications"] = notifications[-MAX_NOTIFICATIONS:]
        configure_admin_config(state.get("super_admin_emails"), state.get("pilot_allowed_emails"))
        state["hydrated"] = True
    except Exception as error:
        state["hydrated"] = True
        log_system_error("", "Admin", "storage_load_failed", error, severity="critical")


def _migrate_legacy_access(access: dict[str, Any]) -> dict[str, Any]:
    users: dict[str, dict[str, Any]] = {}
    for email in access.get("allowed_emails", []):
        users[normalize_email(email)] = default_user_record(email, active=True)
    for email in access.get("blocked_emails", []):
        users[normalize_email(email)] = default_user_record(email, active=False)
    for email in SUPER_ADMIN_EMAILS:
        users[email] = default_user_record(email, active=True, note="Super admin")
    return {"mode": access.get("mode", ALLOW_MODE_CLOSED), "users": users, "updated_at": access.get("updated_at", now_iso())}


def persist_admin_state() -> None:
    state = _admin_state()
    store = state.get("store")
    if store is None:
        return
    try:
        store.save_json(ADMIN_USERS_FILE, state["access"])
        store.save_json(ACTIVITY_LOGS_FILE, state["activity_logs"][-MAX_ACTIVITY_LOGS:])
        store.save_json(SYSTEM_ERROR_LOGS_FILE, state["system_error_logs"][-MAX_ERROR_LOGS:])
        store.save_json(SUSPICIOUS_FLAGS_FILE, state["suspicious_flags"][-MAX_FLAGS:])
        store.save_json(ADMIN_NOTIFICATIONS_FILE, state["notifications"][-MAX_NOTIFICATIONS:])
    except Exception as error:
        _append_system_error("", "Admin", "storage_save_failed", error, severity="critical", persist=False)


def get_access_state() -> dict[str, Any]:
    return _admin_state()["access"]


def set_access_mode(mode: str) -> None:
    if mode not in {ALLOW_MODE_OPEN, ALLOW_MODE_CLOSED}:
        raise ValueError("Invalid access mode.")
    get_access_state()["mode"] = mode
    get_access_state()["updated_at"] = now_iso()
    persist_admin_state()


def upsert_allowed_user(email: str, active: bool = True, admin_note: str = "") -> dict[str, Any]:
    email = normalize_email(email)
    if not email:
        raise ValueError("Email is required.")
    users = get_access_state().setdefault("users", {})
    record = users.get(email, default_user_record(email, active=active, note=admin_note))
    record["email"] = email
    record["active"] = bool(active)
    record["updated_at"] = now_iso()
    if admin_note:
        record["admin_note"] = admin_note
    if is_super_admin(email):
        record["active"] = True
    users[email] = record
    get_access_state()["updated_at"] = now_iso()
    persist_admin_state()
    create_notification("info", "new_user_added_to_allowlist" if active else "user_deactivated", f"{email} updated in pilot allowlist.", email)
    return record


def set_email_access(email: str, allowed: bool, admin_note: str = "") -> None:
    upsert_allowed_user(email, active=allowed, admin_note=admin_note)
    create_notification("info", "user_reactivated" if allowed else "user_deactivated", f"{normalize_email(email)} {'reactivated' if allowed else 'deactivated'}.", normalize_email(email))


def remove_email_from_allowlist(email: str, admin_note: str = "") -> bool:
    email = normalize_email(email)
    if is_super_admin(email):
        raise ValueError("Super admin cannot be removed from the pilot allowlist.")
    users = get_access_state().setdefault("users", {})
    existed = email in users
    if existed:
        users.pop(email)
        get_access_state()["updated_at"] = now_iso()
        persist_admin_state()
        create_notification("info", "user_removed_from_allowlist", f"{email} removed from pilot allowlist. User gameplay data was not deleted.", email)
    return existed


def is_email_allowed(email: str) -> bool:
    return get_access_decision(email)["allowed"]


def get_access_decision(email: str) -> dict[str, Any]:
    email = normalize_email(email)
    if is_super_admin(email):
        return {"allowed": True, "reason": "super_admin"}
    if not email:
        return {"allowed": False, "reason": "not_allowlisted"}
    users = get_access_state().get("users", {})
    record = users.get(email)
    if record and not record.get("active", True):
        return {"allowed": False, "reason": "disabled", "record": record}
    if get_access_state().get("mode") == ALLOW_MODE_CLOSED and not record:
        return {"allowed": False, "reason": "not_allowlisted"}
    return {"allowed": True, "reason": "allowed", "record": record}


def mark_login_success(email: str) -> None:
    email = normalize_email(email)
    users = get_access_state().setdefault("users", {})
    record = users.setdefault(email, default_user_record(email, active=True))
    record["last_login_at"] = now_iso()
    record["last_activity_at"] = now_iso()
    persist_admin_state()
    log_activity(email, "Access", "login_success", "Login succeeded")


def mark_activity(email: str) -> None:
    email = normalize_email(email)
    record = get_access_state().setdefault("users", {}).get(email)
    if record:
        record["last_activity_at"] = now_iso()


def log_activity(
    user_email: str,
    page: str,
    action_type: str,
    action_label: str = "",
    metadata: dict[str, Any] | None = None,
    status: str = "success",
    severity: str = "info",
    session_id: str = "",
) -> dict[str, Any]:
    email = normalize_email(user_email) or "anonymous"
    entry = {
        "timestamp": now_iso(),
        "user_email": email,
        "email": email,
        "session_id": session_id,
        "page": page,
        "feature": page,
        "action_type": action_type,
        "action": action_type,
        "action_label": action_label,
        "detail": action_label,
        "metadata": metadata or {},
        "status": status,
        "severity": severity,
    }
    state = _admin_state()
    state["activity_logs"].append(entry)
    del state["activity_logs"][:-MAX_ACTIVITY_LOGS]
    mark_activity(email)
    _check_suspicious_activity(email, action_type)
    persist_admin_state()
    return entry


def log_event(email: str, feature: str, action: str, detail: str = "") -> None:
    log_activity(email, feature, action, detail)


def log_validation_failed(user_email: str, page: str, action_label: str, metadata: dict[str, Any] | None = None) -> None:
    log_activity(user_email, page, "validation_failed", action_label, metadata, status="blocked", severity="warning")


def log_system_error(email: str, page: str, action_type: str, error: Exception | str, severity: str = "error") -> dict[str, Any]:
    return _append_system_error(email, page, action_type, error, severity=severity, persist=True)


def _append_system_error(email: str, page: str, action_type: str, error: Exception | str, severity: str = "error", persist: bool = True) -> dict[str, Any]:
    entry = {
        "timestamp": now_iso(),
        "user_email": normalize_email(email),
        "email": normalize_email(email),
        "page": page,
        "feature": page,
        "action_type": action_type,
        "error_type": type(error).__name__ if isinstance(error, Exception) else str(action_type),
        "error_message": str(error),
        "short_stack_trace": "".join(traceback.format_exception_only(type(error), error))[-1000:] if isinstance(error, Exception) else "",
        "severity": severity,
    }
    state = _admin_state()
    state["system_error_logs"].append(entry)
    del state["system_error_logs"][:-MAX_ERROR_LOGS]
    if severity in {"critical", "error"}:
        create_notification("critical" if severity == "critical" else "warning", "repeated_system_errors", f"System error: {action_type} - {entry['error_message'][:120]}", normalize_email(email), persist=False)
    _check_repeated_errors(normalize_email(email))
    if persist:
        persist_admin_state()
    return entry


def get_audit_logs() -> list[dict[str, Any]]:
    return get_activity_logs()


def get_activity_logs(limit: int | None = None) -> list[dict[str, Any]]:
    rows = list(_admin_state()["activity_logs"])
    rows.sort(key=lambda row: row.get("timestamp", ""), reverse=True)
    return rows[:limit] if limit else rows


def get_system_logs(limit: int | None = None) -> list[dict[str, Any]]:
    rows = list(_admin_state()["system_error_logs"])
    rows.sort(key=lambda row: row.get("timestamp", ""), reverse=True)
    return rows[:limit] if limit else rows


def get_suspicious_flags(limit: int | None = None) -> list[dict[str, Any]]:
    rows = list(_admin_state()["suspicious_flags"])
    rows.sort(key=lambda row: row.get("timestamp", ""), reverse=True)
    return rows[:limit] if limit else rows


def create_notification(severity: str, title: str, message: str, related_user_email: str = "", persist: bool = True) -> dict[str, Any]:
    item = {
        "id": str(uuid4()),
        "timestamp": now_iso(),
        "severity": severity,
        "title": title,
        "message": message,
        "related_user_email": normalize_email(related_user_email),
        "read": False,
    }
    state = _admin_state()
    state["notifications"].append(item)
    del state["notifications"][:-MAX_NOTIFICATIONS]
    if persist:
        persist_admin_state()
    return item


def get_notifications(limit: int | None = None) -> list[dict[str, Any]]:
    rows = list(_admin_state()["notifications"])
    rows.sort(key=lambda row: row.get("timestamp", ""), reverse=True)
    return rows[:limit] if limit else rows


def mark_notification_read(notification_id: str) -> bool:
    for item in _admin_state()["notifications"]:
        if str(item.get("id")) == str(notification_id):
            item["read"] = True
            persist_admin_state()
            return True
    return False


def mark_all_notifications_read() -> None:
    for item in _admin_state()["notifications"]:
        item["read"] = True
    persist_admin_state()


def _recent_activity(email: str, action_types: set[str], window: timedelta) -> list[dict[str, Any]]:
    cutoff = datetime.now(timezone.utc) - window
    rows = []
    for item in _admin_state()["activity_logs"]:
        if normalize_email(item.get("user_email") or item.get("email")) != normalize_email(email):
            continue
        if item.get("action_type") not in action_types:
            continue
        ts = parse_ts(item.get("timestamp", ""))
        if ts and ts >= cutoff:
            rows.append(item)
    return rows


def _recent_errors(email: str, window: timedelta) -> list[dict[str, Any]]:
    cutoff = datetime.now(timezone.utc) - window
    rows = []
    for item in _admin_state()["system_error_logs"]:
        if normalize_email(item.get("user_email") or item.get("email")) != normalize_email(email):
            continue
        ts = parse_ts(item.get("timestamp", ""))
        if ts and ts >= cutoff:
            rows.append(item)
    return rows


def _check_suspicious_activity(email: str, action_type: str) -> None:
    grouped_action = "account_change" if action_type in {"account_created", "account_deleted"} else "login_blocked" if action_type in {"login_blocked_not_allowlisted", "login_blocked_disabled"} else action_type
    if grouped_action not in SUSPICIOUS_RULES:
        return
    threshold, window, reason = SUSPICIOUS_RULES[grouped_action]
    action_types = {"account_created", "account_deleted"} if grouped_action == "account_change" else {"login_blocked_not_allowlisted", "login_blocked_disabled"} if grouped_action == "login_blocked" else {action_type}
    if len(_recent_activity(email, action_types, window)) > threshold:
        flag_suspicious_behavior(email, reason, {"action_type": grouped_action, "threshold": threshold})


def _check_repeated_errors(email: str) -> None:
    if email and len(_recent_errors(email, timedelta(minutes=10))) > 5:
        flag_suspicious_behavior(email, "More than 5 system errors from the same user within 10 minutes.", {"action_type": "system_error"})


def flag_suspicious_behavior(email: str, reason: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    email = normalize_email(email) or "anonymous"
    flags = _admin_state()["suspicious_flags"]
    recent_duplicate = any(flag.get("user_email") == email and flag.get("reason") == reason and parse_ts(flag.get("timestamp", "")) and parse_ts(flag.get("timestamp", "")) >= datetime.now(timezone.utc) - timedelta(minutes=10) for flag in flags)
    if recent_duplicate:
        return flags[-1]
    flag = {"timestamp": now_iso(), "user_email": email, "reason": reason, "metadata": metadata or {}, "severity": "warning"}
    flags.append(flag)
    del flags[:-MAX_FLAGS]
    create_notification("critical", "user_suspicious_behavior_flagged", reason, email, persist=False)
    log_activity(email, "Security", "suspicious_behavior_flagged", reason, metadata, status="success", severity="warning")
    return flag


def get_user_resource_snapshot(email: str) -> dict[str, Any]:
    # Per-user gameplay data stays in the user's own store. Cross-user Drive reads are intentionally not implemented in Pilot 01.
    return {"account_count": 0, "total_gold": 0, "total_shards": 0, "total_wf": 0.0}


def _usage_duration_by_days(logs: list[dict[str, Any]], days: int) -> float:
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=days - 1)
    by_day: dict[str, list[datetime]] = defaultdict(list)
    for item in logs:
        ts = parse_ts(item.get("timestamp", ""))
        if not ts or ts.date() < cutoff:
            continue
        by_day[ts.date().isoformat()].append(ts)
    seconds = 0.0
    for timestamps in by_day.values():
        seconds += max((max(timestamps) - min(timestamps)).total_seconds(), 0)
    return round(seconds / 3600, 2)


def get_usage_summary() -> list[dict[str, Any]]:
    users = get_access_state().get("users", {})
    logs = get_activity_logs()
    flags = get_suspicious_flags()
    by_user = defaultdict(list)
    feature_counter = defaultdict(Counter)
    today = datetime.now(timezone.utc).date()
    seven_day_cutoff = today - timedelta(days=6)
    for item in logs:
        email = normalize_email(item.get("user_email") or item.get("email"))
        by_user[email].append(item)
        feature_counter[email][item.get("page") or item.get("feature") or "Unknown"] += 1
    rows = []
    all_emails = sorted(set(users.keys()) | set(by_user.keys()))
    for email in all_emails:
        user_logs = by_user.get(email, [])
        today_actions = 0
        seven_day_actions = 0
        for item in user_logs:
            ts = parse_ts(item.get("timestamp", ""))
            if not ts:
                continue
            if ts.date() == today:
                today_actions += 1
            if ts.date() >= seven_day_cutoff:
                seven_day_actions += 1
        user_flags = [flag for flag in flags if normalize_email(flag.get("user_email")) == email]
        record = users.get(email, default_user_record(email, active=False))
        resource_summary = get_user_resource_snapshot(email)
        rows.append({
            "email": email,
            "status": "active" if record.get("active", False) else "disabled",
            "created_at": record.get("created_at", ""),
            "last_login_at": record.get("last_login_at", ""),
            "last_activity_at": record.get("last_activity_at", ""),
            "estimated_usage_hours_today": _usage_duration_by_days(user_logs, 1),
            "estimated_usage_hours_last_7_days": _usage_duration_by_days(user_logs, 7),
            "total_actions_today": today_actions,
            "total_actions_last_7_days": seven_day_actions,
            "top_used_feature": feature_counter[email].most_common(1)[0][0] if feature_counter[email] else "",
            "account_count": resource_summary["account_count"],
            "total_gold": resource_summary["total_gold"],
            "total_shards": resource_summary["total_shards"],
            "total_wf": resource_summary["total_wf"],
            "suspicious_flag_count": len(user_flags),
            "last_suspicious_reason": user_flags[-1]["reason"] if user_flags else "",
            "admin_note": record.get("admin_note", ""),
        })
    return rows


def notification_recommendations() -> list[str]:
    return [
        "Critical: suspicious behavior, repeated system errors, storage failures, OAuth failures, repeated price API failures.",
        "Warning: high action frequency, repeated validation failures, repeated duplicate account/wallet attempts, repeated login blocks.",
        "Info: user added, deactivated, reactivated, or removed from allowlist.",
    ]
