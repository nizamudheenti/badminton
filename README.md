# PPL Season 2 — Badminton Schedule Viewer

A Streamlit app to browse the group-stage and quarterfinal schedule:
court-grid timeline, filterable match list, referee load view, and per-team fixtures.

## Files
- `app.py` — the Streamlit application
- `schedule_data.json` — the schedule data (regenerated from the planning workbook)
- `requirements.txt` — dependencies

## Run locally
```bash
pip install -r requirements.txt
streamlit run app.py
```
Then open the URL it prints (usually http://localhost:8501).

## Deploy on Streamlit Community Cloud
1. Push `app.py`, `schedule_data.json`, and `requirements.txt` to a GitHub repo.
2. Go to https://share.streamlit.io, pick the repo, and set the main file to `app.py`.

## Features
- **Category + Team selectors** at the top drive the whole view — pick a discipline and/or a franchise to see exactly when they play.
- **Timings** — match start/end times grouped by session, focused on the current Category/Team.
- **Court Grid** — time × court layout per session, team-coloured match chips.
- **List** — filterable table with team badges.
- Secondary filters (sidebar): court and player search.

## Updating the data
`schedule_data.json` holds every match (`day, session, start/end, court, discipline,
stage, pair + team for each side`). Replace it (same shape) to refresh the app.
