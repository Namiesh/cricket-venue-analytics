"""
Analytics Package Entrypoint.
Exposes venue statistics, score range analysis, and team head-to-head analytics.
"""

from src.analytics.venue_stats import (
    get_recent_matches,
    calculate_venue_summary,
    search_venues,
    get_venue_by_name,
    get_venues_for_format,
)
from src.analytics.score_analysis import (
    analyze_score_ranges,
    analyze_first_innings_score_outcomes,
    ODI_BANDS,
    T20I_BANDS,
)
from src.analytics.team_stats import (
    get_team_venue_stats,
    get_head_to_head_stats,
    analyze_match_context,
    get_teams_for_venue_format,
)

__all__ = [
    "get_recent_matches",
    "calculate_venue_summary",
    "search_venues",
    "get_venue_by_name",
    "get_venues_for_format",
    "analyze_score_ranges",
    "analyze_first_innings_score_outcomes",
    "ODI_BANDS",
    "T20I_BANDS",
    "get_team_venue_stats",
    "get_head_to_head_stats",
    "analyze_match_context",
    "get_teams_for_venue_format",
]
