# Super Admin Controls

Super admin email: `firmstoney@gmail.com`.

The admin must sign in with Gmail. There is no separate admin password.

## Storage Model

Pilot storage remains split by responsibility:

- User game data: stored under each pilot user's own storage boundary.
- Admin access control and admin logs: stored through the signed-in super admin storage boundary.

When `firmstoney@gmail.com` is signed in and the app is using Google Drive storage, these files are saved in that admin-owned Drive app folder:

- `admin/access_control.json`
- `admin/audit_logs.json`
- `admin/system_errors.json`

No secrets, OAuth tokens, client secrets, or `.env` files should be written to these logs.

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

## Production Note

Google Drive admin-owned storage is the recommended Pilot 01 storage path because it matches the Gmail/Drive model and avoids operating a database too early.

If the pilot grows beyond light usage or needs stronger query/reporting guarantees, migrate these admin files to a managed database such as Postgres/Supabase. Do not use local Streamlit filesystem storage for durable admin records.
