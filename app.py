"""
PPL Season 2 - Badminton Schedule Viewer
Run locally:   streamlit run app.py
Deploy:        push app.py + schedule_data.json + requirements.txt to a repo,
               then deploy on https://share.streamlit.io
"""
import json
import re
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
KNOCKOUT_STAGES = {"Quarterfinal", "Semifinal", "Final"}


def h(value):
    return escape("" if value is None else str(value), quote=True)

# ----------------------------------------------------------------------------- scores
SCORE_XLSX = Path(__file__).parent / "scores.xlsx"
SCORE_CSV = Path(__file__).parent / "scores.csv"

# scores.xlsx columns: match_id (the key — don't change it) plus the editable
# score cells P1 S1/P2 S1 .. P1 S3/P2 S3 (set 1 for group play, sets 2-3 for
# best-of-3 knockouts). Other columns are just context.


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


def resolve_bracket(scores):
    """Fill knockout placeholders from results, in dependency order.

    Groups complete -> QF / Women's SF participants (from standings).
    QFs complete    -> Semifinal participants (QF winners).
    Semis complete  -> Final participants (SF winners).

    Returns {match_id: {"p1","t1","p2","t2"}} with real pairs where known
    and the original placeholder text where not yet decided.
    """
    by_id = {m["id"]: m for m in MATCHES}
    eff = {
        m["id"]: {"p1": m["p1"], "t1": m.get("t1"), "p2": m["p2"], "t2": m.get("t2")}
        for m in MATCHES
    }
    # which sides hold a real (decided) pair — group/crossover are real upfront
    done = {
        m["id"]: {"p1": m["stage"] not in KNOCKOUT_STAGES,
                  "p2": m["stage"] not in KNOCKOUT_STAGES}
        for m in MATCHES
    }

    def set_side(mid, side, pair, team):
        eff[mid][side] = pair
        eff[mid]["t1" if side == "p1" else "t2"] = team
        done[mid][side] = True

    # group standings only when every match in that group is scored
    pos = {}  # (discipline, group) -> {rank: (pair, team)}
    for disc in {m["discipline"] for m in MATCHES}:
        groups = {
            m["stage"] for m in MATCHES
            if m["discipline"] == disc and str(m["stage"]).startswith("Group")
        }
        for grp in groups:
            gm = [m for m in MATCHES if m["discipline"] == disc and m["stage"] == grp]
            if gm and all(match_result(m, scores)["played"] for m in gm):
                table = group_standings(disc, grp, scores)
                pos[(disc, grp)] = {s["rank"]: (s["pair"], s["team"]) for s in table}

    def resolve_group_ref(disc, text):
        mt = re.match(r"Group (\w+)", str(text))
        if not mt:
            return None
        table = pos.get((disc, "Group " + mt.group(1)))
        if not table:
            return None
        if "3rd" in text:
            rank = 3
        elif "Runner-up" in text or "2nd" in text:
            rank = 2
        elif "Winner" in text or "1st" in text:
            rank = 1
        else:
            return None
        return table.get(rank)

    def ordered(disc, stage_name):
        return sorted(
            (m for m in MATCHES if m["discipline"] == disc and m["stage"] == stage_name),
            key=lambda x: (x["start"], x["court"]),
        )

    def winner_of(mid):
        d = done[mid]
        if not (d["p1"] and d["p2"]):
            return None
        r = match_result(by_id[mid], scores)
        if not r["played"] or r["winner"] is None:
            return None
        side = r["winner"]
        e = eff[mid]
        return (e[side], e["t1" if side == "p1" else "t2"])

    # 1) group-based participants: QFs and the Women's SF / Final (1st seed)
    for m in MATCHES:
        if m["stage"] not in KNOCKOUT_STAGES:
            continue
        for side in ("p1", "p2"):
            ref = resolve_group_ref(m["discipline"], m[side])
            if ref:
                set_side(m["id"], side, ref[0], ref[1])

    # 2) semifinal participants from QF winners
    for m in MATCHES:
        if m["stage"] != "Semifinal":
            continue
        qfs = ordered(m["discipline"], "Quarterfinal")
        for side in ("p1", "p2"):
            mt = re.match(r"Winner QF(\d+)", str(m[side]))
            if mt and 1 <= int(mt.group(1)) <= len(qfs):
                w = winner_of(qfs[int(mt.group(1)) - 1]["id"])
                if w:
                    set_side(m["id"], side, w[0], w[1])

    # 3) final participants from SF winners (and Women's "Winner of Semifinal")
    for m in MATCHES:
        if m["stage"] != "Final":
            continue
        sfs = ordered(m["discipline"], "Semifinal")
        for side in ("p1", "p2"):
            text = str(m[side])
            mt = re.match(r"Winner SF(\d+)", text)
            if mt and 1 <= int(mt.group(1)) <= len(sfs):
                w = winner_of(sfs[int(mt.group(1)) - 1]["id"])
                if w:
                    set_side(m["id"], side, w[0], w[1])
            elif text == "Winner of Semifinal" and sfs:
                w = winner_of(sfs[0]["id"])
                if w:
                    set_side(m["id"], side, w[0], w[1])

    return eff

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
        color: var(--accent-strong);
        font-size: 0.74rem;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 0.02em;
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

      /* dropdown control */
      div[data-testid="stSelectbox"] div[data-baseweb="select"] > div {
        background: var(--panel);
        border: 1px solid var(--line);
        border-radius: 8px;
        box-shadow: 0 4px 14px rgba(16, 32, 28, 0.05);
      }

      div[data-testid="stSelectbox"] div[data-baseweb="select"] > div:hover {
        border-color: var(--accent);
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
        display: flex;
        flex-wrap: wrap;
        gap: 0.45rem;
        width: 100%;
      }

      .stTabs [data-baseweb="tab"] {
        background: rgba(255, 255, 255, 0.72);
        border: 1px solid var(--line);
        border-radius: 8px;
        color: var(--ink);
        flex: 1 1 auto;
        font-weight: 800;
        justify-content: center;
        min-width: max-content;
        padding: 0.45rem clamp(0.5rem, 2vw, 1rem);
        text-align: center;
        white-space: nowrap;
      }

      .footer-note {
        border-top: 1px solid var(--line);
        color: var(--muted);
        font-size: 0.78rem;
        margin-top: 1.4rem;
        padding-top: 0.8rem;
      }

      /* Rules tab */
      .rules-intro {
        color: var(--muted);
        font-size: 0.95rem;
        margin: 0.2rem 0 1rem;
      }

      .quick-grid {
        display: grid;
        gap: 0.7rem;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        margin: 0.4rem 0 1.4rem;
      }

      .quick-card {
        background: var(--panel);
        border: 1px solid var(--line);
        border-left: 4px solid var(--accent);
        border-radius: 10px;
        box-shadow: 0 8px 22px rgba(16, 32, 28, 0.06);
        padding: 0.8rem 0.9rem;
      }

      .quick-card .ico { font-size: 1.1rem; }

      .quick-card .k {
        color: var(--muted);
        display: block;
        font-size: 0.7rem;
        font-weight: 800;
        letter-spacing: 0.02em;
        margin-top: 0.3rem;
        text-transform: uppercase;
      }

      .quick-card .v {
        color: var(--ink);
        display: block;
        font-size: 1rem;
        font-weight: 850;
        margin-top: 0.1rem;
      }

      .section-head {
        color: var(--accent-strong);
        font-size: 0.82rem;
        font-weight: 850;
        letter-spacing: 0.03em;
        margin: 0.6rem 0 0.5rem;
        text-transform: uppercase;
      }

      .div-grid {
        display: grid;
        gap: 0.8rem;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        margin-bottom: 1.2rem;
      }

      .div-card {
        background: var(--panel);
        border: 1px solid var(--line);
        border-top: 4px solid var(--dv);
        border-radius: 10px;
        box-shadow: 0 8px 22px rgba(16, 32, 28, 0.06);
        padding: 0.95rem 1rem;
      }

      .div-card h4 {
        color: var(--dv);
        font-size: 1.02rem;
        margin: 0 0 0.55rem;
      }

      .div-card .row {
        border-top: 1px dashed var(--line);
        display: flex;
        font-size: 0.84rem;
        gap: 0.5rem;
        justify-content: space-between;
        padding: 0.32rem 0;
      }

      .div-card .row:first-of-type { border-top: 0; }
      .div-card .row .lbl { color: var(--muted); font-weight: 700; }
      .div-card .row .val { color: var(--ink); font-weight: 800; text-align: right; }

      @media (max-width: 760px) {
        .quick-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        .div-grid { grid-template-columns: 1fr; }
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

        .stTabs [data-baseweb="tab-list"] {
          gap: 0.3rem;
        }

        .stTabs [data-baseweb="tab"] {
          flex: 1 1 40%;
          font-size: 0.82rem;
          min-width: 0;
          padding: 0.4rem 0.5rem;
        }
      }
    </style>
    """,
    unsafe_allow_html=True,
)

total_sessions = list(OrderedDict.fromkeys((m["day"], m["session"]) for m in MATCHES))

st.markdown(
    (
        "<div class='hero'>"
        "<div>"
        "<div class='eyebrow'>Schedule viewer</div>"
        f"<h1>{h(DATA['title'])}</h1>"
        f"<p>{h(DATA['subtitle'])} &middot; {h(len(MATCHES))} scheduled matches</p>"
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
cc1, cc2, cc3 = st.columns([1, 2, 1])

with cc1:
    cat = st.selectbox(
        "Category",
        ["All categories"] + discs,
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
    stage = st.selectbox(
        "Stage",
        ["All", "Group stage", "Quarterfinals", "Semifinals", "Finals"],
    )


def keep(m):
    if cat != "All categories" and m["discipline"] != cat:
        return False

    if pair_team != "All pairs":
        left_pair = f"{m['p1']} ({m['t1']})"
        right_pair = f"{m['p2']} ({m['t2']})"

        if pair_team not in (left_pair, right_pair):
            return False

    if stage == "Group stage" and m["stage"] in KNOCKOUT_STAGES:
        return False

    if stage == "Quarterfinals" and m["stage"] != "Quarterfinal":
        return False

    if stage == "Semifinals" and m["stage"] != "Semifinal":
        return False

    if stage == "Finals" and m["stage"] != "Final":
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
group_count = sum(1 for m in view if m["stage"] not in KNOCKOUT_STAGES)
qf_count = sum(1 for m in view if m["stage"] in KNOCKOUT_STAGES)

st.markdown(
    (
        "<div class='summary-grid'>"
        f"{stat_card('Matches shown', len(view), f'{len(MATCHES)} total scheduled')}"
        f"{stat_card('Group stage', group_count, 'Filtered group matches')}"
        f"{stat_card('Knockouts', qf_count, 'QF, semis & finals')}"
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

# Scores come from scores.xlsx / scores.csv sitting next to app.py. The
# Standings tab only appears once such a file exists.
SCORES = load_scores()
HAS_SCORES = SCORE_XLSX.exists() or SCORE_CSV.exists()

# Auto-advance knockout placeholders (group winners, QF/SF winners) from scores.
EFF = resolve_bracket(SCORES)


def eff_match(m):
    """A copy of the match with knockout participants resolved from results."""
    e = EFF[m["id"]]
    return {**m, "p1": e["p1"], "t1": e["t1"], "p2": e["p2"], "t2": e["t2"]}

tab_labels = ["Timings", "Court Grid"]
if HAS_SCORES:
    tab_labels.append("Results")
    tab_labels.append("Standings")
tab_labels.append("Rules")

_tabs = dict(zip(tab_labels, st.tabs(tab_labels)))
tab_time = _tabs["Timings"]
tab_grid = _tabs["Court Grid"]
tab_rules = _tabs["Rules"]
tab_results = _tabs.get("Results")
tab_stand = _tabs.get("Standings")

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
                        chip_html(eff_match(m), highlight_player=hp, result=match_result(m, SCORES)),
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
                            chip_html(eff_match(cell), highlight_player=hp, result=match_result(cell, SCORES)),
                            unsafe_allow_html=True,
                        )
                    else:
                        cols[idx + 1].markdown("<div class='empty'>Open</div>", unsafe_allow_html=True)

# --- Results (only matches that have a recorded score) ----------------------
if tab_results is not None:
    with tab_results:
        played = [(m, match_result(m, SCORES)) for m in view]
        played = [(m, r) for m, r in played if r["played"]]
        st.markdown(
            (
                "<div class='view-title'>"
                f"<h3>{h(head)}</h3>"
                f"<span class='match-count'>{h(len(played))} results</span>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )
        if not played:
            st.info("No results recorded yet for the selected filters.")
        else:
            for (day, session) in sessions:
                rs = [
                    (m, r) for m, r in played
                    if m["day"] == day and m["session"] == session
                ]
                if not rs:
                    continue
                st.markdown(
                    f"<div class='sess-head'><small>Day {h(day)}</small>{h(session)}<small>{h(len(rs))} results</small></div>",
                    unsafe_allow_html=True,
                )
                cols = st.columns(3)
                for i, (m, r) in enumerate(rs):
                    hp = pair_team if pair_team != "All pairs" else None
                    cols[i % 3].markdown(
                        chip_html(eff_match(m), highlight_player=hp, result=r),
                        unsafe_allow_html=True,
                    )

# --- Standings (only shown when a scores file exists) -----------------------
if tab_stand is not None:
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
        (
            "<div class='view-title'><h3>Rules &amp; Regulations</h3>"
            "<span class='match-count'>BWF rules apply</span></div>"
            "<p class='rules-intro'>The essentials at a glance — tap any section "
            "below for the full detail.</p>"
            "<div class='quick-grid'>"
            "<div class='quick-card'><span class='ico'>🔁</span>"
            "<span class='k'>Group Stage</span><span class='v'>Single set to 21</span></div>"
            "<div class='quick-card'><span class='ico'>🏆</span>"
            "<span class='k'>Knockouts</span><span class='v'>Best of 3 sets</span></div>"
            "<div class='quick-card'><span class='ico'>🎯</span>"
            "<span class='k'>Scoring</span><span class='v'>Rally, win by 2</span></div>"
            "<div class='quick-card'><span class='ico'>⏱️</span>"
            "<span class='k'>Report</span><span class='v'>20 min early</span></div>"
            "</div>"
            "<div class='section-head'>Divisions &amp; path to the final</div>"
            "<div class='div-grid'>"
            "<div class='div-card' style='--dv:#2563EB'><h4>Men's</h4>"
            "<div class='row'><span class='lbl'>Groups</span><span class='val'>4 groups</span></div>"
            "<div class='row'><span class='lbl'>Qualify</span><span class='val'>Top 2 each &rarr; 8</span></div>"
            "<div class='row'><span class='lbl'>Knockout</span><span class='val'>QF &rarr; SF &rarr; Final</span></div>"
            "</div>"
            "<div class='div-card' style='--dv:#C43B73'><h4>Women's</h4>"
            "<div class='row'><span class='lbl'>Group</span><span class='val'>1 group of 5</span></div>"
            "<div class='row'><span class='lbl'>1st place</span><span class='val'>Straight to Final</span></div>"
            "<div class='row'><span class='lbl'>2nd vs 3rd</span><span class='val'>Semi-Final</span></div>"
            "<div class='row'><span class='lbl'>Final</span><span class='val'>1st vs SF winner</span></div>"
            "</div>"
            "<div class='div-card' style='--dv:#15803D'><h4>Mixed</h4>"
            "<div class='row'><span class='lbl'>Groups</span><span class='val'>2 groups</span></div>"
            "<div class='row'><span class='lbl'>Qualify</span><span class='val'>Top 2 each &rarr; SF</span></div>"
            "<div class='row'><span class='lbl'>Knockout</span><span class='val'>SF &rarr; Final</span></div>"
            "</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )

    st.markdown("<div class='section-head'>Full rules</div>", unsafe_allow_html=True)

    with st.expander("🏟️  Format & group stage", expanded=True):
        st.markdown(
            "**Two stages:** Group Stage (round-robin) → Knockout Stage.\n\n"
            "- Each team plays every other team in its group **once**.\n"
            "- Group matches are a **single set to 21 points**.\n"
            "- **Rally scoring** is used throughout the tournament."
        )

    with st.expander("🎯  Scoring system"):
        st.markdown(
            "1. **Rally scoring** — a point is awarded on every rally, regardless of who served.\n"
            "2. A set is won at **21 points** with a **2-point lead**.\n"
            "3. At **20–20**, play continues until a side leads by 2.\n"
            "4. At **29–29**, the **next point decides** the set.\n"
            "5. Knockout matches are **best of 3** — first to **2 sets** wins."
        )

    with st.expander("🏸  Service rules"):
        st.markdown(
            "1. Initial service is decided by a **coin toss**.\n"
            "2. Serve must be **underhand**, shuttle struck **below the waist**.\n"
            "3. **Both feet** must stay on the court until the shuttle is struck.\n"
            "4. Deliberate distractions or feints may be ruled a **fault**.\n"
            "5. Standard BWF service rules apply unless the Committee specifies otherwise."
        )

    with st.expander("⚖️  Tie-breaking criteria"):
        st.markdown(
            "When teams finish level on points, ranking is decided in order:\n\n"
            "1. **Head-to-head** result\n"
            "2. **Points difference** (scored − conceded)\n"
            "3. **Total points scored**\n"
            "4. **Fewest points conceded**\n\n"
            "_If still tied, the Tournament Committee's decision is final._"
        )

    with st.expander("⏱️  Attendance & walkovers"):
        st.markdown(
            "1. Matches start **strictly** to the published schedule.\n"
            "2. Report ready to play **at least 20 minutes before** your match.\n"
            "3. Failing to report on time may result in a **walkover**.\n"
            "4. Inform the Committee of any exceptional circumstances immediately."
        )

    with st.expander("🤝  Conduct & safety"):
        st.markdown(
            "- Display **good sportsmanship** and respect opponents, officials, and spectators.\n"
            "- Unsporting conduct or abuse may bring **warnings, penalties, or disqualification**.\n"
            "- Raise disputes through your **Team Captain** or the Committee.\n"
            "- Wear proper attire and **non-marking footwear**; play at your own risk.\n"
            "- Report any **injury** immediately; the Committee may pause or postpone for safety."
        )

    with st.expander("📋  General regulations"):
        st.markdown(
            "- **BWF rules** apply unless modified by these regulations.\n"
            "- The Committee may interpret, amend, and enforce rules as needed.\n"
            "- All Committee decisions are **final and binding**.\n"
            "- Participation constitutes **acceptance** of all tournament rules."
        )

    st.markdown(
        "<p style='text-align:center;font-weight:850;color:var(--accent-strong);"
        "margin-top:1rem'>🏸 Play Fair · Play Hard · Enjoy the Tournament</p>",
        unsafe_allow_html=True,
    )
st.markdown("<div class='footer-note'>PPL Season 2 - Badminton</div>", unsafe_allow_html=True)
