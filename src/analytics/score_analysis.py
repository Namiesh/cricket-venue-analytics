"""
Score Range Analysis Analytics Module.
Analyzes historical match outcomes grouped by first-innings score bands.
"""

import sys
from pathlib import Path
from typing import Dict, Any, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analytics.venue_stats import get_recent_matches

# Configurable score bands for ODI and T20I
ODI_BANDS: List[Dict[str, Any]] = [
    {"name": "< 200", "min": 0, "max": 199},
    {"name": "200-249", "min": 200, "max": 249},
    {"name": "250-299", "min": 250, "max": 299},
    {"name": "300-349", "min": 300, "max": 349},
    {"name": "350-399", "min": 350, "max": 399},
    {"name": "400+", "min": 400, "max": 9999},
]

T20I_BANDS: List[Dict[str, Any]] = [
    {"name": "< 120", "min": 0, "max": 119},
    {"name": "120-149", "min": 120, "max": 149},
    {"name": "150-179", "min": 150, "max": 179},
    {"name": "180-199", "min": 180, "max": 199},
    {"name": "200-219", "min": 200, "max": 219},
    {"name": "220+", "min": 220, "max": 9999},
]


def get_score_bands_for_format(format: str, custom_bands: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    if custom_bands:
        return custom_bands
    fmt = format.upper()
    if fmt == "ODI":
        return ODI_BANDS
    elif fmt == "T20I":
        return T20I_BANDS
    else:
        raise ValueError(f"Unsupported format '{format}'. Must be 'ODI' or 'T20I'.")


def analyze_score_ranges(
    venue_id: str,
    format: str,
    n: int = 10,
    custom_bands: Optional[List[Dict[str, Any]]] = None,
    db_path: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Groups recent qualifying matches at venue by 1st innings score bands and computes win rates.
    """
    matches, meta = get_recent_matches(venue_id, format, n=n, db_path=db_path)
    bands = get_score_bands_for_format(format, custom_bands)

    # Initialize band stats
    band_results: Dict[str, Dict[str, Any]] = {}
    for b in bands:
        name = b["name"]
        band_results[name] = {
            "score_range": name,
            "min_score": b["min"],
            "max_score": b["max"],
            "number_of_matches": 0,
            "batting_first_wins": 0,
            "chasing_wins": 0,
            "ties": 0,
            "batting_first_win_percentage": None,
        }

    for m in matches:
        inn1 = m.get("innings1")
        if not inn1:
            continue
        score = inn1["total_runs"]

        # Find matching band
        target_band_name = None
        for b in bands:
            if b["min"] <= score <= b["max"]:
                target_band_name = b["name"]
                break

        if not target_band_name:
            continue

        res = band_results[target_band_name]
        res["number_of_matches"] += 1

        if m["batting_first_won"]:
            res["batting_first_wins"] += 1
        elif m["chasing_won"]:
            res["chasing_wins"] += 1
        elif m["is_tie"]:
            res["ties"] += 1

    # Compute percentages
    for name, res in band_results.items():
        total_decided = res["batting_first_wins"] + res["chasing_wins"] + res["ties"]
        if total_decided > 0:
            res["batting_first_win_percentage"] = round((res["batting_first_wins"] / total_decided) * 100.0, 1)

    return {
        "venue_id": venue_id,
        "format": format.upper(),
        "sample_match_count": len(matches),
        "score_bands": band_results,
    }


def analyze_first_innings_score_outcomes(
    venue_id: str,
    format: str,
    n: int = 10,
    custom_bands: Optional[List[Dict[str, Any]]] = None,
    db_path: Optional[Path] = None
) -> Dict[str, Any]:
    """Alias/structured interface for first innings score band outcomes analysis."""
    res = analyze_score_ranges(venue_id, format, n=n, custom_bands=custom_bands, db_path=db_path)
    return res["score_bands"]
