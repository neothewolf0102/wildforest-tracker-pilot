# Wildforest Tracker Pilot 01

Streamlit web pilot for tracking Wildforest accounts, tickets, resources, daily actions, and KPI/ROI summaries.

## Pilot 01 Scope

- Google login entry point for Pilot users.
- Per-user storage boundary designed for Google Drive with the minimum `drive.file` scope.
- Up to 5 Wildforest accounts per Google user.
- Enabled pages: Accounts, Tickets, Resources, Daily Actions, KPI Dashboard.
- Hidden for Pilot 01: OCR, Level Simulation, AI Assistant, Payment, Admin dashboard.

## Streamlit Structure

```text
app.py
pages/
services/
models/
ui/
.streamlit/
  config.toml
  secrets.toml.example
requirements.txt
tests/
```

## Local Run

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## Streamlit Cloud Setup

Add the values from `.streamlit/secrets.toml.example` to Streamlit Community Cloud secrets. Do not commit real secrets, OAuth tokens, local user data, generated QA reports, or backup snapshots.

See `docs/streamlit_cloud_pilot01.md` for deployment and acceptance-test details.
