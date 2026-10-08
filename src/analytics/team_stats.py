"""
Team & Head-to-Head Venue Statistics Module.
Calculates team-specific venue statistics, single-team venue analysis, and head-to-head match context.
Operating on canonical venue IDs and alias resolution.
"""

import sys
import statistics
from pathlib import Path
from typing import Dict, Any, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.processing.venue_normalizer import get_canonical_venue_info, get_venue_aliases
from src.analytics.venue_stats import (
    get_db_connection,
    calculate_venue_summary,
    get_venue_by_name
)
from src.analytics.score_analysis import analyze_score_ranges, get_score_bands_for_format


def get_teams_for_venue_format(venue_id: str, format: str, db_path: Optional[Path] = None) -> List[str]:
    """Returns sorted list of team names that have played at venue_id (or any of its aliases) in format."""
    fmt = format.upper()
    canonical_id, _, _, _ = get_canonical_venue_info(venue_id)
    aliases = get_venue_aliases(venue_id)
    alias_placeholders = ", ".join(["?"] * len(aliases))

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        query = f"""
            SELECT DISTINCT team1 FROM matches WHERE (venue_id = ? OR venue_raw IN ({alias_placeholders})) AND format = ?
            UNION
            SELECT DISTINCT team2 FROM matches WHERE (venue_id = ? OR venue_raw IN ({alias_placeholders})) AND format = ?
        """
        params = [canonical_id] + list(aliases) + [fmt, canonical_id] + list(aliases) + [fmt]
        cursor.execute(query, params)
        teams = [r[0] for r in cursor.fetchall() if r[0]]
        return sorted(teams)


def get_team_venue_stats(
    team: str,
    venue_id: str,
    format: str,
    n: Optional[int] = None,
    db_path: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Calculates team-specific historical statistics at a venue for a given format.
    Default n=None processes all available historical matches across venue aliases.
    """
    fmt = format.upper()
    canonical_id, c_display_name, c_city, c_country = get_canonical_venue_info(venue_id)
    aliases = get_venue_aliases(venue_id)
    alias_placeholders = ", ".join(["?"] * len(aliases))

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        query = f"""
            SELECT match_id, date, format, team1, team2, winner, result_type
            FROM matches
            WHERE (venue_id = ? OR venue_raw IN ({alias_placeholders})) AND format = ? AND (team1 = ? OR team2 = ?)
            ORDER BY date DESC, match_id DESC;
        """
        params = [canonical_id] + list(aliases) + [fmt, team, team]
        cursor.execute(query, params)
        rows = [dict(r) for r in cursor.fetchall()]

    if n is not None:
        rows = rows[:n]

    matches_played = len(rows)
    wins = 0
    losses = 0
    ties = 0
    no_results = 0
    batting_first_wins = 0
    chasing_wins = 0

    scores = []
    first_inn_scores = []
    second_inn_scores = []

    # Batch-fetch innings for all matches in a single query
    innings_lookup: Dict[str, List[Dict[str, Any]]] = {}
    if rows:
        match_ids = [m["match_id"] for m in rows]
        placeholders = ", ".join(["?"] * len(match_ids))
        with get_db_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT match_id, innings_number, batting_team, total_runs
                FROM innings
                WHERE match_id IN ({placeholders}) AND batting_team = ? AND innings_number IN (1, 2);
            """, match_ids + [team])
            for r in cursor.fetchall():
                rd = dict(r)
                innings_lookup.setdefault(rd["match_id"], []).append(rd)

    for m in rows:
        match_id = m["match_id"]
        res_type = m["result_type"]
        winner = m["winner"]

        if res_type == "no result":
            no_results += 1
        elif res_type == "tie":
            ties += 1
            if winner == team:
                wins += 1
            elif winner is not None:
                losses += 1
        elif winner == team:
            wins += 1
        elif winner is not None:
            losses += 1

        for inn in innings_lookup.get(match_id, []):
            tot = inn["total_runs"]
            scores.append(tot)
            if inn["innings_number"] == 1:
                first_inn_scores.append(tot)
                if winner == team:
                    batting_first_wins += 1
            elif inn["innings_number"] == 2:
                second_inn_scores.append(tot)
                if winner == team:
                    chasing_wins += 1

    win_pct = round((wins / matches_played) * 100.0, 1) if matches_played > 0 else None

    avg_score = round(sum(scores) / len(scores), 1) if scores else None
    avg_1st = round(sum(first_inn_scores) / len(first_inn_scores), 1) if first_inn_scores else None
    avg_2nd = round(sum(second_inn_scores) / len(second_inn_scores), 1) if second_inn_scores else None

    highest = max(scores) if scores else None
    lowest = min(scores) if scores else None

    return {
        "team": team,
        "venue_id": canonical_id,
        "canonical_name": c_display_name,
        "format": fmt,
        "matches_played": matches_played,
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "no_results": no_results,
        "win_percentage": win_pct,
        "batting_first_wins": batting_first_wins,
        "chasing_wins": chasing_wins,
        "average_score": avg_score,
        "average_1st_innings": avg_1st,
        "average_2nd_innings": avg_2nd,
        "highest_score": highest,
        "lowest_score": lowest,
    }


