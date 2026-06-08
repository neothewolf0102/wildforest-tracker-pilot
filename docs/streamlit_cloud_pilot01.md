# Streamlit Community Cloud Pilot 01 Deployment

## Target

- Host `app.py` on Streamlit Community Cloud.
- Users access one public Streamlit URL.
- Users login with Google.
- Each user's data boundary is the authenticated Google account.
- No global shared user data storage is used for Pilot 01.
- Pilot 01 supports 4 Google test users operationally, without hardcoding a 4-user limit.
- Each Google user can create up to 5 Wildforest accounts.
- Total Pilot 01 operational capacity is 20 Wildforest accounts.

## Google OAuth Client

Create a Google OAuth client:

- Application type: Web application
- Authorized redirect URI: the deployed Streamlit URL
- Scopes: `openid`, `email`, `profile`, `https://www.googleapis.com/auth/drive.file`

Do not request full Google Drive access.

## Streamlit Secrets

Set these in Streamlit Community Cloud secrets:

```toml
GOOGLE_CLIENT_ID = "..."
GOOGLE_CLIENT_SECRET = "..."
GOOGLE_REDIRECT_URI = "https://your-app.streamlit.app"
GOOGLE_SCOPES = "openid email profile https://www.googleapis.com/auth/drive.file"
APP_DRIVE_FOLDER_NAME = "Wildforest Tracker"
```

Do not commit real secrets. Use `.streamlit/secrets.toml.example` only as a template.

## Pilot Pages

Enabled: Accounts, Tickets, Resources, Daily Actions, KPI Dashboard.

Hidden/locked: OCR, Level Simulation, AI Assistant, Payment, Admin dashboard.

## Acceptance Test

1. User A logs in and creates one account.
2. User B logs in with another Gmail and sees no User A data.
3. User A logs in from another machine and sees the saved account once Drive persistence is enabled.
4. Export CSV/Excel writes reports under the user's app storage boundary.
5. A user can create 5 accounts.
6. Creating a 6th account is blocked with `Pilot limit reached: maximum 5 accounts per user.`
