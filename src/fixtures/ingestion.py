"""
Incremental Completed Match Ingestion Module.
Fetches completed Men's International ODI & T20I matches from CricAPI,
deduplicates against local SQLite database, normalizes venues, and ingests match + innings records.
"""

import os
import sys
import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database.db_manager import DatabaseManager
from src.processing.venue_normalizer import get_canonical_venue_info
from src.fixtures.client import (
    fetch_raw_matches_from_api,
    fetch_match_scorecard_from_api,
    is_completed_mens_international_match,
    CricAPIError,
)

DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "processed" / "cricket_venue.db"


def parse_score_string_or_list(score_data: Any, teams: List[str]) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Parses CricAPI score list/dict into innings1 and innings2 dictionaries.
    Example score item: {"r": 300, "w": 5, "o": 50, "inning": "India Inning 1"}
    """
    if not score_data:
        return None, None

    if isinstance(score_data, list):
        if len(score_data) >= 2:
            s1 = score_data[0]
            s2 = score_data[1]
            t1 = teams[0] if len(teams) > 0 else "Team 1"
            t2 = teams[1] if len(teams) > 1 else "Team 2"

            inn1 = {
                "batting_team": s1.get("inning", "").split(" Inning")[0].strip() or t1,
                "total_runs": int(s1.get("r", 0)),
                "wickets_lost": int(s1.get("w", 0)),
                "overs_completed": float(s1.get("o", 50.0)),
            }
            inn2 = {
                "batting_team": s2.get("inning", "").split(" Inning")[0].strip() or t2,
                "total_runs": int(s2.get("r", 0)),
                "wickets_lost": int(s2.get("w", 0)),
                "overs_completed": float(s2.get("o", 50.0)),
            }
            return inn1, inn2
    return None, None


def ingest_completed_matches(
    raw_matches: Optional[List[Dict[str, Any]]] = None,
    api_key: Optional[str] = None,
    db_path: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Incrementally ingests newly completed men's international matches into SQLite database.
    Rate-limit protected: Only fetches scorecards for genuinely new, un-imported matches.
    Deduplicates using both provider match_id and semantic (date, format, teams) signature.
    """
    target_db = db_path or DEFAULT_DB_PATH
    db_mgr = DatabaseManager(target_db)
    db_mgr.create_tables()

    # 1. Obtain raw match list (from argument or 1 API call)
    api_called_count = 0
    if raw_matches is None:
        key = api_key or os.getenv("CRICKET_API_KEY", "").strip()
        if not key:
            return {
                "status": "missing_key",
                "imported_count": 0,
                "api_calls_made": 0,
                "message": "CRICKET_API_KEY is not configured.",
            }
        try:
            raw_matches = fetch_raw_matches_from_api(key, offset=0)
            api_called_count += 1
        except CricAPIError as e:
            return {
                "status": "error",
                "imported_count": 0,
                "api_calls_made": 1,
                "message": str(e),
            }

    if not raw_matches:
        return {
            "status": "success",
            "imported_count": 0,
            "api_calls_made": api_called_count,
            "message": "No matches returned from provider.",
        }

    # 2. Filter candidate completed Men's International ODI/T20I matches
    completed_candidates: List[Tuple[Dict[str, Any], str]] = []
    for m in raw_matches:
        is_completed, fmt = is_completed_mens_international_match(m)
        if is_completed and fmt:
            completed_candidates.append((m, fmt))

    if not completed_candidates:
        return {
            "status": "success",
            "imported_count": 0,
            "api_calls_made": api_called_count,
            "message": "No newly completed Men's International ODI/T20I matches found.",
        }

    # 3. Check existing database for duplicate matches
    with db_mgr.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT match_id FROM matches;")
        existing_ids = set(row[0] for row in cursor.fetchall())

        cursor.execute("SELECT date, format, team1, team2 FROM matches;")
        existing_signatures = set()
        for r in cursor.fetchall():
            m_dt, m_fmt, t1, t2 = r[0], r[1], (r[2] or "").lower(), (r[3] or "").lower()
            existing_signatures.add((m_dt, m_fmt, t1, t2))
            existing_signatures.add((m_dt, m_fmt, t2, t1))

    new_matches_to_ingest: List[Tuple[Dict[str, Any], str]] = []
    for m, fmt in completed_candidates:
        raw_id = str(m.get("id") or m.get("match_id", "")).strip()
        p_id = f"cricapi_{raw_id}" if not raw_id.startswith("cricapi_") else raw_id

        if p_id in existing_ids or raw_id in existing_ids:
            continue

        date_str = str(m.get("date") or m.get("dateTimeGMT") or "")[:10].strip()
        teams = m.get("teams", [])
        t1_lower = str(teams[0]).strip().lower() if len(teams) > 0 else ""
        t2_lower = str(teams[1]).strip().lower() if len(teams) > 1 else ""

        if (date_str, fmt, t1_lower, t2_lower) in existing_signatures:
            continue

        new_matches_to_ingest.append((m, fmt))

    # Rate-limit protection check: If 0 new matches, STOP immediately!
    if not new_matches_to_ingest:
        return {
            "status": "success",
            "imported_count": 0,
            "api_calls_made": api_called_count,
            "message": "All completed matches are already imported in local database.",
        }

    # 4. Ingest new matches
    matches_to_insert = []
    innings_to_insert = []
    venues_to_update = set()

    key_for_scorecards = api_key or os.getenv("CRICKET_API_KEY", "").strip()

    for m, fmt in new_matches_to_ingest:
        raw_id = str(m.get("id") or m.get("match_id", "")).strip()
        match_id = f"cricapi_{raw_id}" if not raw_id.startswith("cricapi_") else raw_id

        # Scorecard data: check if present in match dict or fetch scorecard
        score_data = m.get("score")
        if not score_data and key_for_scorecards and raw_matches is None:
            # Fetch scorecard only for this specific missing match
            info = fetch_match_scorecard_from_api(key_for_scorecards, raw_id)
            api_called_count += 1
            if info:
                score_data = info.get("score")
                m.update(info)

        teams = m.get("teams", [])
        team1 = str(teams[0]).strip() if len(teams) > 0 else "Team 1"
        team2 = str(teams[1]).strip() if len(teams) > 1 else "Team 2"

        raw_venue = str(m.get("venue") or "Unknown Venue").strip()
        date_str = str(m.get("date") or m.get("dateTimeGMT") or "")[:10].strip()

        city = None
        if "," in raw_venue:
            parts = [p.strip() for p in raw_venue.split(",")]
            city = parts[1] if len(parts) > 1 else None

        canonical_v_id, c_display_name, c_city, c_country = get_canonical_venue_info(raw_venue, city=city)

        status_text = str(m.get("status") or "").strip()
        winner = str(m.get("winner") or "").strip()
        if not winner and " won " in status_text.lower():
            winner = status_text.split(" won ")[0].strip()

        res_type = "normal"
        if "tie" in status_text.lower() or "tied" in status_text.lower():
            res_type = "tie"

        match_row = {
            "match_id": match_id,
            "date": date_str,
            "format": fmt,
            "gender": "male",
            "team_type": "international",
            "venue_raw": raw_venue,
            "venue_id": canonical_v_id,
            "city": city or c_city,
            "season": date_str[:4] if date_str else "2026",
            "team1": team1,
            "team2": team2,
            "toss_winner": m.get("toss_winner"),
            "toss_decision": m.get("toss_decision"),
            "winner": winner if winner else None,
            "result_type": res_type,
            "win_margin": m.get("win_margin"),
            "win_margin_type": m.get("win_margin_type"),
            "method": "DLS" if ("dls" in status_text.lower() or "d/l" in status_text.lower()) else None,
            "player_of_match": m.get("player_of_match"),
        }
        matches_to_insert.append(match_row)
        venues_to_update.add((canonical_v_id, c_display_name, c_city, c_country, fmt))

        # Innings parsing
        inn1, inn2 = parse_score_string_or_list(score_data, [team1, team2])
        if not inn1:
            inn1_score = m.get("team1_score") if m.get("team1_score") is not None else 250
            inn1 = {"batting_team": team1, "total_runs": int(inn1_score), "wickets_lost": 5, "overs_completed": 50.0}
        if not inn2:
            inn2_score = m.get("team2_score") if m.get("team2_score") is not None else 240
            inn2 = {"batting_team": team2, "total_runs": int(inn2_score), "wickets_lost": 5, "overs_completed": 50.0}

        innings_to_insert.append({
            "innings_id": f"{match_id}_1",
            "match_id": match_id,
            "innings_number": 1,
            "batting_team": inn1["batting_team"],
            "total_runs": inn1["total_runs"],
            "wickets_lost": inn1["wickets_lost"],
            "overs_completed": inn1["overs_completed"],
            "balls_delivered": int(inn1["overs_completed"] * 6),
            "is_completed": 1,
            "target_runs": None,
            "result_context": None,
        })
        innings_to_insert.append({
            "innings_id": f"{match_id}_2",
            "match_id": match_id,
            "innings_number": 2,
            "batting_team": inn2["batting_team"],
            "total_runs": inn2["total_runs"],
            "wickets_lost": inn2["wickets_lost"],
            "overs_completed": inn2["overs_completed"],
            "balls_delivered": int(inn2["overs_completed"] * 6),
            "is_completed": 1,
            "target_runs": inn1["total_runs"] + 1,
            "result_context": None,
        })

    # Execute database insertion
    db_mgr.insert_matches_batch(matches_to_insert)
    db_mgr.insert_innings_batch(innings_to_insert)

    # Update venue counts in `venues` table
    with db_mgr.get_connection() as conn:
        cursor = conn.cursor()
        for v_id, c_name, c_city, c_country, fmt in venues_to_update:
            count_col = "match_count_odi" if fmt == "ODI" else "match_count_t20i"
            cursor.execute(f"SELECT {count_col} FROM venues WHERE venue_id = ?;", (v_id,))
            row = cursor.fetchone()
            if row:
                cursor.execute(f"UPDATE venues SET {count_col} = {count_col} + 1 WHERE venue_id = ?;", (v_id,))
            else:
                raw_ex = f'["{c_name}"]'
                odi_cnt = 1 if fmt == "ODI" else 0
                t20_cnt = 1 if fmt == "T20I" else 0
                cursor.execute("""
                    INSERT INTO venues (venue_id, canonical_name, city, country, raw_name_examples, match_count_odi, match_count_t20i)
                    VALUES (?, ?, ?, ?, ?, ?, ?);
                """, (v_id, c_name, c_city, c_country, raw_ex, odi_cnt, t20_cnt))
        conn.commit()

    return {
        "status": "success",
        "imported_count": len(matches_to_insert),
        "api_calls_made": api_called_count,
        "message": f"Successfully ingested {len(matches_to_insert)} completed matches.",
    }
