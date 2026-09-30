"""
Demo / Validation Script for Venue Analytics Engine.
Demonstrates recent match venue statistics and score range analysis on active database venues.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analytics.venue_stats import (
    search_venues,
    calculate_venue_summary,
)
from src.analytics.score_analysis import analyze_score_ranges
from src.analytics.team_stats import (
    get_team_venue_stats,
    get_head_to_head_stats,
    analyze_match_context,
)


def run_demo():
    print("=" * 65)
    print(" CRICKET VENUE ANALYTICS ENGINE DEMO ")
    print("=" * 65)

    # 1. Search venue
    venues = search_venues("Wankhede")
    if not venues:
        venues = search_venues("Adelaide")
    if not venues:
        venues = search_venues("Lord")

    if not venues:
        print("[!] No venues found in database.")
        return

    target_venue = venues[0]
    venue_id = target_venue["venue_id"]
    canonical_name = target_venue["canonical_name"]

    print(f"\nTarget Venue Discovered: {canonical_name} (ID: {venue_id})")
    print(f"Total Matches: ODI={target_venue['match_count_odi']}, T20I={target_venue['match_count_t20i']}")

    for fmt in ["ODI", "T20I"]:
        print("\n" + "-" * 65)
        print(f" VENUE SUMMARY: {canonical_name} [{fmt}] - LAST 10 MATCHES ")
        print("-" * 65)

        summary = calculate_venue_summary(venue_id, fmt, n=10)

        print(f"VENUE        : {summary['canonical_name']}")
        print(f"FORMAT       : {summary['format']}")
        print(f"MATCHES USED : {summary['actual_match_count']} / {summary['requested_match_count']}")
        print(f"DATE RANGE   : {summary['date_range']}")

        f_inn = summary["first_innings"]
        s_inn = summary["second_innings"]

        print(f"\n1st Innings Scores -> Avg: {f_inn['average']} | Med: {f_inn['median']} | Max: {f_inn['highest']} | Min: {f_inn['lowest']}")
        print(f"2nd Innings Scores -> Avg: {s_inn['average']} | Med: {s_inn['median']} | Max: {s_inn['highest']} | Min: {s_inn['lowest']}")

        print(f"\nBatting First Wins : {summary['batting_first_wins']} ({summary['batting_first_win_percentage']}%)")
        print(f"Chasing Wins       : {summary['chasing_wins']} ({summary['chasing_win_percentage']}%)")
        print(f"Ties               : {summary['ties']}")
        print(f"No Results in Sample: {summary['no_results']}")

        print(f"\nSCORE RANGE ANALYSIS [{fmt}]:")
        scores_res = analyze_score_ranges(venue_id, fmt, n=10)
        for band_name, b_info in scores_res["score_bands"].items():
            cnt = b_info["number_of_matches"]
            bf_w = b_info["batting_first_wins"]
            pct = f"{b_info['batting_first_win_percentage']}%" if b_info['batting_first_win_percentage'] is not None else "N/A"
            print(f"  Band {band_name:8s} : {cnt} matches | Batting 1st Wins: {bf_w} | Batting 1st Win %: {pct}")

    # Team stats & Head-to-Head demonstration
    print("\n" + "-" * 65)
    print(f" TEAM & HEAD-TO-HEAD ANALYSIS DEMO ")
    print("-" * 65)

    team1, team2 = "India", "Australia"
    fmt = "ODI"
    t_stats = get_team_venue_stats(team1, venue_id, fmt)
    h2h = get_head_to_head_stats(team1, team2, venue_id, fmt)

    print(f"\n{team1} at {canonical_name} ({fmt}):")
    print(f"  Played: {t_stats['matches_played']} | Wins: {t_stats['wins']} | Losses: {t_stats['losses']}")
    print(f"  Avg Score: {t_stats['average_score']} | Highest: {t_stats['highest_score']} | Lowest: {t_stats['lowest_score']}")

    print(f"\nHead-to-Head ({team1} vs {team2}) at {canonical_name} ({fmt}):")
    print(f"  Total Matches: {h2h['matches']}")
    print(f"  {team1} Wins: {h2h['team1_wins']} | {team2} Wins: {h2h['team2_wins']}")

    # Full context demonstration
    ctx = analyze_match_context(team1, team2, venue_id, fmt, recent_matches=10)
    print(f"\nUpcoming Match Context Object Generated: Status = '{ctx['status_message']}'")
    print("=" * 65)


if __name__ == "__main__":
    run_demo()
