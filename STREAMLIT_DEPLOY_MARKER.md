# Streamlit Deploy Marker

This marker commit intentionally triggers Streamlit Community Cloud to redeploy after the repository was restored to public visibility.

Expected deploy source:

- Repository: `neothewolf0102/wildforest-tracker-pilot`
- Branch: `main`
- Main file: `app.py`

Expected UI:

- Top-tab app, not Streamlit multipage sidebar.
- No `pages/` folder in deploy source.
- Hidden tabs: WF price history, Game Configuration, Export.
