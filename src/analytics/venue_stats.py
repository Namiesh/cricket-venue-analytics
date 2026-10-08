"""
Venue Statistics Analytics Module.
Calculates recent match statistics, first vs second innings comparisons, and venue summaries.
Operating on canonical venue IDs and alias resolution.
"""

import sqlite3
import statistics
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.processing.venue_normalizer import (
    get_canonical_venue_info,
    get_venue_aliases,
    resolve_venue_search
)

DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "processed" / "cricket_venue.db"


def get_db_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    target_path = db_path or DEFAULT_DB_PATH
    conn = sqlite3.connect(target_path)
    conn.row_factory = sqlite3.Row
    return conn


def get_venues_for_format(format: str, db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Returns all canonical venues that have at least one match for the specified format."""
    fmt = format.upper()
    count_col = "match_count_odi" if fmt == "ODI" else "match_count_t20i"
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT venue_id, canonical_name, city, country, {count_col} as match_count
            FROM venues
            WHERE {count_col} > 0
            ORDER BY canonical_name ASC;
        """)
        return [dict(row) for row in cursor.fetchall()]


def search_venues(search_text: str, db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Searches venues by canonical_name, city, country, venue_id, or alias search."""
    if not search_text or not search_text.strip():
        return []

    resolved = resolve_venue_search(search_text)
    target_id = resolved["canonical_venue_id"] if resolved else None

    query_str = f"%{search_text.strip()}%"
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        if target_id:
            cursor.execute("""
                SELECT venue_id, canonical_name, city, country, raw_name_examples, match_count_odi, match_count_t20i
                FROM venues
                WHERE venue_id = ? OR canonical_name LIKE ? OR city LIKE ? OR country LIKE ? OR raw_name_examples LIKE ?
                ORDER BY (match_count_odi + match_count_t20i) DESC;
            """, (target_id, query_str, query_str, query_str, query_str))
        else:
            cursor.execute("""
                SELECT venue_id, canonical_name, city, country, raw_name_examples, match_count_odi, match_count_t20i
                FROM venues
                WHERE canonical_name LIKE ? OR city LIKE ? OR country LIKE ? OR venue_id LIKE ? OR raw_name_examples LIKE ?
                ORDER BY (match_count_odi + match_count_t20i) DESC;
            """, (query_str, query_str, query_str, query_str, query_str))

        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_venue_by_name(name: str, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Lookup canonical venue by ID, canonical name, or any alias."""
    if not name or not name.strip():
        return None

    canonical_id, c_name, _, _ = get_canonical_venue_info(name)

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()

        # Try exact venue_id match
        cursor.execute("""
            SELECT venue_id, canonical_name, city, country, raw_name_examples, match_count_odi, match_count_t20i
            FROM venues
            WHERE venue_id = ? OR LOWER(canonical_name) = LOWER(?);
        """, (canonical_id, name.strip()))
        row = cursor.fetchone()
        if row:
            return dict(row)

        # Try search in raw_name_examples
        cursor.execute("""
            SELECT venue_id, canonical_name, city, country, raw_name_examples, match_count_odi, match_count_t20i
            FROM venues
            WHERE raw_name_examples LIKE ? OR canonical_name LIKE ?
            LIMIT 1;
        """, (f"%{name.strip()}%", f"%{name.strip()}%"))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_recent_matches(
    venue_id: str,
    format: str,
    n: int = 10,
    db_path: Optional[Path] = None
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Returns (qualifying_matches, metadata) for a given venue and format.
    Resolves venue_id to canonical ID and alias list.
    Excludes no-result and abandoned matches.
    """
    fmt = format.upper()
    if fmt not in ["ODI", "T20I"]:
        raise ValueError("Format must be 'ODI' or 'T20I'.")

    canonical_id, c_name, _, _ = get_canonical_venue_info(venue_id)
    aliases = get_venue_aliases(venue_id)

    alias_placeholders = ", ".join(["?"] * len(aliases))

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        query = f"""
            SELECT match_id, date, format, gender, team_type, venue_raw, venue_id, city, season,
                   team1, team2, toss_winner, toss_decision, winner, result_type, win_margin,
                   win_margin_type, method, player_of_match
            FROM matches
            WHERE (venue_id = ? OR venue_raw IN ({alias_placeholders})) AND format = ?
            ORDER BY date DESC, match_id DESC;
        """
        params = [canonical_id] + list(aliases) + [fmt]
        cursor.execute(query, params)
        all_matches = [dict(row) for row in cursor.fetchall()]

    total_available_at_venue = len(all_matches)
    exclusion_reasons = {"no_result": 0, "missing_innings": 0}

    # First pass: filter no-result / abandoned matches without touching the DB
    candidate_matches = []
    for m in all_matches:
        if m["result_type"] == "no result" or (m["winner"] is None and m["result_type"] not in ["tie", "normal"]):
            exclusion_reasons["no_result"] += 1
        else:
            candidate_matches.append(m)

    # Batch-fetch all innings for candidate matches in a single query
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
            for row in cursor.fetchall():
                r = dict(row)
                innings_lookup.setdefault(r["match_id"], []).append(r)

    # Second pass: enrich matches using the lookup dict
    qualifying_matches = []
    for m in candidate_matches:
        inn_rows = innings_lookup.get(m["match_id"], [])
        if not inn_rows:
            exclusion_reasons["missing_innings"] += 1
            continue

        inn1 = inn_rows[0] if len(inn_rows) >= 1 else None
        inn2 = inn_rows[1] if len(inn_rows) >= 2 else None

        m["innings1"] = inn1
        m["innings2"] = inn2
        m["is_dl"] = m["method"] in ["D/L", "DLS"]

        m["batting_first_won"] = False
        m["chasing_won"] = False
        m["is_tie"] = (m["result_type"] == "tie")

        if m["winner"]:
            if inn1 and m["winner"] == inn1["batting_team"]:
                m["batting_first_won"] = True
            elif inn2 and m["winner"] == inn2["batting_team"]:
                m["chasing_won"] = True

        qualifying_matches.append(m)

    selected_matches = qualifying_matches[:n]

    metadata = {
        "requested_count": n,
        "available_qualifying_count": len(qualifying_matches),
        "total_venue_matches": total_available_at_venue,
        "actual_used_count": len(selected_matches),
        "excluded_count": total_available_at_venue - len(qualifying_matches),
        "exclusion_reasons": exclusion_reasons,
    }

    return selected_matches, metadata


def calculate_venue_summary(
    venue_id: str,
    format: str,
    n: int = 10,
    db_path: Optional[Path] = None
) -> Dict[str, Any]:
    """Calculates comprehensive venue summary for last N qualifying matches."""
    matches, meta = get_recent_matches(venue_id, format, n=n, db_path=db_path)

    venue_info = get_venue_by_name(venue_id, db_path=db_path)
    canonical_id, fallback_c_name, fallback_city, _ = get_canonical_venue_info(venue_id)

    canonical_name = venue_info["canonical_name"] if venue_info else fallback_c_name
    city = venue_info["city"] if venue_info else fallback_city
    country = venue_info["country"] if venue_info else None

    if not matches:
        return {
            "venue_id": canonical_id,
            "canonical_name": canonical_name,
            "city": city,
            "country": country,
            "format": format.upper(),
            "requested_match_count": n,
            "actual_match_count": 0,
            "date_range": None,
            "first_innings": {"average": None, "median": None, "highest": None, "lowest": None},
            "second_innings": {"average": None, "median": None, "highest": None, "lowest": None},
            "first_innings_wickets_avg": None,
            "second_innings_wickets_avg": None,
            "batting_first_wins": 0,
            "chasing_wins": 0,
            "ties": 0,
            "no_results": meta["exclusion_reasons"]["no_result"],
            "batting_first_win_percentage": None,
            "chasing_win_percentage": None,
            "avg_winning_score_batting_first": None,
            "avg_successful_chase_score": None,
            "dl_matches_count": 0,
            "status_message": "Insufficient historical matches available.",
        }

    dates = [m["date"] for m in matches if m["date"]]
    date_range = {"start": min(dates), "end": max(dates)} if dates else None

    inn1_scores = [m["innings1"]["total_runs"] for m in matches if m.get("innings1")]
    inn2_scores = [m["innings2"]["total_runs"] for m in matches if m.get("innings2")]

    inn1_wickets = [m["innings1"]["wickets_lost"] for m in matches if m.get("innings1")]
    inn2_wickets = [m["innings2"]["wickets_lost"] for m in matches if m.get("innings2")]

    batting_first_wins = sum(1 for m in matches if m["batting_first_won"])
    chasing_wins = sum(1 for m in matches if m["chasing_won"])
    ties = sum(1 for m in matches if m["is_tie"])
    dl_count = sum(1 for m in matches if m["is_dl"])

    total_decided = batting_first_wins + chasing_wins + ties
    bf_win_pct = round((batting_first_wins / total_decided) * 100.0, 1) if total_decided > 0 else None
    chase_win_pct = round((chasing_wins / total_decided) * 100.0, 1) if total_decided > 0 else None

    winning_scores_bf = [m["innings1"]["total_runs"] for m in matches if m["batting_first_won"] and m.get("innings1")]
    winning_scores_chase = [m["innings2"]["total_runs"] for m in matches if m["chasing_won"] and m.get("innings2")]

    avg_win_bf = round(sum(winning_scores_bf) / len(winning_scores_bf), 1) if winning_scores_bf else None
    avg_win_chase = round(sum(winning_scores_chase) / len(winning_scores_chase), 1) if winning_scores_chase else None

    def calc_stats(scores: List[int]) -> Dict[str, Optional[float]]:
        if not scores:
            return {"average": None, "median": None, "highest": None, "lowest": None}
        return {
            "average": round(sum(scores) / len(scores), 1),
            "median": round(statistics.median(scores), 1),
            "highest": max(scores),
            "lowest": min(scores),
        }

    return {
        "venue_id": canonical_id,
        "canonical_name": canonical_name,
        "city": city,
        "country": country,
        "format": format.upper(),
        "requested_match_count": n,
        "actual_match_count": len(matches),
        "date_range": date_range,
        "first_innings": calc_stats(inn1_scores),
        "second_innings": calc_stats(inn2_scores),
        "first_innings_wickets_avg": round(sum(inn1_wickets) / len(inn1_wickets), 1) if inn1_wickets else None,
        "second_innings_wickets_avg": round(sum(inn2_wickets) / len(inn2_wickets), 1) if inn2_wickets else None,
        "batting_first_wins": batting_first_wins,
        "chasing_wins": chasing_wins,
        "ties": ties,
        "no_results": meta["exclusion_reasons"]["no_result"],
        "batting_first_win_percentage": bf_win_pct,
        "chasing_win_percentage": chase_win_pct,
        "avg_winning_score_batting_first": avg_win_bf,
        "avg_successful_chase_score": avg_win_chase,
        "dl_matches_count": dl_count,
        "status_message": "OK" if len(matches) >= n else f"Note: Only {len(matches)} historical matches available.",
    }
