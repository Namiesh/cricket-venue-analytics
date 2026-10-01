"""
CricAPI Client & Fixture Filtering Module.
Fetches raw match data from CricAPI /v1/matches and filters for Men's International ODI & T20I matches.
"""

import os
import re
import requests
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime, timezone
from src.fixtures.models import UpcomingFixture
from src.fixtures.normalizer import resolve_fixture_venue

# Franchise, domestic, and non-international team keywords to EXCLUDE
EXCLUDED_SERIES_KEYWORDS = [
    "ipl", "indian premier league", "bbl", "big bash", "psl", "pakistan super league",
    "cpl", "caribbean premier league", "ilt20", "sa20", "mlc", "major league cricket",
    "super smash", "t20 blast", "wpl", "wbbl", "t10", "sixty", "lpl", "lanka premier league",
    "hundred", "ranji", "vijay hazare", "syed mushtaq", "marsh cup", "county", "sheffield shield",
    "plunket shield", "ford trophy", "trophy", "franchise", "legends", "t20 cup",
    "invitation xi", "xi", "prime minister", "governor", "a team", " touring ", "warm-up"
]

# Recognized International Men's Teams
INTERNATIONAL_MENS_TEAMS = {
    "india", "australia", "england", "new zealand", "south africa", "pakistan",
    "sri lanka", "west indies", "bangladesh", "afghanistan", "ireland", "zimbabwe",
    "netherlands", "scotland", "united states", "usa", "uae", "united arab emirates",
    "nepal", "namibia", "oman", "papua new guinea", "png", "canada", "jersey", "uganda",
    "hong kong", "bermuda", "italy", "kenya", "singapore", "malaysia", "spain"
}


