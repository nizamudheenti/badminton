"""
PPL Season 2 - Badminton Schedule Viewer
Run locally:   streamlit run app.py
Deploy:        push app.py + schedule_data.json + requirements.txt to a repo,
               then deploy on https://share.streamlit.io
"""
import io
import json
from collections import OrderedDict
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

# ----------------------------------------------------------------------------- data
st.set_page_config(page_title="PPL S2 Badminton Schedule", page_icon="🏸", layout="wide")
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

# ----------------------------------------------------------------------------- scores
SCORE_XLSX = Path(__file__).parent / "scores.xlsx"
SCORE_CSV = Path(__file__).parent / "scores.csv"

# Columns written to / read from the score sheet. The first block is read-only
# context so you know which match each row is; the SET_COLS are the ones you edit.
REF_COLS = [
    "match_id", "Day", "Time", "Court", "Category", "Stage",
    "Pair 1", "Team 1", "Pair 2", "Team 2",
]
SET_COLS = ["P1 S1", "P2 S1", "P1 S2", "P2 S2", "P1 S3", "P2 S3"]


def _as_int(value):
    """Best-effort int from a spreadsheet cell; blank/garbage -> None."""
    if value is None:
        return None
    try:
        if isinstance(value, float) and pd.isna(value):
            return None
    except Exception:  # noqa: BLE001
        pass
    s = str(value).strip()
    if s == "" or s.lower() in ("nan", "none"):
        return None
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return None


def build_template_df():
    """One row per match with empty score columns, ready to fill in Excel."""
    rows = []
    for m in sorted(MATCHES, key=lambda x: (x["day"], x["start"], x["court"])):
        row = {
            "match_id": m["id"],
            "Day": m["day"],
            "Time": f"{m['start_str']} - {m['end_str']}",
            "Court": m["court"],
            "Category": m["discipline"],
            "Stage": m["stage"],
            "Pair 1": m.get("p1"),
            "Team 1": m.get("t1"),
            "Pair 2": m.get("p2"),
            "Team 2": m.get("t2"),
        }
        for col in SET_COLS:
            row[col] = None
        rows.append(row)
    return pd.DataFrame(rows, columns=REF_COLS + SET_COLS)


def template_xlsx_bytes():
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        build_template_df().to_excel(writer, index=False, sheet_name="Scores")
    return buf.getvalue()


def parse_scores(df):
    """DataFrame (from xlsx/csv) -> {match_id: [(p1,p2), ...] per played set}."""
    out = {}
    if df is None or df.empty or "match_id" not in df.columns:
        return out
    for _, r in df.iterrows():
        mid = _as_int(r.get("match_id"))
        if mid is None:
            continue
        sets = []
        for i in (1, 2, 3):
            a = _as_int(r.get(f"P1 S{i}"))
            b = _as_int(r.get(f"P2 S{i}"))
            if a is not None and b is not None:
                sets.append((a, b))
        if sets:
            out[mid] = sets
    return out


def load_scores():
    """Read scores from scores.xlsx (preferred) or scores.csv if present."""
    try:
        if SCORE_XLSX.exists():
            return parse_scores(pd.read_excel(SCORE_XLSX, sheet_name=0))
        if SCORE_CSV.exists():
            return parse_scores(pd.read_csv(SCORE_CSV))
    except Exception as e:  # noqa: BLE001
        st.warning(f"Could not read score file: {e}")
    return {}


def match_result(m, scores):
    """Compute the outcome of one match from its recorded sets."""
    sets = scores.get(m["id"])
    if not sets:
        return {"played": False}
    pf1 = sum(a for a, b in sets)
    pf2 = sum(b for a, b in sets)
    w1 = sum(1 for a, b in sets if a > b)
    w2 = sum(1 for a, b in sets if b > a)
    winner = "p1" if w1 > w2 else "p2" if w2 > w1 else None
    return {
        "played": True,
        "sets": sets,
        "pf1": pf1, "pf2": pf2,
        "w1": w1, "w2": w2,
        "winner": winner,
        "score_str": ", ".join(f"{a}-{b}" for a, b in sets),
    }


