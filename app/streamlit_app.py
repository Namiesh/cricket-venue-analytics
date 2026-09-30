"""
Cricket Venue Analytics — Streamlit Dashboard
Integrates automatic upcoming international ODI & T20I matches with historical venue analytics.
Supports Mode A (Venue-Wide), Mode B (Single Team at Venue), and Mode C (Two Teams Head-to-Head).
"""

import sys
from pathlib import Path
from datetime import datetime
import streamlit as st
import pandas as pd
import plotly.express as px

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analytics import (
    get_venues_for_format,
    get_recent_matches,
    calculate_venue_summary,
    analyze_score_ranges,
    get_team_venue_stats,
    get_head_to_head_stats,
    get_teams_for_venue_format,
    analyze_match_context,
    get_venue_by_name,
)
from src.fixtures import (
    get_upcoming_fixtures,
    resolve_fixture_venue,
    UpcomingFixture,
)
from src.processing.venue_normalizer import get_canonical_venue_info

# Page Configuration
st.set_page_config(
    page_title="Cricket Venue Analytics",
    page_icon="🏏",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS
st.markdown("""
<style>
    .main-title {
        font-size: 2.2rem;
        font-weight: 700;
        margin-bottom: 0.1rem;
    }
    .main-subtitle {
        font-size: 1.1rem;
        color: #888;
        margin-bottom: 1.2rem;
    }
    .venue-title {
        font-size: 1.8rem;
        font-weight: 600;
        color: #1E88E5;
        margin-bottom: 0.2rem;
    }
    .venue-subtitle {
        font-size: 1.0rem;
        color: #AAA;
        margin-bottom: 1.2rem;
    }
    .fixture-card {
        background-color: #1E1E1E;
        border: 1px solid #333;
        border-radius: 8px;
        padding: 1rem;
        margin-bottom: 0.5rem;
    }
    .badge-odi {
        background-color: #1565C0;
        color: white;
        padding: 3px 8px;
        border-radius: 4px;
        font-weight: bold;
        font-size: 0.85rem;
    }
    .badge-t20 {
        background-color: #E65100;
        color: white;
        padding: 3px 8px;
        border-radius: 4px;
        font-weight: bold;
        font-size: 0.85rem;
    }
    .insight-box {
        background-color: #0E2A47;
        border-left: 5px solid #1E88E5;
        padding: 1rem;
        border-radius: 4px;
        margin: 1rem 0;
        font-size: 1.05rem;
        line-height: 1.5;
    }
    .cache-bar {
        font-size: 0.85rem;
        color: #888;
        margin-bottom: 1rem;
    }
    .match-banner {
        background-color: #1A237E;
        border: 1px solid #3949AB;
        padding: 1.2rem;
        border-radius: 8px;
        margin-bottom: 1.5rem;
    }
</style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=600)
def load_venues(format_selected: str):
    return get_venues_for_format(format_selected)


@st.cache_data(ttl=300)
def load_teams(venue_id: str, format_selected: str):
    return get_teams_for_venue_format(venue_id, format_selected)


def main():
    # Session state initialization for SINGLE SOURCE OF TRUTH
    if "selected_fixture" not in st.session_state:
        st.session_state["selected_fixture"] = None

    selected_fixture = st.session_state["selected_fixture"]

    # Sidebar Controls
    st.sidebar.title("🏏 Filters & Controls")

    if selected_fixture is not None:
        st.sidebar.info(
            f"🔒 **Fixture Lock Active**\n\n"
            f"Match: **{selected_fixture['team1']} vs {selected_fixture['team2']}** ({selected_fixture['format']})\n\n"
            f"Venue: **{selected_fixture['canonical_display_name']}**\n\n"
            f"Click below to return to manual venue browsing."
        )
        if st.sidebar.button("❌ Clear Selected Match"):
            st.session_state["selected_fixture"] = None
            st.rerun()

    # Format Selector
    format_selected = st.sidebar.radio(
        "Select Match Format",
        options=["ODI", "T20I"],
        index=0 if (not selected_fixture or selected_fixture["format"] == "ODI") else 1,
        key="format_selector",
        help="ODI and T20I statistics are kept strictly separated.",
    )

    # If fixture lock active, ensure format matches fixture format
    if selected_fixture and selected_fixture["format"] != format_selected:
        format_selected = selected_fixture["format"]

    # Available Venues for format
    available_venues = load_venues(format_selected)
    if not available_venues:
        st.error(f"No historical {format_selected} venue records found in database.")
        return

    venue_options = {v["canonical_name"]: v["venue_id"] for v in available_venues}
    venue_display_names = list(venue_options.keys())

    # Historical Window Selector
    window_options = {
        "Last 5": 5,
        "Last 10": 10,
        "Last 20": 20,
        "Last 50": 50,
        "All Available": 9999,
    }
    selected_window_label = st.sidebar.selectbox(
        "Historical Window",
        options=list(window_options.keys()),
        index=1,
        key="window_selector",
    )
    window_n = window_options[selected_window_label]

    # Mode 1: UPCOMING FIXTURE ANALYSIS MODE
    if selected_fixture is not None:
        target_format = selected_fixture["format"]
        target_team1 = selected_fixture["team1"]
        target_team2 = selected_fixture["team2"]

        # Resolve venue ID safely
        raw_v = selected_fixture.get("raw_venue_name") or selected_fixture["venue"]
        city_v = selected_fixture.get("city")
        v_id, c_display_name, _, _ = get_canonical_venue_info(raw_v, city_v)
        resolved_vid = selected_fixture.get("canonical_venue_id") or selected_fixture.get("resolved_venue_id") or v_id

        if not resolved_vid:
            st.sidebar.warning(f"⚠️ Unresolved venue: '{c_display_name}'. Select historical venue below:")
            selected_venue_display = st.sidebar.selectbox("Manual Venue Fallback", options=venue_display_names, key="manual_fallback_venue")
            resolved_vid = venue_options[selected_venue_display]

        target_venue_id = resolved_vid
        selected_team1 = target_team1
        selected_team2 = target_team2

    # Mode 2: MANUAL VENUE BROWSING MODE
    else:
        selected_venue_display = st.sidebar.selectbox(
            "Select Venue",
            options=venue_display_names,
            index=0,
            key="venue_selector",
        )
        target_venue_id = venue_options[selected_venue_display]
        target_format = format_selected

        venue_teams = load_teams(target_venue_id, target_format)
        team1_options = ["None"] + venue_teams
        selected_team1 = st.sidebar.selectbox("Optional Team 1", options=team1_options, index=0, key="t1_selector")

        team2_options = ["None"] + [t for t in venue_teams if t != selected_team1]
        selected_team2 = st.sidebar.selectbox("Optional Team 2", options=team2_options, index=0, key="t2_selector")

    # Main Page Header
    st.markdown('<div class="main-title">CRICKET VENUE ANALYTICS</div>', unsafe_allow_html=True)
    st.markdown('<div class="main-subtitle">Historical International ODI & T20I Venue Analysis</div>', unsafe_allow_html=True)

    # ==========================================
    # UPCOMING INTERNATIONAL MATCHES SECTION
    # ==========================================
    st.markdown("### 📅 UPCOMING INTERNATIONAL MATCHES")

    force_refresh = st.session_state.get("trigger_manual_refresh", False)
    st.session_state["trigger_manual_refresh"] = False

    fixtures, cache_meta = get_upcoming_fixtures(force_refresh=force_refresh)

    # Status Bar & Refresh Button
    c_status, c_btn = st.columns([4, 1])
    with c_status:
        last_updated = cache_meta.get("fetched_at") or "Unknown"
        if last_updated != "Unknown" and "T" in last_updated:
            try:
                dt_obj = datetime.fromisoformat(last_updated.replace("Z", "+00:00"))
                last_updated = dt_obj.strftime("%d %b %Y, %H:%M UTC")
            except Exception:
                pass
        msg = cache_meta.get("message", "Using cached fixture data.")
        st.markdown(f'<div class="cache-bar"><b>Status:</b> {msg} | <b>Last Updated:</b> {last_updated}</div>', unsafe_allow_html=True)

    with c_btn:
        if st.button("🔄 Refresh Matches"):
            st.session_state["trigger_manual_refresh"] = True
            st.rerun()

    # Upcoming Fixtures Grid
    if not fixtures:
        st.info("No upcoming men's international ODI or T20I matches available in fixture cache.")
    else:
        displayed_fixtures = fixtures[:10]
        cols = st.columns(2)
        for idx, fix in enumerate(displayed_fixtures):
            col = cols[idx % 2]
            with col:
                ist_formatted_time = fix.formatted_ist_datetime()
                badge_class = "badge-odi" if fix.format == "ODI" else "badge-t20"
                c_display = fix.canonical_display_name or get_canonical_venue_info(fix.venue, fix.city)[1]

                st.markdown(f"""
                <div class="fixture-card">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 0.5rem;">
                        <span class="{badge_class}">{fix.format}</span>
                        <span style="font-size:0.85rem; color:#64B5F6; font-weight:600;">{ist_formatted_time}</span>
                    </div>
                    <div style="font-size:1.15rem; font-weight:bold; margin-bottom:0.3rem;">
                        {fix.team1} vs {fix.team2}
                    </div>
                    <div style="font-size:0.9rem; color:#CCC;">📍 {c_display}</div>
                    <div style="font-size:0.8rem; color:#888; margin-bottom:0.8rem;">{fix.series or "International Match"}</div>
                </div>
                """, unsafe_allow_html=True)

                btn_key = f"btn_analyze_{fix.match_id}"
                if st.button(f"🔍 ANALYZE MATCH ({fix.team1} vs {fix.team2})", key=btn_key):
                    v_id, c_name, _, _ = get_canonical_venue_info(fix.raw_venue_name or fix.venue, fix.city)
                    resolved_vid = fix.canonical_venue_id or fix.resolved_venue_id or v_id

                    st.session_state["selected_fixture"] = {
                        "match_id": fix.match_id,
                        "team1": fix.team1,
                        "team2": fix.team2,
                        "format": fix.format,
                        "venue": fix.venue,
                        "raw_venue_name": fix.raw_venue_name,
                        "canonical_venue_id": resolved_vid,
                        "canonical_display_name": c_name,
                        "city": fix.city,
                        "scheduled_datetime": fix.scheduled_datetime,
                        "formatted_ist": ist_formatted_time,
                        "series": fix.series,
                        "resolved_venue_id": resolved_vid,
                    }
                    st.rerun()

    st.markdown("---")

    # ==========================================
    # HISTORICAL VENUE ANALYSIS SECTION
    # ==========================================
    # Active Upcoming Match Banner if selected
    if selected_fixture is not None:
        fix_info = selected_fixture
        st.markdown(f"""
        <div class="match-banner">
            <div style="font-size:1.2rem; font-weight:bold; color:#64B5F6;">🎯 UPCOMING MATCH ANALYSIS</div>
            <div style="font-size:1.4rem; font-weight:bold; margin:0.3rem 0;">{fix_info['team1']} vs {fix_info['team2']}</div>
            <div>Format: <b>{fix_info['format']}</b> | Venue: <b>{fix_info['canonical_display_name']}</b> | Scheduled: <b>{fix_info['formatted_ist']}</b></div>
            <div style="font-size:0.85rem; color:#AAA; margin-top:0.3rem;">{fix_info['series'] or ''}</div>
        </div>
        """, unsafe_allow_html=True)

    # Perform Analysis Query
    match_context = analyze_match_context(
        team1=selected_team1 if selected_team1 != "None" else None,
        team2=selected_team2 if selected_team2 != "None" else None,
        venue_id=target_venue_id,
        format=target_format,
        n_venue_matches=window_n,
    )

    mode = match_context.get("mode", "venue_wide")
    summary = match_context["venue_summary"]
    c_name = summary["canonical_name"]
    city_str = f"{summary['city']}, {summary['country']}" if summary["city"] and summary["country"] else (summary["city"] or "")

    # CRITICAL CONSISTENCY CHECK
    if selected_fixture is not None:
        expected_vid = selected_fixture.get("canonical_venue_id") or selected_fixture.get("resolved_venue_id")
        if expected_vid and summary["venue_id"] != expected_vid:
            st.error(f"❌ Analysis context mismatch detected! Selected fixture venue '{selected_fixture['canonical_display_name']}' does not match historical summary venue '{c_name}'.")
            return

    # Header for Selected Historical Venue / Team
    if mode == "single_team":
        st.markdown(f'<div class="venue-title">{selected_team1.upper()} AT {c_name.upper()}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="venue-subtitle">{city_str} | <b style="color:#1E88E5;">{target_format}</b> | {selected_team1} Historical Analysis — {selected_window_label}</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="venue-title">{c_name.upper()}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="venue-subtitle">{city_str} | <b style="color:#1E88E5;">{target_format}</b> | Historical Analysis — {selected_window_label}</div>', unsafe_allow_html=True)

    # Navigation Tabs
    tab_overview, tab_score, tab_recent, tab_teams = st.tabs(
        ["📊 Overview", "🎯 Score Analysis", "📜 Recent Matches", "⚔️ Team Analysis"]
    )

    # TAB 1: OVERVIEW
    with tab_overview:
        act_cnt = summary["actual_match_count"]
        req_cnt = summary["requested_match_count"]

        if act_cnt == 0:
            if mode == "single_team":
                st.warning(f"No qualifying {target_format} matches found for {selected_team1} at {c_name}.")
            else:
                st.warning(f"No qualifying {target_format} matches found at {c_name}.")
            return
        elif act_cnt < 3:
            st.warning("⚠️ Limited historical sample. Statistics may not be representative.")
        elif act_cnt < req_cnt and req_cnt != 9999:
            if mode == "single_team":
                st.info(f"ℹ️ Only {act_cnt} qualifying historical matches are available for {selected_team1} at this venue and format.")
            else:
                st.info(f"ℹ️ Only {act_cnt} qualifying historical matches are available for this venue and format.")

        f_inn = summary["first_innings"]
        s_inn = summary["second_innings"]

        col1, col2, col3, col4, col5, col6, col7 = st.columns(7)
        if mode == "single_team":
            col1.metric(f"Avg {selected_team1} 1st Inn", f"{f_inn['average']:.0f}" if f_inn.get('average') is not None else "N/A")
            col2.metric(f"Avg {selected_team1} 2nd Inn", f"{s_inn['average']:.0f}" if s_inn.get('average') is not None else "N/A")
        else:
            col1.metric("Avg 1st Innings", f"{f_inn['average']:.0f}" if f_inn.get('average') is not None else "N/A")
            col2.metric("Avg 2nd Innings", f"{s_inn['average']:.0f}" if s_inn.get('average') is not None else "N/A")

        col3.metric("Highest 1st", f"{f_inn['highest']}" if f_inn.get('highest') is not None else "N/A")
        col4.metric("Highest 2nd", f"{s_inn['highest']}" if s_inn.get('highest') is not None else "N/A")
        col5.metric("Lowest 1st", f"{f_inn['lowest']}" if f_inn.get('lowest') is not None else "N/A")
        col6.metric("Lowest 2nd", f"{s_inn['lowest']}" if s_inn.get('lowest') is not None else "N/A")
        col7.metric("Matches Analyzed", f"{act_cnt}")

        st.markdown("---")

        c_left, c_right = st.columns(2)

        with c_left:
            st.subheader("First vs Second Innings Comparison")
            comp_title = f"{selected_team1} Innings Comparison ({target_format})" if mode == "single_team" else f"Innings Comparison ({target_format})"
            inn1_lbl = f"{selected_team1} 1st Inn" if mode == "single_team" else "1st Innings"
            inn2_lbl = f"{selected_team1} 2nd Inn" if mode == "single_team" else "2nd Innings"

            comp_rows = []
            for m_name, f_val, s_val in [
                ("Average", f_inn.get("average"), s_inn.get("average")),
                ("Median", f_inn.get("median"), s_inn.get("median")),
                ("Highest", f_inn.get("highest"), s_inn.get("highest")),
                ("Lowest", f_inn.get("lowest"), s_inn.get("lowest")),
            ]:
                comp_rows.append({
                    "Metric": m_name,
                    "Innings": inn1_lbl,
                    "Runs": float(f_val) if f_val is not None else None,
                })
                comp_rows.append({
                    "Metric": m_name,
                    "Innings": inn2_lbl,
                    "Runs": float(s_val) if s_val is not None else None,
                })

            comp_df = pd.DataFrame(comp_rows)
            fig_comp = px.bar(
                comp_df,
                x="Metric",
                y="Runs",
                color="Innings",
                barmode="group",
                color_discrete_sequence=["#1E88E5", "#FF7043"],
                title=comp_title,
            )
            fig_comp.update_layout(height=380, margin=dict(l=20, r=20, t=40, b=20))
            st.plotly_chart(fig_comp, use_container_width=True)

        with c_right:
            st.subheader("Historical Win Distribution")
            if mode == "single_team":
                w_cnt = summary.get("wins", 0)
                l_cnt = summary.get("losses", 0)
                t_cnt = summary.get("ties", 0)
                tot_dec = w_cnt + l_cnt + t_cnt

                if tot_dec > 0:
                    pie_df = pd.DataFrame({
                        "Outcome": [f"{selected_team1} Wins", f"{selected_team1} Losses", "Ties"],
                        "Count": [w_cnt, l_cnt, t_cnt],
                    })
                    fig_pie = px.pie(
                        pie_df,
                        names="Outcome",
                        values="Count",
                        color="Outcome",
                        color_discrete_map={
                            f"{selected_team1} Wins": "#1E88E5",
                            f"{selected_team1} Losses": "#E53935",
                            "Ties": "#FFA726",
                        },
                        hole=0.4,
                        title=f"{selected_team1} Match Outcomes",
                    )
                    fig_pie.update_layout(height=380, margin=dict(l=20, r=20, t=40, b=20))
                    st.plotly_chart(fig_pie, use_container_width=True)
                else:
                    st.info("No decided matches in the selected sample.")
            else:
                bf_w = summary["batting_first_wins"]
                ch_w = summary["chasing_wins"]
                t_w = summary["ties"]
                tot_dec = bf_w + ch_w + t_w

                if tot_dec > 0:
                    pie_df = pd.DataFrame({
                        "Outcome": ["Batting First Wins", "Chasing Wins", "Ties"],
                        "Count": [bf_w, ch_w, t_w],
                    })
                    fig_pie = px.pie(
                        pie_df,
                        names="Outcome",
                        values="Count",
                        color="Outcome",
                        color_discrete_map={
                            "Batting First Wins": "#1E88E5",
                            "Chasing Wins": "#26A69A",
                            "Ties": "#FFA726",
                        },
                        hole=0.4,
                        title="Outcome Distribution",
                    )
                    fig_pie.update_layout(height=380, margin=dict(l=20, r=20, t=40, b=20))
                    st.plotly_chart(fig_pie, use_container_width=True)
                else:
                    st.info("No decided matches in the selected sample.")

        # Venue Insight Box
        st.subheader("💡 Venue Insight")
        if mode == "single_team":
            f_cnt = f_inn.get("sample_count", 0)
            s_cnt = s_inn.get("sample_count", 0)
            f_avg_str = f"{f_inn['average']} runs" if f_inn.get('average') is not None else "N/A"
            s_avg_str = f"{s_inn['average']} runs" if s_inn.get('average') is not None else "N/A"
            win_pct_str = f"{summary['win_percentage']}%" if summary.get('win_percentage') is not None else "N/A"

            insight_text = (
                f"Among <b>{selected_team1}</b>'s last {act_cnt} qualifying {target_format} matches analyzed at <b>{c_name}</b>, "
                f"{selected_team1} averaged <b>{f_avg_str}</b> when batting first ({f_cnt} matches) "
                f"and <b>{s_avg_str}</b> when batting second ({s_cnt} matches). "
                f"{selected_team1} won <b>{summary['wins']}</b> matches ({win_pct_str}), "
                f"including <b>{summary['batting_first_wins']}</b> when batting first and <b>{summary['chasing_wins']}</b> when chasing."
            )
        else:
            bf_w = summary["batting_first_wins"]
            ch_w = summary["chasing_wins"]
            bf_pct_str = f"{summary['batting_first_win_percentage']}%" if summary['batting_first_win_percentage'] is not None else "N/A"
            ch_pct_str = f"{summary['chasing_win_percentage']}%" if summary['chasing_win_percentage'] is not None else "N/A"

            insight_text = (
                f"Among the last {act_cnt} qualifying {target_format} matches analyzed at <b>{c_name}</b>, "
                f"the average first-innings score was <b>{f_inn['average']} runs</b> (avg {summary['first_innings_wickets_avg']} wickets lost), "
                f"compared with <b>{s_inn['average']} runs</b> in the second innings (avg {summary['second_innings_wickets_avg']} wickets lost). "
                f"Teams batting first won <b>{bf_w}</b> matches ({bf_pct_str}), while teams chasing won <b>{ch_w}</b> matches ({ch_pct_str})."
            )
            if summary.get("avg_winning_score_batting_first"):
                insight_text += f" The average winning score when batting first at this venue was <b>{summary['avg_winning_score_batting_first']} runs</b>."

        st.markdown(f'<div class="insight-box">{insight_text}</div>', unsafe_allow_html=True)

    # TAB 2: SCORE ANALYSIS
    with tab_score:
        st.subheader(f"First-Innings Score vs Historical Outcome ({target_format})")
        if mode == "single_team":
            st.caption(f"Historical descriptive win rates for {selected_team1}'s 1st innings scores grouped by score bands.")
        else:
            st.caption("Historical descriptive win rates grouped by 1st innings score bands.")

        score_res = match_context["score_ranges"]
        bands_data = score_res.get("score_bands", score_res) if isinstance(score_res, dict) else score_res

        rows = []
        for name, b in bands_data.items():
            pct_disp = f"{b['batting_first_win_percentage']:.1f}%" if b.get("batting_first_win_percentage") is not None else "N/A"
            rows.append({
                "Score Range": b["score_range"],
                "Matches": b["number_of_matches"],
                "Batting First Wins": b["batting_first_wins"],
                "Chasing Wins": b["chasing_wins"],
                "Ties": b["ties"],
                "Batting First Win %": pct_disp,
            })

        table_df = pd.DataFrame(rows)
        st.dataframe(table_df, use_container_width=True, hide_index=True)

        st.markdown("---")

        chart_data = []
        for name, b in bands_data.items():
            if b["number_of_matches"] > 0 and b.get("batting_first_win_percentage") is not None:
                chart_data.append({
                    "Score Range": b["score_range"],
                    "Batting First Win %": b["batting_first_win_percentage"],
                    "Matches": b["number_of_matches"],
                })

        if chart_data:
            chart_df = pd.DataFrame(chart_data)
            fig_bar = px.bar(
                chart_df,
                x="Score Range",
                y="Batting First Win %",
                text="Batting First Win %",
                hover_data=["Matches"],
                color_discrete_sequence=["#1E88E5"],
                title=f"{selected_team1} Batting-First Win Rate by Score Band" if mode == "single_team" else "Historical Batting-First Win Rate by First-Innings Score",
            )
            fig_bar.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
            fig_bar.update_layout(yaxis=dict(range=[0, 110]), height=400)
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.info("Insufficient score-band data available for visualization in this sample.")

    # TAB 3: RECENT MATCHES
    with tab_recent:
        st.subheader("Recent Historical Matches Used in Analysis")
        st.caption("Newest completed matches first. Matches with 'no result' are excluded from score calculations.")

        if mode == "single_team":
            recent_matches = summary.get("qualifying_matches", [])
            meta = {"exclusion_reasons": {"no_result": summary.get("no_results", 0)}}
        else:
            recent_matches, meta = get_recent_matches(target_venue_id, target_format, n=window_n)

        if meta.get("exclusion_reasons", {}).get("no_result", 0) > 0:
            st.info(f"ℹ️ {meta['exclusion_reasons']['no_result']} no-result/abandoned match(es) were excluded from score and win-rate calculations.")

        dl_cnt = sum(1 for m in recent_matches if m.get("is_dl"))
        if dl_cnt > 0:
            st.info(f"ℹ️ {dl_cnt} match(es) in this sample used a DLS/DL adjusted result.")

        if not recent_matches:
            st.warning("No recent matches available.")
        else:
            m_rows = []
            for m in recent_matches:
                inn1 = m.get("innings1") or {}
                inn2 = m.get("innings2") or {}

                res_str = m["result_type"] or "normal"
                if m["winner"]:
                    res_str = f"{m['winner']} won"
                    if m["win_margin"] and m["win_margin_type"]:
                        res_str += f" by {m['win_margin']} {m['win_margin_type']}"

                if mode == "single_team":
                    bat_pos_str = "Batting 1st" if m.get("team_batting_pos") == 1 else "Chasing (2nd)"
                    team_score_str = f"{m.get('team_score', '-')}/{m.get('team_wickets', '-')}" if m.get('team_score') is not None else "-"
                    opp_score_str = f"{m.get('opp_score', '-')}/{m.get('opp_wickets', '-')}" if m.get('opp_score') is not None else "-"
                    m_rows.append({
                        "Date": m["date"],
                        "Opponent": m.get("opponent", "-"),
                        "Batting Position": bat_pos_str,
                        f"{selected_team1} Score": team_score_str,
                        "Opponent Score": opp_score_str,
                        "Winner": m["winner"] or "-",
                        "Result": res_str,
                        "DLS/DL": "Yes" if m["is_dl"] else "No",
                    })
                else:
                    m_rows.append({
                        "Date": m["date"],
                        "Team 1": m["team1"],
                        "Team 2": m["team2"],
                        "1st Innings Team": inn1.get("batting_team", "-"),
                        "1st Innings Score": f"{inn1.get('total_runs', '-')}/{inn1.get('wickets_lost', '-')}",
                        "2nd Innings Team": inn2.get("batting_team", "-"),
                        "2nd Innings Score": f"{inn2.get('total_runs', '-')}/{inn2.get('wickets_lost', '-')}",
                        "Winner": m["winner"] or "-",
                        "Result": res_str,
                        "DLS/DL": "Yes" if m["is_dl"] else "No",
                    })

            match_table_df = pd.DataFrame(m_rows)
            st.dataframe(match_table_df, use_container_width=True, hide_index=True)

    # TAB 4: TEAM ANALYSIS
    with tab_teams:
        st.subheader("Team Specific & Head-to-Head Venue Record")

        if selected_team1 == "None" and selected_team2 == "None":
            st.info("👉 Select Team 1 or Team 2 in the sidebar (or click 'ANALYZE MATCH' on an upcoming fixture) to view team-specific venue performance and head-to-head records.")
        else:
            if selected_team1 != "None" and selected_team2 != "None":
                st.markdown(f"### ⚔️ Head-to-Head: {selected_team1} vs {selected_team2}")
                h2h = match_context.get("head_to_head") or {}

                if h2h.get("total_matches", 0) == 0:
                    st.info(f"No qualifying head-to-head matches found between {selected_team1} and {selected_team2} at {c_name} for {target_format}.")
                else:
                    col1, col2, col3, col4, col5 = st.columns(5)
                    col1.metric("Head-to-Head Matches", h2h.get("total_matches", 0))
                    col2.metric(f"{selected_team1} Wins", h2h.get("team1_wins", 0))
                    col3.metric(f"{selected_team2} Wins", h2h.get("team2_wins", 0))
                    col4.metric("Ties", h2h.get("ties", 0))
                    col5.metric("No Results", h2h.get("no_results", 0))

                st.markdown("---")

            if selected_team1 != "None":
                st.markdown(f"### 🛡️ {selected_team1} — Venue Record ({target_format})")
                t1_stats = match_context.get("team1_stats") or {}

                if t1_stats.get("matches_played", 0) == 0:
                    st.info(f"No matches recorded for {selected_team1} at {c_name} in {target_format}.")
                else:
                    tc1, tc2, tc3, tc4, tc5 = st.columns(5)
                    tc1.metric("Matches Played", t1_stats["matches_played"])
                    tc2.metric("Wins", t1_stats["wins"])
                    tc3.metric("Losses", t1_stats["losses"])
                    tc4.metric("Ties", t1_stats["ties"])
                    tc5.metric("No Results", t1_stats["no_results"])

                    tc6, tc7, tc8, tc9 = st.columns(4)
                    tc6.metric("Average Score", t1_stats.get("average_score") or "N/A")
                    tc7.metric("Highest Score", t1_stats.get("highest_score") or "N/A")
                    tc8.metric("Lowest Score", t1_stats.get("lowest_score") or "N/A")
                    tc9.metric("Batting 1st Wins", t1_stats.get("batting_first_wins", 0))

            if selected_team2 != "None":
                st.markdown(f"### 🛡️ {selected_team2} — Venue Record ({target_format})")
                t2_stats = match_context.get("team2_stats") or {}

                if t2_stats.get("matches_played", 0) == 0:
                    st.info(f"No matches recorded for {selected_team2} at {c_name} in {target_format}.")
                else:
                    tc1, tc2, tc3, tc4, tc5 = st.columns(5)
                    tc1.metric("Matches Played", t2_stats["matches_played"])
                    tc2.metric("Wins", t2_stats["wins"])
                    tc3.metric("Losses", t2_stats["losses"])
                    tc4.metric("Ties", t2_stats["ties"])
                    tc5.metric("No Results", t2_stats["no_results"])

                    tc6, tc7, tc8, tc9 = st.columns(4)
                    tc6.metric("Average Score", t2_stats.get("average_score") or "N/A")
                    tc7.metric("Highest Score", t2_stats.get("highest_score") or "N/A")
                    tc8.metric("Lowest Score", t2_stats.get("lowest_score") or "N/A")
                    tc9.metric("Batting 1st Wins", t2_stats.get("batting_first_wins", 0))


if __name__ == "__main__":
    main()