class CricAPIError(Exception):
    """Custom exception for CricAPI HTTP / API failures."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


def fetch_raw_matches_from_api(api_key: str, offset: int = 0) -> List[Dict[str, Any]]:
    """Performs HTTP GET request to CricAPI /v1/matches."""
    clean_key = api_key.strip() if api_key else ""
    if not clean_key:
        raise CricAPIError("CRICKET_API_KEY is not configured.", status_code=401)

    url = "https://api.cricapi.com/v1/matches"
    params = {"apikey": clean_key, "offset": offset}

    try:
        response = requests.get(url, params=params, timeout=10)
    except requests.exceptions.Timeout as e:
        raise CricAPIError("Cricket fixture request timed out. Using cached data.", status_code=504) from e
    except requests.exceptions.RequestException as e:
        raise CricAPIError("Cricket fixture service is temporarily unavailable. Using cached data.", status_code=500) from e

    if response.status_code in (401, 403):
        raise CricAPIError("Cricket API authentication failed. Check CRICKET_API_KEY.", status_code=response.status_code)
    elif response.status_code == 429:
        raise CricAPIError("Cricket API rate limit reached. Using cached fixture data.", status_code=429)
    elif response.status_code >= 500:
        raise CricAPIError("Cricket fixture service is temporarily unavailable. Using cached data.", status_code=response.status_code)
    elif response.status_code != 200:
        raise CricAPIError(f"Cricket API returned HTTP status {response.status_code}.", status_code=response.status_code)

    try:
        data = response.json()
    except Exception as e:
        raise CricAPIError("Cricket API returned an unexpected response format. Existing cache preserved.") from e

    if data.get("status") != "success":
        msg = data.get("reason") or data.get("message") or "Cricket API request was not successful."
        raise CricAPIError(f"Cricket API Error: {msg}", status_code=400)

    matches = data.get("data", [])
    if not isinstance(matches, list):
        return []

    return matches


def is_mens_international_match(match: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """
    Evaluates whether a CricAPI match is a Men's International ODI or T20I.
    Returns (is_valid, format_tag).
    """
    m_type = str(match.get("matchType", "")).lower().strip()
    name = str(match.get("name", "")).lower()
    status = str(match.get("status", "")).lower()
    series = (str(match.get("series_id", "")) + " " + name).lower()

    # Format check: Must be odi or t20/t20i
    if m_type == "odi":
        format_tag = "ODI"
    elif m_type in ["t20", "t20i"]:
        format_tag = "T20I"
    else:
        return False, None

    # Exclude Women's matches
    if any(w in name or w in series for w in ["women", "womens", "wodi", "wt20", "wbbl", "wpl"]):
        return False, None

    # Exclude completed, abandoned, or cancelled matches
    if match.get("matchEnded", False) is True:
        return False, None
    if any(s in status for s in ["completed", "result", "won by", "abandoned", "cancelled", "no result"]):
        return False, None

    # Exclude franchise, domestic, A teams, tour matches
    for kw in EXCLUDED_SERIES_KEYWORDS:
        if kw in name or kw in series:
            return False, None

    # Teams check: Must involve recognized men's international teams
    teams = match.get("teams", [])
    if not teams or len(teams) < 2:
        return False, None

    t1_lower = str(teams[0]).lower().strip()
    t2_lower = str(teams[1]).lower().strip()

    is_t1_intl = any(it == t1_lower or f" {it}" in f" {t1_lower}" for it in INTERNATIONAL_MENS_TEAMS)
    is_t2_intl = any(it == t2_lower or f" {it}" in f" {t2_lower}" for it in INTERNATIONAL_MENS_TEAMS)

    if not (is_t1_intl and is_t2_intl):
        return False, None

    return True, format_tag


def parse_and_filter_fixtures(
    raw_matches: List[Dict[str, Any]],
    db_path: Optional[Any] = None
) -> List[UpcomingFixture]:
    """Filters, deduplicates, sorts, and normalizes raw API matches into self-contained UpcomingFixture objects."""
    fixtures_dict: Dict[str, UpcomingFixture] = {}

    for m in raw_matches:
        match_id = str(m.get("id") or m.get("match_id", "")).strip()
        if not match_id:
            continue

        is_valid, fmt = is_mens_international_match(m)
        if not is_valid or not fmt:
            continue

        teams = m.get("teams", [])
        team1 = str(teams[0]).strip() if len(teams) > 0 else "Team 1"
        team2 = str(teams[1]).strip() if len(teams) > 1 else "Team 2"

        raw_venue = str(m.get("venue") or "Unknown Venue").strip()
        date_str = str(m.get("dateTimeGMT") or m.get("date") or "").strip()

        city = None
        if "," in raw_venue:
            parts = [p.strip() for p in raw_venue.split(",")]
            city = parts[1] if len(parts) > 1 else None

        resolved_v_id = resolve_fixture_venue(raw_venue, city=city, db_path=db_path)

        fixture = UpcomingFixture(
            match_id=match_id,
            team1=team1,
            team2=team2,
            format=fmt,
            venue=raw_venue,
            city=city,
            scheduled_datetime=date_str,
            status="upcoming",
            series=m.get("name"),
            resolved_venue_id=resolved_v_id,
            raw_data=m,
        )
        fixtures_dict[match_id] = fixture

    fixtures = list(fixtures_dict.values())

    def sort_key(f: UpcomingFixture):
        dt_str = f.scheduled_datetime
        try:
            return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        except Exception:
            return datetime.max.replace(tzinfo=timezone.utc)

    fixtures.sort(key=sort_key)
    return fixtures


def fetch_match_scorecard_from_api(api_key: str, match_id: str) -> Optional[Dict[str, Any]]:
    """Performs HTTP GET request to CricAPI /v1/match_info?id=..."""
    clean_key = api_key.strip() if api_key else ""
    if not clean_key or not match_id:
        return None

    url = "https://api.cricapi.com/v1/match_info"
    params = {"apikey": clean_key, "id": match_id}

    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "success":
                return data.get("data")
    except Exception:
        pass
    return None


def is_completed_mens_international_match(match: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """
    Evaluates whether a CricAPI match is a COMPLETED Men's International ODI or T20I.
    Returns (is_completed, format_tag).
    """
    m_type = str(match.get("matchType", "")).lower().strip()
    name = str(match.get("name", "")).lower()
    status = str(match.get("status", "")).lower()
    series = (str(match.get("series_id", "")) + " " + name).lower()

    # Format check: Must be odi or t20/t20i
    if m_type == "odi":
        format_tag = "ODI"
    elif m_type in ["t20", "t20i"]:
        format_tag = "T20I"
    else:
        return False, None

    # Exclude Women's matches
    if any(w in name or w in series for w in ["women", "womens", "wodi", "wt20", "wbbl", "wpl"]):
        return False, None

    # Exclude franchise, domestic, A teams, tour matches
    for kw in EXCLUDED_SERIES_KEYWORDS:
        if kw in name or kw in series:
            return False, None

    # Must be COMPLETED
    is_ended = match.get("matchEnded", False) is True
    is_completed_status = any(s in status for s in ["completed", "won by", "won", "result"]) and not any(s in status for s in ["abandoned", "cancelled", "no result"])

    if not (is_ended or is_completed_status):
        return False, None

    # Teams check: Must involve recognized men's international teams
    teams = match.get("teams", [])
    if not teams or len(teams) < 2:
        return False, None

    t1_lower = str(teams[0]).lower().strip()
    t2_lower = str(teams[1]).lower().strip()

    is_t1_intl = any(it == t1_lower or f" {it}" in f" {t1_lower}" for it in INTERNATIONAL_MENS_TEAMS)
    is_t2_intl = any(it == t2_lower or f" {it}" in f" {t2_lower}" for it in INTERNATIONAL_MENS_TEAMS)

    if not (is_t1_intl and is_t2_intl):
        return False, None

    return True, format_tag