def group_standings(discipline, stage, scores):
    """Build a ranked standings table for one (discipline, group)."""
    matches = [
        m for m in MATCHES
        if m["discipline"] == discipline and m["stage"] == stage
    ]
    stats = OrderedDict()  # pair label -> stat dict

    def slot(pair, team):
        if pair not in stats:
            stats[pair] = {
                "pair": pair, "team": team,
                "played": 0, "won": 0, "lost": 0,
                "pf": 0, "pa": 0, "pts": 0,
            }
        return stats[pair]

    h2h = {}  # (winner_pair, loser_pair) -> True
    for m in matches:
        if not (m.get("p1") and m.get("p2")):
            continue
        a = slot(m["p1"], m.get("t1"))
        b = slot(m["p2"], m.get("t2"))
        res = match_result(m, scores)
        if not res["played"]:
            continue
        a["played"] += 1
        b["played"] += 1
        a["pf"] += res["pf1"]; a["pa"] += res["pf2"]
        b["pf"] += res["pf2"]; b["pa"] += res["pf1"]
        if res["winner"] == "p1":
            a["won"] += 1; b["lost"] += 1
            a["pts"] += 2
            h2h[(m["p1"], m["p2"])] = True
        elif res["winner"] == "p2":
            b["won"] += 1; a["lost"] += 1
            b["pts"] += 2
            h2h[(m["p2"], m["p1"])] = True

    teams = list(stats.values())
    if not teams:
        return []

    def tiebreak_key(s):
        return (-(s["pf"] - s["pa"]), -s["pf"], s["pa"])

    # Bucket by match points, then resolve within each bucket.
    teams.sort(key=lambda s: -s["pts"])
    ordered = []
    i = 0
    while i < len(teams):
        j = i
        while j < len(teams) and teams[j]["pts"] == teams[i]["pts"]:
            j += 1
        bucket = teams[i:j]
        if len(bucket) == 2:
            x, y = bucket
            if h2h.get((x["pair"], y["pair"])):
                bucket = [x, y]
            elif h2h.get((y["pair"], x["pair"])):
                bucket = [y, x]
            else:
                bucket.sort(key=tiebreak_key)
        else:
            bucket.sort(key=tiebreak_key)
        ordered.extend(bucket)
        i = j

    for rank, s in enumerate(ordered, start=1):
        s["rank"] = rank
        s["pd"] = s["pf"] - s["pa"]
    return ordered

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

      .pair .sc {
        background: #eef3ef;
        border-radius: 6px;
        color: var(--ink);
        font-size: 0.82rem;
        font-weight: 850;
        margin-left: auto;
        padding: 0.05rem 0.4rem;
      }

      .pair.winner {
        color: var(--accent-strong);
        font-weight: 850;
      }

      .pair.winner .sc {
        background: var(--accent);
        color: #ffffff;
      }

      .chip-foot .score {
        color: var(--accent-strong);
        font-weight: 800;
      }

      .chip-foot .no-score {
        color: var(--soft);
        font-style: italic;
        font-weight: 650;
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
courts = sorted({m["court"] for m in MATCHES})
pair_teams = sorted(
    {
        f"{m['p1']} ({m['t1']})"
        for m in MATCHES
        if m.get("p1") and m.get("t1")
    }
    |
    {
        f"{m['p2']} ({m['t2']})"
        for m in MATCHES
        if m.get("p2") and m.get("t2")
    }
)

st.markdown("<div class='filter-label'>Filters</div>", unsafe_allow_html=True)
cc1, cc2, cc3 = st.columns([1.5, 1.8, 1])

with cc1:
    cat = st.radio(
        "Category",
        ["All categories"] + discs,
        horizontal=True,
    )

def get_pair_options(selected_category):
    pairs = set()

    for m in MATCHES:
        if (
            selected_category != "All categories"
            and m["discipline"] != selected_category
        ):
            continue

        if m.get("p1") and m.get("t1"):
            pairs.add(f"{m['p1']} ({m['t1']})")

        if m.get("p2") and m.get("t2"):
            pairs.add(f"{m['p2']} ({m['t2']})")

    return sorted(pairs)

pair_options = get_pair_options(cat)

with cc2:
    pair_team = st.selectbox(
        "Player Pair",
        ["All pairs"] + pair_options,
    )

with cc3:
    stage = st.radio(
        "Stage",
        ["All", "Group stage", "Quarterfinals"],
        horizontal=True,
    )


def keep(m):
    if cat != "All categories" and m["discipline"] != cat:
        return False

    if pair_team != "All pairs":
        left_pair = f"{m['p1']} ({m['t1']})"
        right_pair = f"{m['p2']} ({m['t2']})"

        if pair_team not in (left_pair, right_pair):
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


def chip_html(m, highlight_team=None, highlight_player=None, result=None):
    accent = DISC_ACCENT.get(m["discipline"], "#90a4ae")
    soft = accent + "14"
    tag = f"{DISC_ABBR.get(m['discipline'], '?')} {m['stage']}"
    c1 = TEAM_COLORS.get(m.get("t1"), "#94A3B8")
    c2 = TEAM_COLORS.get(m.get("t2"), "#94A3B8")
    pair1 = f"{m['p1']} ({m['t1']})"
    pair2 = f"{m['p2']} ({m['t2']})"

    side_1_selected = (highlight_player and highlight_player == pair1)

    side_2_selected = (highlight_player and highlight_player == pair2)
    selected_1 = " selected" if side_1_selected else ""
    selected_2 = " selected" if side_2_selected else ""

    win_1 = win_2 = ""
    sc_1 = sc_2 = ""
    foot_score = "<span class='no-score'>Not played</span>"
    if result and result.get("played"):
        if result["winner"] == "p1":
            win_1 = " winner"
        elif result["winner"] == "p2":
            win_2 = " winner"
        # points scored by each side across all sets
        sc_1 = f"<span class='sc'>{h(result['pf1'])}</span>"
        sc_2 = f"<span class='sc'>{h(result['pf2'])}</span>"
        foot_score = f"<span class='score'>{h(result['score_str'])}</span>"

    highlight = " highlight" if side_1_selected or side_2_selected else ""
    return (
        f"<div class='chip{highlight}' style='--chip-accent:{h(accent)}; --chip-soft:{h(soft)};'>"
        f"<div class='tag'>{h(tag)}</div>"
        f"<div class='pair{selected_1}{win_1}'><span class='dot' style='background:{h(c1)}'></span>{h(m['p1'])}{sc_1}</div>"
        f"<div class='vs'>vs</div>"
        f"<div class='pair{selected_2}{win_2}'><span class='dot' style='background:{h(c2)}'></span>{h(m['p2'])}{sc_2}</div>"
        f"<div class='chip-foot'><span>Court {h(m['court'])}</span>{foot_score}</div>"
        f"</div>"
    )


sessions = total_sessions
head = "All categories" if cat == "All categories" else f"{cat}"
if pair_team != "All pairs":
    head += f" - {pair_team}"
if stage != "All":
    head += f" - {stage}"

# Resolve the active score source: an uploaded file takes priority for this
# session, otherwise read scores.xlsx / scores.csv sitting next to app.py.
SCORES = st.session_state.get("uploaded_scores")
if SCORES is None:
    SCORES = load_scores()

tab_time, tab_grid, tab_list, tab_stand, tab_rules = st.tabs(
    ["Timings", "Court Grid", "List", "Standings", "Rules"]
)

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
                    hp = pair_team if pair_team != "All pairs" else None
                    inner[i % 3].markdown(
                        chip_html(m, highlight_player=hp, result=match_result(m, SCORES)),
                        unsafe_allow_html=True,
                    )

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
                        hp = pair_team if pair_team != "All pairs" else None
                        cols[idx + 1].markdown(
                            chip_html(cell, highlight_player=hp, result=match_result(cell, SCORES)),
                            unsafe_allow_html=True,
                        )
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
        def list_row(m):
            res = match_result(m, SCORES)
            if res["played"]:
                if res["winner"] == "p1":
                    won = f"{m['p1']}"
                elif res["winner"] == "p2":
                    won = f"{m['p2']}"
                else:
                    won = "Tie"
                score = res["score_str"]
            else:
                won = ""
                score = "—"
            return {
                "Day": m["day"],
                "Session": m["session"],
                "Time": f"{m['start_str']} - {m['end_str']}",
                "Court": f"Court {m['court']}",
                "Category": m["discipline"],
                "Stage": m["stage"],
                "Match": f"{m['p1']} vs {m['p2']}",
                "Teams": f"{m.get('t1') or 'TBD'} / {m.get('t2') or 'TBD'}",
                "Score": score,
                "Winner": won,
            }

        rows = [list_row(m) for m in view]
        st.dataframe(
            rows,
            width="stretch",
            hide_index=True,
            height=min(720, 38 * (len(rows) + 1)),
            column_config={
                "Match": st.column_config.TextColumn("Match", width="large"),
                "Teams": st.column_config.TextColumn("Teams", width="medium"),
                "Score": st.column_config.TextColumn("Score", width="small"),
                "Winner": st.column_config.TextColumn("Winner", width="medium"),
            },
        )
# --- Standings --------------------------------------------------------------
with tab_stand:
    st.markdown(
        (
            "<div class='view-title'>"
            "<h3>Group Standings</h3>"
            f"<span class='match-count'>{h(len(SCORES))} matches scored</span>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )

    with st.expander("How to update scores", expanded=not SCORES):
        st.markdown(
            "1. **Download** the score sheet below — one row per match.\n"
            "2. Fill in the set scores in Excel: `P1 S1`/`P2 S1` for the single "
            "group set (use `S2`/`S3` columns too for best-of-3 knockouts).\n"
            "3. Save it as **`scores.xlsx`** next to `app.py` (or upload it below "
            "for a quick preview). For the deployed site, commit `scores.xlsx` "
            "to the repo.\n"
            "4. Standings, the **Score** column and the match cards update "
            "automatically. Don't change the `match_id` column."
        )
        dl1, dl2 = st.columns(2)
        dl1.download_button(
            "⬇ Download score sheet (Excel)",
            data=template_xlsx_bytes(),
            file_name="scores.xlsx",
            mime="application/vnd.openpyxlformats-officedocument.spreadsheetml.sheet",
            width="stretch",
        )
        dl2.download_button(
            "⬇ Download score sheet (CSV)",
            data=build_template_df().to_csv(index=False).encode("utf-8"),
            file_name="scores.csv",
            mime="text/csv",
            width="stretch",
        )

        up = st.file_uploader(
            "Preview a filled score sheet (.xlsx or .csv)", type=["xlsx", "csv"]
        )
        if up is not None:
            try:
                df_up = (
                    pd.read_csv(up)
                    if up.name.lower().endswith(".csv")
                    else pd.read_excel(up, sheet_name=0)
                )
                st.session_state["uploaded_scores"] = parse_scores(df_up)
                st.success(f"Loaded {up.name}. Showing scores from this file.")
                st.rerun()
            except Exception as e:  # noqa: BLE001
                st.error(f"Could not read that file: {e}")
        if st.session_state.get("uploaded_scores") is not None:
            if st.button("Clear preview / use scores.xlsx on disk"):
                del st.session_state["uploaded_scores"]
                st.rerun()

    if not SCORES:
        st.info(
            "No scores recorded yet. Download the score sheet above, fill it in, "
            "and save it as scores.xlsx next to app.py."
        )

    # Standings per discipline -> per group (round-robin groups only).
    GROUP_RANK = {"Group W": 0, "Group A": 1, "Group B": 2, "Group C": 3, "Group D": 4}
    for disc in discs:
        groups = sorted(
            {
                m["stage"]
                for m in MATCHES
                if m["discipline"] == disc and str(m["stage"]).startswith("Group")
            },
            key=lambda g: GROUP_RANK.get(g, 99),
        )
        if not groups:
            continue
        st.markdown(
            f"<div class='sess-head'><small>Category</small>{h(disc)}</div>",
            unsafe_allow_html=True,
        )
        cols = st.columns(min(len(groups), 2))
        for gi, grp in enumerate(groups):
            table = group_standings(disc, grp, SCORES)
            target = cols[gi % len(cols)]
            with target:
                st.markdown(f"**{h(grp)}**")
                if not table:
                    st.caption("No pairs found for this group.")
                    continue
                rows = [
                    {
                        "#": s["rank"],
                        "Pair": s["pair"],
                        "Team": s["team"],
                        "P": s["played"],
                        "W": s["won"],
                        "L": s["lost"],
                        "PF": s["pf"],
                        "PA": s["pa"],
                        "PD": s["pd"],
                        "Pts": s["pts"],
                    }
                    for s in table
                ]
                st.dataframe(
                    rows,
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "#": st.column_config.NumberColumn("#", width="small"),
                        "Pair": st.column_config.TextColumn("Pair", width="large"),
                        "Team": st.column_config.TextColumn("Team", width="small"),
                    },
                )
    st.caption(
        "P played · W won · L lost · PF points for · PA points against · "
        "PD point difference · Pts = 2 per win. Ties broken by head-to-head "
        "(2-way), then point difference, points for, then fewest conceded."
    )

# --- Rules ------------------------------------------------------------------
with tab_rules:
    st.markdown(
        """
# PPL Season 2 – Tournament Rules & Regulations

## 1. Tournament Format

The tournament consists of two stages:

* Group Stage
* Knockout Stage

All teams must adhere to the rules and regulations outlined below.


## 2. Group Stage

1. Teams will compete in a round-robin format within their respective groups.
2. Each team will play every other team in its group once.
3. All Group Stage matches will be played as a **single set to 21 points**.
4. Rally scoring will be used throughout the tournament.


## 3. Qualification for Knockout Stages

### Men's Division

1. The Men's Division consists of **4 groups**.
2. The **top 2 teams** from each group will qualify for the Quarter-Finals.
3. A total of **8 teams** will advance to the Knockout Stage.

### Women's Division

1. The Women's Division consists of **1 group with 5 teams**.
2. Each team will play every other team once.
3. The team finishing **1st** in the standings will qualify directly for the **Final**.
4. The teams finishing **2nd** and **3rd** will compete in a **Semi-Final**.
5. The winner of the Semi-Final will advance to the **Final**.
6. Teams finishing **4th** and **5th** will be eliminated.

### Mixed Division

1. The Mixed Division consists of **2 groups**.
2. The **top 2 teams** from each group will qualify for the Semi-Finals.
3. Semi-Final winners will advance to the Final.


## 4. Knockout Stage

### Men's Division

* Quarter-Finals
* Semi-Finals
* Final

### Women's Division

* Semi-Final (2nd vs 3rd)
* Final (1st vs Semi-Final Winner)

### Mixed Division

* Semi-Finals
* Final

All Knockout Stage matches will be played as **Best of 3 sets to 21 points**.


## 5. Scoring System

1. Rally scoring shall be used throughout the tournament.
2. A point is awarded on every rally, regardless of which side served.
3. A set is won by the first team to reach **21 points** with a minimum lead of **2 points**.
4. If the score reaches **20–20**, play shall continue until one team gains a 2-point advantage.
5. If the score reaches **29–29**, the next point shall decide the set.
6. In Knockout Stage matches, the first team to win **2 sets** wins the match.


## 6. Service Rules

1. The initial service shall be decided by a coin toss.
2. The serve must be delivered underhand, with the shuttle struck below the server's waist.
3. Both feet of the server must remain in contact with the court surface until the shuttle is struck.
4. Deliberate distractions, excessive movements, or actions intended to interfere with an opponent's readiness may be deemed faults.
5. Standard badminton service rules shall apply unless otherwise specified by the Tournament Committee.


## 7. Tie-Breaking Criteria

If two or more teams finish the Group Stage with an equal number of points, rankings shall be determined in the following order:

1. **Head-to-Head Result**
2. **Points Difference** (Points Scored − Points Conceded)
3. **Total Points Scored**
4. **Lowest Points Conceded**

The Tournament Committee's decision shall be final if teams remain tied after all criteria have been applied.


## 8. Match Attendance & Walkovers

1. All matches will begin strictly according to the published schedule.
2. Players must report and be ready to play at least **20 minutes before** their scheduled match time.
3. Failure to report on time may result in a **walkover**.
4. Any exceptional circumstances must be communicated to the Tournament Committee immediately.

---

## 9. Player Conduct & Sportsmanship

1. Players are expected to display good sportsmanship at all times.
2. Respect must be shown to opponents, officials, volunteers, and spectators.
3. Unsporting conduct, abusive language, or inappropriate behavior may result in warnings, penalties, or disqualification.
4. Any disputes should be raised through the Team Captain or Tournament Committee.

---

## 10. Safety & Equipment

1. Players must wear appropriate badminton attire and non-marking sports footwear.
2. Players participate at their own risk and are responsible for ensuring they are physically fit to compete.
3. Any injury sustained during the tournament must be reported immediately to the Tournament Committee.
4. The Tournament Committee reserves the right to stop or postpone a match if player safety is at risk.

---

## 11. General Regulations

1. Standard Badminton World Federation (BWF) rules shall apply unless specifically modified by these tournament regulations.
2. The Tournament Committee reserves the right to interpret, amend, and enforce these rules whenever necessary.
3. Any decision made by the Tournament Committee shall be final and binding.
4. Participation in the tournament constitutes acceptance of all tournament rules and regulations.

---

### 🏸 Play Fair • Play Hard • Enjoy the Tournament"""
    )
st.markdown("<div class='footer-note'>PPL Season 2 - Badminton</div>", unsafe_allow_html=True)
