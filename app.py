"""
PPL Season 2 — Badminton Schedule Viewer
Run locally:   streamlit run app.py
Deploy:        push app.py + schedule_data.json + requirements.txt to a repo,
               then deploy on https://share.streamlit.io
"""
import json
from pathlib import Path
from collections import OrderedDict

import streamlit as st

# ----------------------------------------------------------------------------- data
st.set_page_config(page_title="PPL S2 · Schedule", page_icon="🏸", layout="wide")
DATA_PATH = Path(__file__).parent / "schedule_data.json"


@st.cache_data
def load_data():
    with open(DATA_PATH) as f:
        return json.load(f)


try:
    DATA = load_data()
except Exception as e:  # noqa: BLE001
    st.error(f"Could not load schedule_data.json — keep it next to app.py.  ({e})")
    st.stop()

MATCHES = DATA["matches"]
TEAM_COLORS = DATA["team_colors"]
DISC_ACCENT = {"Women's": "#EC407A", "Men's": "#42A5F5", "Mixed": "#66BB6A"}
DISC_ABBR = {"Women's": "W", "Men's": "M", "Mixed": "X"}

# ----------------------------------------------------------------------------- styles
st.markdown(
    """
    <style>
      .block-container {padding-top: 1.3rem; max-width: 1300px;}
      .hero {
        background: linear-gradient(110deg,#1f2a37 0%,#2d3e50 50%,#37474f 100%);
        border-radius: 18px; padding: 22px 28px; color:#fff; margin-bottom: 14px;
        box-shadow: 0 10px 30px rgba(0,0,0,.18);
      }
      .hero h1 {margin:0; font-size:1.7rem; letter-spacing:.3px;}
      .hero p  {margin:4px 0 0; opacity:.8; font-size:.95rem;}
      .sess-head {
        font-weight:800; font-size:1.02rem; color:#263238;
        border-left:6px solid #37474f; padding:6px 12px; margin:18px 0 8px;
        background:#eceff1; border-radius:0 8px 8px 0;
      }
      .chip {border-radius:12px; padding:9px 11px; height:100%;
             border:1px solid rgba(0,0,0,.06); box-shadow:0 1px 4px rgba(0,0,0,.05);}
      .chip .tag {font-size:.66rem; font-weight:800; letter-spacing:.4px;
                  text-transform:uppercase; opacity:.75; margin-bottom:5px;}
      .pair {display:flex; align-items:center; gap:7px; font-size:.86rem;
             font-weight:600; color:#1b1b1b; line-height:1.25; margin:1px 0;}
      .dot {width:10px; height:10px; border-radius:50%; flex:0 0 auto;
            box-shadow:0 0 0 1px rgba(0,0,0,.12);}
      .vs {font-size:.7rem; color:#90a4ae; font-weight:700; margin:1px 0 1px 17px;}
      .timecell {font-weight:800; color:#263238; font-size:.82rem; padding-top:18px;}
      .empty {opacity:.25; text-align:center; padding-top:22px; font-size:.8rem;}
      .legend span {display:inline-flex; align-items:center; gap:6px; margin-right:14px;
                    font-size:.82rem; color:#37474f;}
      .badge {display:inline-block; padding:2px 9px; border-radius:999px;
              color:#fff; font-size:.72rem; font-weight:700;}
      .tline {display:flex; gap:14px; align-items:flex-start; padding:8px 0;
              border-bottom:1px solid #eceff1;}
      .tline .when {min-width:150px; font-weight:800; color:#263238; font-size:.9rem;}
      .tline .when small {display:block; font-weight:500; color:#90a4ae;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    f"""<div class="hero">
        <h1>🏸 {DATA['title']}</h1>
        <p>{DATA['subtitle']} · {DATA['courts']} courts</p>
    </div>""",
    unsafe_allow_html=True,
)

# ----------------------------------------------------------------------------- primary selectors: CATEGORY + TEAM
discs = sorted({m["discipline"] for m in MATCHES})
teams = sorted({t for m in MATCHES for t in (m["t1"], m["t2"]) if t})

cc1, cc2, cc3 = st.columns([1.4, 1, 1])
with cc1:
    cat = st.radio("Category", ["All"] + discs, horizontal=True)
with cc2:
    team = st.selectbox("Team", ["All teams"] + teams)
with cc3:
    stage = st.radio("Stage", ["All", "Group", "Quarterfinals"], horizontal=True)

# secondary filters
with st.sidebar:
    st.header("More filters")
    courts = sorted({m["court"] for m in MATCHES})
    f_court = st.multiselect("Court", courts, default=[])
    q = st.text_input("🔎 Search player / pair").strip().lower()
    st.markdown("---")
    st.caption("Pick a Category and Team above to see their match timings.")


def keep(m):
    if cat != "All" and m["discipline"] != cat:
        return False
    if team != "All teams" and team not in (m["t1"], m["t2"]):
        return False
    if stage == "Group" and m["stage"] == "Quarterfinal":
        return False
    if stage == "Quarterfinals" and m["stage"] != "Quarterfinal":
        return False
    if f_court and m["court"] not in f_court:
        return False
    if q and q not in (m["p1"] + " " + m["p2"]).lower():
        return False
    return True


view = [m for m in MATCHES if keep(m)]
view.sort(key=lambda x: (x["day"], x["start"], x["court"]))

# ----------------------------------------------------------------------------- metrics
m1, m2, m3, m4 = st.columns(4)
m1.metric("Matches shown", len(view))
m2.metric("Group", sum(1 for m in view if m["stage"] != "Quarterfinal"))
m3.metric("Quarterfinals", sum(1 for m in view if m["stage"] == "Quarterfinal"))
if view:
    m4.metric("First → Last", f"{view[0]['start_str']} → {view[-1]['end_str']}")
else:
    m4.metric("First → Last", "—")

leg = " ".join(
    f"<span><span class='dot' style='background:{c}'></span>{t}</span>"
    for t, c in TEAM_COLORS.items()
)
st.markdown(f"<div class='legend' style='margin:6px 0 2px'>{leg}</div>", unsafe_allow_html=True)


def chip_html(m, highlight_team=None):
    accent = DISC_ACCENT.get(m["discipline"], "#90a4ae")
    bg = accent + "14"
    tag = f"{DISC_ABBR.get(m['discipline'], '?')} · {m['stage']}"
    c1 = TEAM_COLORS.get(m["t1"], "#cfd8dc")
    c2 = TEAM_COLORS.get(m["t2"], "#cfd8dc")
    w1 = "800" if highlight_team and m["t1"] == highlight_team else "600"
    w2 = "800" if highlight_team and m["t2"] == highlight_team else "600"
    return (
        f"<div class='chip' style='background:{bg}; border-left:4px solid {accent}'>"
        f"<div class='tag' style='color:{accent}'>{tag}</div>"
        f"<div class='pair' style='font-weight:{w1}'><span class='dot' style='background:{c1}'></span>{m['p1']}</div>"
        f"<div class='vs'>vs</div>"
        f"<div class='pair' style='font-weight:{w2}'><span class='dot' style='background:{c2}'></span>{m['p2']}</div>"
        f"</div>"
    )


sessions = list(OrderedDict.fromkeys((m["day"], m["session"]) for m in MATCHES))

tab_time, tab_grid, tab_list = st.tabs(["🕒 Timings", "📅 Court Grid", "📋 List"])

# --- Timings (category + team focused) --------------------------------------
with tab_time:
    if not view:
        st.info("No matches for this Category / Team selection.")
    else:
        head = "Showing all categories" if cat == "All" else f"{cat}"
        if team != "All teams":
            head += f" · {team}"
        st.markdown(f"#### {head} — {len(view)} matches")
        for (day, session) in sessions:
            rs = [m for m in view if m["day"] == day and m["session"] == session]
            if not rs:
                continue
            st.markdown(f"<div class='sess-head'>Day {day} · {session}</div>", unsafe_allow_html=True)
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
                    inner[i % 3].markdown(chip_html(m, hl), unsafe_allow_html=True)

# --- Court Grid -------------------------------------------------------------
with tab_grid:
    if not view:
        st.info("No matches for this Category / Team selection.")
    for (day, session) in sessions:
        rs = [m for m in view if m["day"] == day and m["session"] == session]
        if not rs:
            continue
        st.markdown(f"<div class='sess-head'>Day {day} · {session}</div>", unsafe_allow_html=True)
        times = sorted({(m["start"], m["start_str"], m["end_str"]) for m in rs})
        head = st.columns([1] + [3] * DATA["courts"])
        head[0].markdown("**Time**")
        for ci in range(DATA["courts"]):
            head[ci + 1].markdown(f"**Court {ci + 1}**")
        for start, s_str, e_str in times:
            cols = st.columns([1] + [3] * DATA["courts"])
            cols[0].markdown(
                f"<div class='timecell'>{s_str}<br><span style='font-weight:500;opacity:.6'>{e_str}</span></div>",
                unsafe_allow_html=True,
            )
            for ci in range(DATA["courts"]):
                cell = next((m for m in rs if m["court"] == ci + 1 and m["start"] == start), None)
                if cell:
                    hl = team if team != "All teams" else None
                    cols[ci + 1].markdown(chip_html(cell, hl), unsafe_allow_html=True)
                else:
                    cols[ci + 1].markdown("<div class='empty'>—</div>", unsafe_allow_html=True)

# --- List -------------------------------------------------------------------
with tab_list:
    if not view:
        st.info("No matches for this Category / Team selection.")
    else:
        rows = [
            {
                "Day": m["day"],
                "Session": m["session"],
                "Time": f"{m['start_str']}–{m['end_str']}",
                "Court": m["court"],
                "Category": m["discipline"],
                "Stage": m["stage"],
                "Match": f"{m['p1']}  vs  {m['p2']}",
                "Teams": f"{m['t1'] or '—'} / {m['t2'] or '—'}",
            }
            for m in view
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True)

st.caption("PPL Season 2 schedule viewer · built with Streamlit")
