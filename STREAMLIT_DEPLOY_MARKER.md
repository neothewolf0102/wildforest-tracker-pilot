# Streamlit Deploy Marker

Updated: 2026-06-08 15:10 Asia/Bangkok

This marker commit intentionally triggers Streamlit Community Cloud to redeploy after the repository visibility/auth issue.

Expected deploy source:

- Repository: `neothewolf0102/wildforest-tracker-pilot`
- Branch: `main`
- Main file: `app.py`

Expected UI for the current GitHub pilot source:

- Top-tab app, not Streamlit multipage sidebar.
- No `pages/` folder in deploy source.
- Hidden tabs: WF price history, Game Configuration, Export.

Root-cause note:

- GitHub API still reported repository visibility as `private` during verification, which can block Streamlit Cloud from pulling the latest commit unless the app is reconnected/rebooted with GitHub access.
- The local full app under `E:\Wildforest\Apps1\Wildforest Tracker - GLOBAL STAGING` is not yet fully mirrored into this GitHub repo because the repo is missing its supporting modules.
