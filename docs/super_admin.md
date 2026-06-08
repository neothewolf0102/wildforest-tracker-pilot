# Super Admin Controls

Super admin email: `firmstoney@gmail.com`.

## User Access

The super admin panel can:

- Switch between `Open except blocked` and `Allowlist only` pilot access mode.
- Activate a Gmail address.
- Deactivate/block a Gmail address.
- Always keep `firmstoney@gmail.com` active.

Pilot users still keep the Pilot 01 account cap: maximum 5 Wildforest accounts per user.

## Logs

The admin panel shows:

- Usage summary by Gmail.
- First seen / last seen.
- Approximate session duration.
- Event count.
- Top logged feature.
- Suspicious flags such as high event frequency, long sessions, and repeated errors.
- Raw audit events.
- System error log table.

## Notification Recommendations

Recommended notifications for the super admin:

- A non-allowlisted Gmail attempts access while allowlist mode is enabled.
- A blocked Gmail continues attempting to access the app.
- A user creates/edits data unusually often in a short window.
- System errors spike for one user or one feature.
- A session exceeds expected daily usage, for example more than 8 hours.
- A user approaches Pilot account capacity.

## Storage Note

User game data remains scoped to each pilot user's storage boundary. Admin audit data is intentionally minimal and should not include user secrets or OAuth tokens.

For production durability across Streamlit restarts/redeploys, replace the current runtime admin cache with a durable admin-owned Google Drive folder or database-backed audit store.
