"""
PPL Season 2 - Badminton Schedule Viewer
Run locally:   streamlit run app.py
Deploy:        push app.py + schedule_data.json + requirements.txt to a repo,
               then deploy on https://share.streamlit.io
"""
import json
from collections import OrderedDict
from html import escape
from pathlib import Path

import streamlit as st

# ----------------------------------------------------------------------------- data
st.set_page_config(page_title="PPL S2 Schedule", page_icon="🏸", layout="wide")
DATA_PATH = Path(__file__).parent / "schedule_data.json"


@st.cache_data
def load_data():
    with open(DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


try:
    DATA = load_data()
except Exception as e:  # noqa: BLE001
    st.error(f"Could not load schedule_data.json — keep it next to app.py.  ({e})")
    st.stop()

MATCHES = DATA["matches"]
TEAM_COLORS = DATA["team_colors"]
DISCIPLINE_ORDER = ["Women's", "Men's", "Mixed"]
DISC_ACCENT = {"Women's": "#C43B73", "Men's": "#2563EB", "Mixed": "#15803D"}
DISC_ABBR = {"Women's": "W", "Men's": "M", "Mixed": "X"}


def h(value):
    return escape("" if value is None else str(value), quote=True)


def player_names(pair):
    names = []
    for name in str(pair or "").split(" + "):
        clean_name = name.strip()
        lower_name = clean_name.lower()
        if not clean_name:
            continue
        if lower_name.startswith("group ") or "winner" in lower_name or "runner-up" in lower_name:
            continue
        names.append(clean_name)
    return names

# ----------------------------------------------------------------------------- styles
st.markdown(
    """
    <style>
      :root {
        --paper: #f6f8f4;
        --paper-strong: #edf4ef;
        --panel: #ffffff;
        --ink: #17201f;
        --muted: #64736f;
        --soft: #899792;
        --line: #dce7e1;
        --accent: #0f766e;
        --accent-strong: #0b5f59;
        --gold: #a06107;
      }

      .stApp {
        background: linear-gradient(180deg, var(--paper) 0%, var(--paper-strong) 100%);
        color: var(--ink);
      }

      .block-container {
        max-width: 1360px;
        padding-top: 1rem;
        padding-bottom: 2rem;
      }

      h1, h2, h3, h4, h5, h6, p, label, span, div {
        letter-spacing: 0;
      }

      div[data-testid="stRadio"] > label,
      div[data-testid="stSelectbox"] > label {
        color: var(--ink);
        font-weight: 700;
      }

      .stRadio [role="radiogroup"] {
        gap: 0.35rem;
      }

      .stRadio label {
        background: rgba(255, 255, 255, 0.76);
        border: 1px solid var(--line);
        border-radius: 8px;
        padding: 0.35rem 0.55rem;
      }

      .hero {
        align-items: end;
        border-bottom: 1px solid var(--line);
        color: var(--ink);
        display: grid;
        gap: 1rem;
        grid-template-columns: minmax(0, 1fr) auto;
        margin-bottom: 1rem;
        padding: 0.45rem 0 1.1rem;
      }

      .hero h1 {
        color: var(--ink);
        font-size: 2.2rem;
        line-height: 1.08;
        margin: 0.15rem 0 0.4rem;
      }

      .hero p {
        color: var(--muted);
        font-size: 1rem;
        margin: 0;
      }

      .eyebrow {
        color: var(--accent);
        font-size: 0.78rem;
        font-weight: 800;
        text-transform: uppercase;
      }

      .hero-meta {
        display: grid;
        gap: 0.5rem;
        grid-template-columns: repeat(3, minmax(92px, auto));
      }

      .meta-pill,
      .stat-card {
        background: rgba(255, 255, 255, 0.92);
        border: 1px solid var(--line);
        border-radius: 8px;
        box-shadow: 0 8px 22px rgba(16, 32, 28, 0.06);
      }

      .meta-pill {
        padding: 0.55rem 0.75rem;
      }

      .meta-label,
      .stat-label {
        color: var(--muted);
        display: block;
        font-size: 0.72rem;
        font-weight: 700;
        text-transform: uppercase;
      }

      .meta-value,
      .stat-value {
        color: var(--ink);
        display: block;
        font-weight: 850;
      }

      .meta-value {
        font-size: 1.05rem;
        margin-top: 0.1rem;
      }

      .filter-label {
        color: var(--accent-strong);
        font-size: 0.78rem;
        font-weight: 850;
        margin: 0.2rem 0 0.1rem;
        text-transform: uppercase;
      }

      .summary-grid {
        display: grid;
        gap: 0.75rem;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        margin: 1rem 0 0.75rem;
      }

      .stat-card {
        min-height: 92px;
        padding: 0.85rem 0.95rem;
      }

      .stat-value {
        font-size: 1.55rem;
        line-height: 1.1;
        margin-top: 0.3rem;
      }

      .stat-detail {
        color: var(--soft);
        display: block;
        font-size: 0.82rem;
        margin-top: 0.35rem;
      }

      .legend {
        align-items: center;
        display: flex;
        flex-wrap: wrap;
        gap: 0.45rem 0.75rem;
        margin: 0.35rem 0 1rem;
      }

      .legend-label {
        color: var(--muted);
        font-size: 0.82rem;
        font-weight: 800;
      }

      .legend span.item {
        align-items: center;
        background: rgba(255, 255, 255, 0.76);
        border: 1px solid var(--line);
        border-radius: 999px;
        color: var(--ink);
        display: inline-flex;
        font-size: 0.82rem;
        font-weight: 750;
        gap: 0.4rem;
        padding: 0.28rem 0.55rem;
      }

      .sess-head {
        align-items: center;
        border-top: 1px solid var(--line);
        color: var(--ink);
        display: flex;
        font-size: 1rem;
        font-weight: 850;
        gap: 0.7rem;
        margin: 1rem 0 0.55rem;
        padding-top: 0.85rem;
      }

      .sess-head small {
        color: var(--muted);
        font-size: 0.84rem;
        font-weight: 700;
      }

      .chip {
        background: var(--panel);
        border: 1px solid var(--line);
        border-left: 4px solid var(--chip-accent);
        border-radius: 8px;
        box-shadow: 0 8px 22px rgba(16, 32, 28, 0.06);
        height: 100%;
        min-height: 156px;
        padding: 0.75rem;
      }

      .chip.highlight {
        border-color: rgba(15, 118, 110, 0.42);
        box-shadow: 0 10px 26px rgba(15, 118, 110, 0.13);
      }

      .chip .tag {
        align-items: center;
        background: var(--chip-soft);
        border-radius: 999px;
        color: var(--chip-accent);
        display: inline-flex;
        font-size: 0.74rem;
        font-weight: 850;
        margin-bottom: 0.55rem;
        padding: 0.25rem 0.5rem;
        text-transform: uppercase;
      }

      .pair {
        align-items: center;
        color: var(--ink);
        display: flex;
        font-size: 0.9rem;
        font-weight: 720;
        gap: 0.45rem;
        line-height: 1.28;
        margin: 0.18rem 0;
        overflow-wrap: anywhere;
      }

      .pair.selected {
        background: rgba(15, 118, 110, 0.08);
        border-radius: 6px;
        margin-left: -0.25rem;
        margin-right: -0.25rem;
        padding: 0.15rem 0.25rem;
      }

      .dot {
        border-radius: 50%;
        box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.12);
        flex: 0 0 auto;
        height: 0.65rem;
        width: 0.65rem;
      }

      .vs {
        color: var(--soft);
        font-size: 0.72rem;
        font-weight: 850;
        margin: 0.1rem 0 0.1rem 1.12rem;
        text-transform: uppercase;
      }

      .chip-foot {
        border-top: 1px solid #eef3ef;
        color: var(--muted);
        display: flex;
        flex-wrap: wrap;
        font-size: 0.76rem;
        font-weight: 700;
        gap: 0.25rem 0.7rem;
        justify-content: space-between;
        margin-top: 0.65rem;
        padding-top: 0.5rem;
      }

      .timecell {
        color: var(--ink);
        font-size: 0.9rem;
        font-weight: 850;
        padding-top: 0.65rem;
      }

      .when {
        color: var(--ink);
        font-size: 0.9rem;
        font-weight: 850;
        padding-top: 0.65rem;
      }

      .when small {
        color: var(--muted);
        display: block;
        font-size: 0.78rem;
        font-weight: 650;
        margin-top: 0.12rem;
      }

      .empty {
        align-items: center;
        background: rgba(255, 255, 255, 0.48);
        border: 1px solid var(--line);
        border-radius: 8px;
        color: var(--soft);
        display: flex;
        font-size: 0.82rem;
        font-weight: 750;
        justify-content: center;
        min-height: 156px;
      }

      .view-title {
        align-items: end;
        display: flex;
        gap: 1rem;
        justify-content: space-between;
        margin: 0.8rem 0 0.65rem;
      }

      .view-title h3 {
        color: var(--ink);
        font-size: 1.15rem;
        line-height: 1.2;
        margin: 0;
      }

      .match-count {
        background: #fffaf0;
        border: 1px solid #f4d49a;
        border-radius: 999px;
        color: var(--gold);
        font-size: 0.82rem;
        font-weight: 800;
        padding: 0.32rem 0.6rem;
        white-space: nowrap;
      }

      .stTabs [data-baseweb="tab-list"] {
        gap: 0.45rem;
      }

      .stTabs [data-baseweb="tab"] {
        background: rgba(255, 255, 255, 0.72);
        border: 1px solid var(--line);
        border-radius: 8px;
        color: var(--ink);
        font-weight: 800;
        padding: 0.45rem 0.85rem;
      }

      .footer-note {
        border-top: 1px solid var(--line);
        color: var(--muted);
        font-size: 0.78rem;
        margin-top: 1.4rem;
        padding-top: 0.8rem;
      }

      @media (max-width: 760px) {
        .hero {
          grid-template-columns: 1fr;
        }

        .hero h1 {
          font-size: 1.72rem;
        }

        .hero-meta,
        .summary-grid {
          grid-template-columns: repeat(2, minmax(0, 1fr));
        }

        .view-title {
          align-items: flex-start;
          flex-direction: column;
          gap: 0.45rem;
        }
      }
    </style>
    """,
    unsafe_allow_html=True,
)

total_sessions = list(OrderedDict.fromkeys((m["day"], m["session"]) for m in MATCHES))
total_start = min(MATCHES, key=lambda m: m["start"])["start_str"]
total_end = max(MATCHES, key=lambda m: m["end"])["end_str"]

st.markdown(
    (
        "<div class='hero'>"
        "<div>"
        "<div class='eyebrow'>Schedule viewer</div>"
        f"<h1>{h(DATA['title'])}</h1>"
        f"<p>{h(DATA['subtitle'])} &middot; {h(len(MATCHES))} scheduled matches</p>"
        "</div>"
        "<div class='hero-meta'>"
        f"<div class='meta-pill'><span class='meta-label'>Courts</span><span class='meta-value'>{h(DATA['courts'])}</span></div>"
        f"<div class='meta-pill'><span class='meta-label'>Sessions</span><span class='meta-value'>{h(len(total_sessions))}</span></div>"
        f"<div class='meta-pill'><span class='meta-label'>Window</span><span class='meta-value'>{h(total_start)} - {h(total_end)}</span></div>"
        "</div>"
        "</div>"
    ),
    unsafe_allow_html=True,
)

# ----------------------------------------------------------------------------- primary selectors: CATEGORY + TEAM
present_discs = {m["discipline"] for m in MATCHES}
discs = [d for d in DISCIPLINE_ORDER if d in present_discs]
discs += sorted(present_discs - set(discs))
teams = sorted({t for m in MATCHES for t in (m["t1"], m["t2"]) if t})
courts = sorted({m["court"] for m in MATCHES})
players = sorted(
    {
        player
        for m in MATCHES
        for pair in (m["p1"], m["p2"])
        for player in player_names(pair)
    }
)

st.markdown("<div class='filter-label'>Filters</div>", unsafe_allow_html=True)
cc1, cc2, cc3, cc4 = st.columns([1.35, 1, 1.35, 1])
with cc1:
    cat = st.radio("Category", ["All categories"] + discs, horizontal=True)
with cc2:
    team = st.selectbox("Team", ["All teams"] + teams)
with cc3:
    player = st.selectbox("Player", ["All players"] + players)
with cc4:
    stage = st.radio("Stage", ["All", "Group stage", "Quarterfinals"], horizontal=True)


def keep(m):
    if cat != "All categories" and m["discipline"] != cat:
        return False
    if team != "All teams" and team not in (m["t1"], m["t2"]):
        return False
    if player != "All players" and player not in player_names(m["p1"]) + player_names(m["p2"]):
        return False
    if stage == "Group stage" and m["stage"] == "Quarterfinal":
        return False
    if stage == "Quarterfinals" and m["stage"] != "Quarterfinal":
        return False
    return True


view = [m for m in MATCHES if keep(m)]
view.sort(key=lambda x: (x["day"], x["start"], x["court"]))

# ----------------------------------------------------------------------------- metrics
def stat_card(label, value, detail=""):
    detail_html = f"<span class='stat-detail'>{h(detail)}</span>" if detail else ""
    return (
        "<div class='stat-card'>"
        f"<span class='stat-label'>{h(label)}</span>"
        f"<span class='stat-value'>{h(value)}</span>"
        f"{detail_html}</div>"
    )


def legend_html():
    items = " ".join(
        f"<span class='item'><span class='dot' style='background:{h(c)}'></span>{h(t)}</span>"
        for t, c in TEAM_COLORS.items()
    )
    return f"<div class='legend'><span class='legend-label'>Teams</span>{items}</div>"


view_window = f"{view[0]['start_str']} - {view[-1]['end_str']}" if view else "None"
active_courts = len({m["court"] for m in view}) if view else 0
group_count = sum(1 for m in view if m["stage"] != "Quarterfinal")
qf_count = sum(1 for m in view if m["stage"] == "Quarterfinal")

st.markdown(
    (
        "<div class='summary-grid'>"
        f"{stat_card('Matches shown', len(view), f'{len(MATCHES)} total scheduled')}"
        f"{stat_card('Group stage', group_count, 'Filtered group matches')}"
        f"{stat_card('Quarterfinals', qf_count, 'Filtered knockout matches')}"
        f"{stat_card('Active courts', active_courts, view_window)}"
        "</div>"
    ),
    unsafe_allow_html=True,
)

st.markdown(legend_html(), unsafe_allow_html=True)


def chip_html(m, highlight_team=None, highlight_player=None):
    accent = DISC_ACCENT.get(m["discipline"], "#90a4ae")
    soft = accent + "14"
    tag = f"{DISC_ABBR.get(m['discipline'], '?')} {m['stage']}"
    c1 = TEAM_COLORS.get(m.get("t1"), "#94A3B8")
    c2 = TEAM_COLORS.get(m.get("t2"), "#94A3B8")
    side_1_selected = (
        (highlight_team and m.get("t1") == highlight_team)
        or (highlight_player and highlight_player in player_names(m["p1"]))
    )
    side_2_selected = (
        (highlight_team and m.get("t2") == highlight_team)
        or (highlight_player and highlight_player in player_names(m["p2"]))
    )
    selected_1 = " selected" if side_1_selected else ""
    selected_2 = " selected" if side_2_selected else ""
    highlight = " highlight" if selected_1 or selected_2 else ""
    return (
        f"<div class='chip{highlight}' style='--chip-accent:{h(accent)}; --chip-soft:{h(soft)};'>"
        f"<div class='tag'>{h(tag)}</div>"
        f"<div class='pair{selected_1}'><span class='dot' style='background:{h(c1)}'></span>{h(m['p1'])}</div>"
        f"<div class='vs'>vs</div>"
        f"<div class='pair{selected_2}'><span class='dot' style='background:{h(c2)}'></span>{h(m['p2'])}</div>"
        f"<div class='chip-foot'><span>Court {h(m['court'])}</span></div>"
        f"</div>"
    )


sessions = total_sessions
head = "All categories" if cat == "All categories" else f"{cat}"
if team != "All teams":
    head += f" - {team}"
if player != "All players":
    head += f" - {player}"
if stage != "All":
    head += f" - {stage}"

tab_time, tab_grid, tab_list = st.tabs(["Timings", "Court Grid", "List"])

# --- Timings (category + team focused) --------------------------------------
with tab_time:
    if not view:
        st.info("No matches for the selected filters.")
    else:
        st.markdown(
            (
                "<div class='view-title'>"
                f"<h3>{h(head)}</h3>"
                f"<span class='match-count'>{h(len(view))} matches</span>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )
        for (day, session) in sessions:
            rs = [m for m in view if m["day"] == day and m["session"] == session]
            if not rs:
                continue
            st.markdown(
                f"<div class='sess-head'><small>Day {h(day)}</small>{h(session)}<small>{h(len(rs))} matches</small></div>",
                unsafe_allow_html=True,
            )
            by_time = OrderedDict()
            for m in rs:
                by_time.setdefault((m["start_str"], m["end_str"]), []).append(m)
            for (s_str, e_str), ms in by_time.items():
                left, right = st.columns([1, 5])
                left.markdown(
                    f"<div class='when'>{s_str}<small>{e_str}</small></div>",
                    unsafe_allow_html=True,
                )
                inner = right.columns(min(len(ms), 3))
                for i, m in enumerate(ms):
                    hl = team if team != "All teams" else None
                    hp = player if player != "All players" else None
                    inner[i % 3].markdown(chip_html(m, hl, hp), unsafe_allow_html=True)

# --- Court Grid -------------------------------------------------------------
with tab_grid:
    if not view:
        st.info("No matches for the selected filters.")
    else:
        grid_courts = courts
        st.markdown(
            (
                "<div class='view-title'>"
                f"<h3>{h(head)}</h3>"
                f"<span class='match-count'>{h(len(view))} matches</span>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )
        for (day, session) in sessions:
            rs = [m for m in view if m["day"] == day and m["session"] == session]
            if not rs:
                continue
            st.markdown(
                f"<div class='sess-head'><small>Day {h(day)}</small>{h(session)}<small>{h(len(rs))} matches</small></div>",
                unsafe_allow_html=True,
            )
            times = sorted({(m["start"], m["start_str"], m["end_str"]) for m in rs})
            header_cols = st.columns([1] + [3] * len(grid_courts))
            header_cols[0].markdown("**Time**")
            for idx, court_no in enumerate(grid_courts):
                header_cols[idx + 1].markdown(f"**Court {court_no}**")
            for start, s_str, e_str in times:
                cols = st.columns([1] + [3] * len(grid_courts))
                cols[0].markdown(
                    f"<div class='timecell'>{h(s_str)}<br><span style='font-weight:650;color:#64736f'>{h(e_str)}</span></div>",
                    unsafe_allow_html=True,
                )
                for idx, court_no in enumerate(grid_courts):
                    cell = next((m for m in rs if m["court"] == court_no and m["start"] == start), None)
                    if cell:
                        hl = team if team != "All teams" else None
                        hp = player if player != "All players" else None
                        cols[idx + 1].markdown(chip_html(cell, hl, hp), unsafe_allow_html=True)
                    else:
                        cols[idx + 1].markdown("<div class='empty'>Open</div>", unsafe_allow_html=True)

# --- List -------------------------------------------------------------------
with tab_list:
    st.markdown(
        (
            "<div class='view-title'>"
            f"<h3>{h(head)}</h3>"
            f"<span class='match-count'>{h(len(view))} matches</span>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )
    if not view:
        st.info("No matches for the selected filters.")
    else:
        rows = [
            {
                "Day": m["day"],
                "Session": m["session"],
                "Time": f"{m['start_str']} - {m['end_str']}",
                "Court": f"Court {m['court']}",
                "Category": m["discipline"],
                "Stage": m["stage"],
                "Match": f"{m['p1']} vs {m['p2']}",
                "Teams": f"{m.get('t1') or 'TBD'} / {m.get('t2') or 'TBD'}",
            }
            for m in view
        ]
        st.dataframe(
            rows,
            width="stretch",
            hide_index=True,
            height=min(720, 38 * (len(rows) + 1)),
            column_config={
                "Match": st.column_config.TextColumn("Match", width="large"),
                "Teams": st.column_config.TextColumn("Teams", width="medium"),
            },
        )

st.markdown("<div class='footer-note'>PPL Season 2 schedule viewer</div>", unsafe_allow_html=True)
