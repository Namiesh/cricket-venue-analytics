"""
Cricsheet JSON File Parser.
Safely extracts Match and Innings data structures from a single Cricsheet JSON file.
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from src.processing.venue_normalizer import normalize_venue


def parse_cricsheet_json(file_path: Path, format_tag: str) -> Optional[Tuple[Dict[str, Any], List[Dict[str, Any]]]]:
    """
    Parses a single Cricsheet JSON file.
    Returns (match_record, innings_records) or None if parsing failed or record filtered out.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        match_id = file_path.stem
        info = data.get("info", {})

        # Gender check: Retain only male matches
        gender = info.get("gender")
        if gender != "male":
            return None

        # Team type check: Retain international matches
        team_type = info.get("team_type")
        if team_type != "international":
            return None

        # Dates
        dates = info.get("dates", [])
        primary_date = dates[0] if dates else None

        # Format normalization
        m_type = info.get("match_type", "")
        if format_tag == "ODI" or m_type.upper() == "ODI":
            match_format = "ODI"
        elif format_tag == "T20I" or m_type.upper() in ["T20", "T20I"]:
            match_format = "T20I"
        else:
            match_format = format_tag

        # Teams
        teams = info.get("teams", [])
        team1 = teams[0] if len(teams) > 0 else None
        team2 = teams[1] if len(teams) > 1 else None

        # Toss
        toss = info.get("toss", {})
        toss_winner = toss.get("winner")
        toss_decision = toss.get("decision")

        # Venue & City
        venue_raw = info.get("venue")
        city = info.get("city")
        venue_id = normalize_venue(venue_raw, city)

        # Season
        season = str(info.get("season")) if info.get("season") is not None else None

        # Player of match
        potm = info.get("player_of_match", [])
        if isinstance(potm, list):
            player_of_match = ", ".join(potm) if potm else None
        else:
            player_of_match = str(potm) if potm else None

        # Outcome extraction
        outcome = info.get("outcome", {})
        winner = outcome.get("winner")
        result_type = outcome.get("result")
        method = outcome.get("method")

        # Win margin & type
        win_margin = None
        win_margin_type = None
        by_dict = outcome.get("by", {})
        if "runs" in by_dict:
            win_margin = by_dict["runs"]
            win_margin_type = "runs"
        elif "wickets" in by_dict:
            win_margin = by_dict["wickets"]
            win_margin_type = "wickets"

        # Special result handling
        if result_type == "no result":
            winner = None
        elif result_type == "tie":
            # If tie, winner may be present (super over/eliminator) or None
            pass

        match_record = {
            "match_id": match_id,
            "date": primary_date,
            "format": match_format,
            "gender": gender,
            "team_type": team_type,
            "venue_raw": venue_raw,
            "venue_id": venue_id,
            "city": city,
            "season": season,
            "team1": team1,
            "team2": team2,
            "toss_winner": toss_winner,
            "toss_decision": toss_decision,
            "winner": winner,
            "result_type": result_type,
            "win_margin": win_margin,
            "win_margin_type": win_margin_type,
            "method": method,
            "player_of_match": player_of_match,
        }

        # Innings processing
        innings_records = []
        raw_innings = data.get("innings", [])

        for idx, inn in enumerate(raw_innings, start=1):
            batting_team = inn.get("team")
            target_runs = inn.get("target", {}).get("runs") if isinstance(inn.get("target"), dict) else None

            total_runs = 0
            wickets_lost = 0
            legal_balls = 0

            for over_obj in inn.get("overs", []):
                for d in over_obj.get("deliveries", []):
                    runs_dict = d.get("runs", {})
                    total_runs += runs_dict.get("total", 0)

                    wickets_list = d.get("wickets", [])
                    wickets_lost += len(wickets_list)

                    extras_dict = d.get("extras", {})
                    is_wide = "wides" in extras_dict
                    is_noball = "noballs" in extras_dict
                    if not is_wide and not is_noball:
                        legal_balls += 1

            overs_completed = round((legal_balls // 6) + (legal_balls % 6) / 10.0, 1)

            # Completion heuristic
            is_completed = 1
            if wickets_lost < 10 and (not target_runs or total_runs < target_runs):
                # Check if full overs played
                allotted = 50 if match_format == "ODI" else 20
                if overs_completed < allotted and result_type == "no result":
                    is_completed = 0

            innings_id = f"{match_id}_{idx}"

            innings_record = {
                "innings_id": innings_id,
                "match_id": match_id,
                "innings_number": idx,
                "batting_team": batting_team,
                "total_runs": total_runs,
                "wickets_lost": wickets_lost,
                "overs_completed": overs_completed,
                "balls_delivered": legal_balls,
                "is_completed": is_completed,
                "target_runs": target_runs,
                "result_context": None,
            }
            innings_records.append(innings_record)

        return match_record, innings_records

    except Exception as e:
        raise RuntimeError(f"Error parsing {file_path.name}: {e}") from e