def get_head_to_head_stats(
    team1: str,
    team2: str,
    venue_id: str,
    format: str,
    db_path: Optional[Path] = None
) -> Dict[str, Any]:
    """Calculates head-to-head historical record between team1 and team2 at venue_id for format."""
    fmt = format.upper()
    canonical_id, c_display_name, c_city, c_country = get_canonical_venue_info(venue_id)
    aliases = get_venue_aliases(venue_id)
    alias_placeholders = ", ".join(["?"] * len(aliases))

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        query = f"""
            SELECT match_id, date, format, team1, team2, winner, result_type
            FROM matches
            WHERE (venue_id = ? OR venue_raw IN ({alias_placeholders})) AND format = ?
              AND ((team1 = ? AND team2 = ?) OR (team1 = ? AND team2 = ?))
            ORDER BY date DESC;
        """
        params = [canonical_id] + list(aliases) + [fmt, team1, team2, team2, team1]
        cursor.execute(query, params)
        rows = [dict(r) for r in cursor.fetchall()]

    total_matches = len(rows)
    team1_wins = sum(1 for m in rows if m["winner"] == team1)
    team2_wins = sum(1 for m in rows if m["winner"] == team2)
    ties = sum(1 for m in rows if m["result_type"] == "tie")
    no_results = sum(1 for m in rows if m["result_type"] == "no result")

    t1_scores = []
    t2_scores = []

    # Batch-fetch innings for all H2H matches in a single query
    innings_lookup: Dict[str, List[Dict[str, Any]]] = {}
    if rows:
        match_ids = [m["match_id"] for m in rows]
        placeholders = ", ".join(["?"] * len(match_ids))
        with get_db_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT match_id, batting_team, total_runs
                FROM innings
                WHERE match_id IN ({placeholders}) AND innings_number IN (1, 2);
            """, match_ids)
            for r in cursor.fetchall():
                rd = dict(r)
                innings_lookup.setdefault(rd["match_id"], []).append(rd)

    for m in rows:
        for inn in innings_lookup.get(m["match_id"], []):
            b_team = inn["batting_team"]
            tot = inn["total_runs"]
            if b_team == team1:
                t1_scores.append(tot)
            elif b_team == team2:
                t2_scores.append(tot)

    return {
        "team1": team1,
        "team2": team2,
        "venue_id": canonical_id,
        "canonical_name": c_display_name,
        "format": fmt,
        "total_matches": total_matches,
        "matches": total_matches,
        "team1_wins": team1_wins,
        "team2_wins": team2_wins,
        "ties": ties,
        "no_results": no_results,
        "team1_avg_score": round(sum(t1_scores) / len(t1_scores), 1) if t1_scores else None,
        "team2_avg_score": round(sum(t2_scores) / len(t2_scores), 1) if t2_scores else None,
        "team1_highest_score": max(t1_scores) if t1_scores else None,
        "team2_highest_score": max(t2_scores) if t2_scores else None,
        "team1_lowest_score": min(t1_scores) if t1_scores else None,
        "team2_lowest_score": min(t2_scores) if t2_scores else None,
        "last_match_date": rows[0]["date"] if rows else None,
        "last_match_winner": rows[0]["winner"] if rows else None,
    }


def get_team_venue_analysis(
    team: str,
    venue_id: str,
    format: str,
    n: int = 10,
    db_path: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Calculates team-specific historical venue analytics when exactly ONE team is selected.
    Filter pipeline:
      FORMAT -> CANONICAL VENUE -> SELECTED TEAM PARTICIPATION -> QUALIFYING MATCHES -> SORT BY DATE DESC -> TAKE LAST N
    """
    fmt = format.upper()
    if fmt not in ["ODI", "T20I"]:
        raise ValueError("Format must be 'ODI' or 'T20I'.")

    canonical_id, c_display_name, c_city, c_country = get_canonical_venue_info(venue_id)
    aliases = get_venue_aliases(venue_id)
    alias_placeholders = ", ".join(["?"] * len(aliases))

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        query = f"""
            SELECT match_id, date, format, gender, team_type, venue_raw, venue_id, city, season,
                   team1, team2, toss_winner, toss_decision, winner, result_type, win_margin,
                   win_margin_type, method, player_of_match
            FROM matches
            WHERE (venue_id = ? OR venue_raw IN ({alias_placeholders})) AND format = ? AND (team1 = ? OR team2 = ?)
            ORDER BY date DESC, match_id DESC;
        """
        params = [canonical_id] + list(aliases) + [fmt, team, team]
        cursor.execute(query, params)
        all_team_matches = [dict(row) for row in cursor.fetchall()]

    # First pass: filter no-result matches without touching the DB
    no_results_count = 0
    candidate_matches = []
    for m in all_team_matches:
        if m["result_type"] == "no result" or (m["winner"] is None and m["result_type"] not in ["tie", "normal"]):
            no_results_count += 1
        else:
            candidate_matches.append(m)

    # Batch-fetch innings for all candidate matches in a single query
    innings_lookup: Dict[str, List[Dict[str, Any]]] = {}
    if candidate_matches:
        candidate_ids = [m["match_id"] for m in candidate_matches]
        placeholders = ", ".join(["?"] * len(candidate_ids))
        with get_db_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT innings_id, match_id, innings_number, batting_team, total_runs, wickets_lost,
                       overs_completed, balls_delivered, is_completed, target_runs, result_context
                FROM innings
                WHERE match_id IN ({placeholders}) AND innings_number IN (1, 2)
                ORDER BY match_id, innings_number ASC;
            """, candidate_ids)
            for r in cursor.fetchall():
                rd = dict(r)
                innings_lookup.setdefault(rd["match_id"], []).append(rd)

    # Second pass: enrich matches using the lookup dict
    qualifying_matches = []
    for m in candidate_matches:
        match_id = m["match_id"]
        inn_rows = innings_lookup.get(match_id, [])

        if not inn_rows:
            continue

        inn1 = inn_rows[0] if len(inn_rows) >= 1 else None
        inn2 = inn_rows[1] if len(inn_rows) >= 2 else None

        m["innings1"] = inn1
        m["innings2"] = inn2
        m["is_dl"] = m["method"] in ["D/L", "DLS"]

        # Determine team's batting position & score
        opponent = m["team2"] if m["team1"] == team else m["team1"]
        m["opponent"] = opponent

        team_batting_pos = None
        team_score = None
        team_wickets = None
        opp_score = None
        opp_wickets = None

        if inn1 and inn1["batting_team"] == team:
            team_batting_pos = 1
            team_score = inn1["total_runs"]
            team_wickets = inn1["wickets_lost"]
            if inn2:
                opp_score = inn2["total_runs"]
                opp_wickets = inn2["wickets_lost"]
        elif inn2 and inn2["batting_team"] == team:
            team_batting_pos = 2
            team_score = inn2["total_runs"]
            team_wickets = inn2["wickets_lost"]
            if inn1:
                opp_score = inn1["total_runs"]
                opp_wickets = inn1["wickets_lost"]

        m["team_batting_pos"] = team_batting_pos
        m["team_score"] = team_score
        m["team_wickets"] = team_wickets
        m["opp_score"] = opp_score
        m["opp_wickets"] = opp_wickets

        m["team_won"] = (m["winner"] == team)
        m["team_lost"] = (m["winner"] is not None and m["winner"] != team and m["result_type"] != "tie")
        m["is_tie"] = (m["result_type"] == "tie")

        qualifying_matches.append(m)

    total_team_venue_matches = len(qualifying_matches)
    selected_matches = qualifying_matches[:n]

    if not selected_matches:
        return {
            "mode": "single_team",
            "team": team,
            "venue_id": canonical_id,
            "canonical_name": c_display_name,
            "city": c_city,
            "country": c_country,
            "format": fmt,
            "requested_match_count": n,
            "actual_match_count": 0,
            "total_team_venue_matches": 0,
            "date_range": None,
            "first_innings": {"average": None, "median": None, "highest": None, "lowest": None, "sample_count": 0},
            "second_innings": {"average": None, "median": None, "highest": None, "lowest": None, "sample_count": 0},
            "first_innings_wickets_avg": None,
            "second_innings_wickets_avg": None,
            "wins": 0,
            "losses": 0,
            "ties": 0,
            "no_results": no_results_count,
            "win_percentage": None,
            "batting_first_wins": 0,
            "chasing_wins": 0,
            "qualifying_matches": [],
            "score_bands": {},
            "status_message": f"No qualifying matches found for {team} at {c_display_name} in {fmt}.",
        }

    dates = [m["date"] for m in selected_matches if m["date"]]
    date_range = {"start": min(dates), "end": max(dates)} if dates else None

    inn1_scores = [m["team_score"] for m in selected_matches if m["team_batting_pos"] == 1 and m["team_score"] is not None]
    inn2_scores = [m["team_score"] for m in selected_matches if m["team_batting_pos"] == 2 and m["team_score"] is not None]

    inn1_wickets = [m["team_wickets"] for m in selected_matches if m["team_batting_pos"] == 1 and m["team_wickets"] is not None]
    inn2_wickets = [m["team_wickets"] for m in selected_matches if m["team_batting_pos"] == 2 and m["team_wickets"] is not None]

    wins = sum(1 for m in selected_matches if m["team_won"])
    losses = sum(1 for m in selected_matches if m["team_lost"])
    ties = sum(1 for m in selected_matches if m["is_tie"])
    batting_first_wins = sum(1 for m in selected_matches if m["team_batting_pos"] == 1 and m["team_won"])
    chasing_wins = sum(1 for m in selected_matches if m["team_batting_pos"] == 2 and m["team_won"])

    total_decided = wins + losses + ties
    win_pct = round((wins / total_decided) * 100.0, 1) if total_decided > 0 else None

    def calc_team_stats(scores: List[int]) -> Dict[str, Any]:
        if not scores:
            return {"average": None, "median": None, "highest": None, "lowest": None, "sample_count": 0}
        return {
            "average": round(sum(scores) / len(scores), 1),
            "median": round(statistics.median(scores), 1),
            "highest": max(scores),
            "lowest": min(scores),
            "sample_count": len(scores),
        }

    # Score bands for team's scores
    bands = get_score_bands_for_format(fmt)
    team_band_results = {}
    for b in bands:
        name = b["name"]
        team_band_results[name] = {
            "score_range": name,
            "min_score": b["min"],
            "max_score": b["max"],
            "number_of_matches": 0,
            "batting_first_wins": 0,
            "chasing_wins": 0,
            "ties": 0,
            "batting_first_win_percentage": None,
        }

    for m in selected_matches:
        if m["team_batting_pos"] == 1 and m["team_score"] is not None:
            sc = m["team_score"]
            for b in bands:
                if b["min"] <= sc <= b["max"]:
                    res = team_band_results[b["name"]]
                    res["number_of_matches"] += 1
                    if m["team_won"]:
                        res["batting_first_wins"] += 1
                    elif m["team_lost"]:
                        res["chasing_wins"] += 1
                    elif m["is_tie"]:
                        res["ties"] += 1
                    break

    for name, res in team_band_results.items():
        if res["number_of_matches"] > 0:
            res["batting_first_win_percentage"] = round((res["batting_first_wins"] / res["number_of_matches"]) * 100.0, 1)

    return {
        "mode": "single_team",
        "team": team,
        "venue_id": canonical_id,
        "canonical_name": c_display_name,
        "city": c_city,
        "country": c_country,
        "format": fmt,
        "requested_match_count": n,
        "actual_match_count": len(selected_matches),
        "total_team_venue_matches": total_team_venue_matches,
        "date_range": date_range,
        "first_innings": calc_team_stats(inn1_scores),
        "second_innings": calc_team_stats(inn2_scores),
        "first_innings_wickets_avg": round(sum(inn1_wickets) / len(inn1_wickets), 1) if inn1_wickets else None,
        "second_innings_wickets_avg": round(sum(inn2_wickets) / len(inn2_wickets), 1) if inn2_wickets else None,
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "no_results": no_results_count,
        "win_percentage": win_pct,
        "batting_first_wins": batting_first_wins,
        "chasing_wins": chasing_wins,
        "qualifying_matches": selected_matches,
        "score_bands": team_band_results,
        "status_message": "OK" if len(selected_matches) >= n else f"Note: Only {len(selected_matches)} historical matches available for {team} at this venue.",
    }


def analyze_match_context(
    team1: Optional[str],
    team2: Optional[str],
    venue_id: str,
    format: str,
    n_venue_matches: int = 10,
    db_path: Optional[Path] = None
) -> Dict[str, Any]:
    """Combines venue summary, team stats, head-to-head stats, and score ranges into a single unified payload."""
    canonical_id, c_display_name, c_city, c_country = get_canonical_venue_info(venue_id)

    t1_valid = bool(team1 and team1 != "None" and team1 != "Team A")
    t2_valid = bool(team2 and team2 != "None" and team2 != "Team B")

    # MODE B: Single Team Analysis (Only Team 1 selected)
    if t1_valid and not t2_valid:
        single_analysis = get_team_venue_analysis(team1, canonical_id, format, n=n_venue_matches, db_path=db_path)
        return {
            "mode": "single_team",
            "team1": team1,
            "team2": None,
            "venue_id": canonical_id,
            "canonical_name": c_display_name,
            "format": format.upper(),
            "status_message": single_analysis.get("status_message", "OK"),
            "venue_summary": single_analysis,
            "team_analysis": single_analysis,
            "score_ranges": single_analysis["score_bands"],
            "score_analysis": {"score_bands": single_analysis["score_bands"]},
            "team1_stats": get_team_venue_stats(team1, canonical_id, format, db_path=db_path),
            "team1_venue_stats": get_team_venue_stats(team1, canonical_id, format, db_path=db_path),
            "team2_stats": None,
            "team2_venue_stats": None,
            "head_to_head": None,
        }

    # MODE C: Two Team Head-to-Head Analysis (Team 1 + Team 2 selected)
    elif t1_valid and t2_valid:
        v_summary = calculate_venue_summary(canonical_id, format, n=n_venue_matches, db_path=db_path)
        score_ranges = analyze_score_ranges(canonical_id, format, n=n_venue_matches, db_path=db_path)
        t1_stats = get_team_venue_stats(team1, canonical_id, format, db_path=db_path)
        t2_stats = get_team_venue_stats(team2, canonical_id, format, db_path=db_path)
        h2h_stats = get_head_to_head_stats(team1, team2, canonical_id, format, db_path=db_path)

        return {
            "mode": "two_team",
            "team1": team1,
            "team2": team2,
            "venue_id": canonical_id,
            "canonical_name": c_display_name,
            "format": format.upper(),
            "status_message": v_summary.get("status_message", "OK"),
            "venue_summary": v_summary,
            "score_ranges": score_ranges,
            "score_analysis": {"score_bands": score_ranges},
            "team1_stats": t1_stats,
            "team1_venue_stats": t1_stats,
            "team2_stats": t2_stats,
            "team2_venue_stats": t2_stats,
            "head_to_head": h2h_stats,
        }

    # MODE A: Venue-Wide Analysis (No teams selected)
    else:
        v_summary = calculate_venue_summary(canonical_id, format, n=n_venue_matches, db_path=db_path)
        score_ranges = analyze_score_ranges(canonical_id, format, n=n_venue_matches, db_path=db_path)

        return {
            "mode": "venue_wide",
            "team1": None,
            "team2": None,
            "venue_id": canonical_id,
            "canonical_name": c_display_name,
            "format": format.upper(),
            "status_message": v_summary.get("status_message", "OK"),
            "venue_summary": v_summary,
            "score_ranges": score_ranges,
            "score_analysis": {"score_bands": score_ranges},
            "team1_stats": None,
            "team1_venue_stats": None,
            "team2_stats": None,
            "team2_venue_stats": None,
            "head_to_head": None,
        }
