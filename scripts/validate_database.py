"""
Database Validation Script for Cricket Venue Analytics.
Verifies integrity, format separation, venue normalization, and data quality across 17 checkpoints.
"""

import sqlite3
import sys
from pathlib import Path
from typing import Dict, Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DB_PATH = PROJECT_ROOT / "data" / "processed" / "cricket_venue.db"
LOG_PATH = PROJECT_ROOT / "data" / "processed" / "ingestion_errors.log"


def validate_database() -> Dict[str, Any]:
    if not DB_PATH.exists():
        print(f"[!] Database file does not exist at {DB_PATH}")
        return {}

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("=" * 60)
    print(" DATABASE VALIDATION REPORT ")
    print("=" * 60)

    # 1. Matches by format
    cursor.execute("SELECT format, COUNT(*) FROM matches GROUP BY format;")
    matches_by_format = dict(cursor.fetchall())
    print(f"\n1. Matches by Format: {matches_by_format}")

    # 2. Matches by gender
    cursor.execute("SELECT gender, COUNT(*) FROM matches GROUP BY gender;")
    matches_by_gender = dict(cursor.fetchall())
    print(f"2. Matches by Gender: {matches_by_gender}")

    # 3. Matches by team_type
    cursor.execute("SELECT team_type, COUNT(*) FROM matches GROUP BY team_type;")
    matches_by_team_type = dict(cursor.fetchall())
    print(f"3. Matches by Team Type: {matches_by_team_type}")

    # 4. Number of unique normalized venues
    cursor.execute("SELECT COUNT(*) FROM venues;")
    unique_venues_count = cursor.fetchone()[0]
    print(f"4. Unique Normalized Venues Count: {unique_venues_count}")

    # 5. Total & avg innings per match
    cursor.execute("SELECT COUNT(*) FROM innings;")
    total_innings = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM matches;")
    total_matches = cursor.fetchone()[0]
    avg_innings = (total_innings / total_matches) if total_matches > 0 else 0
    print(f"5. Total Innings: {total_innings} (Avg per match: {avg_innings:.2f})")

    # 6. Matches with missing venue
    cursor.execute("SELECT COUNT(*) FROM matches WHERE venue_raw IS NULL OR venue_id IS NULL;")
    missing_venue_count = cursor.fetchone()[0]
    print(f"6. Matches with Missing Venue: {missing_venue_count}")

    # 7. Matches with missing winner
    cursor.execute("SELECT COUNT(*) FROM matches WHERE winner IS NULL;")
    missing_winner_count = cursor.fetchone()[0]
    print(f"7. Matches with Missing Winner: {missing_winner_count}")

    # 8. No-result matches
    cursor.execute("SELECT COUNT(*) FROM matches WHERE result_type = 'no result';")
    no_result_count = cursor.fetchone()[0]
    print(f"8. No-Result Matches Count: {no_result_count}")

    # 9. Tie matches
    cursor.execute("SELECT COUNT(*) FROM matches WHERE result_type = 'tie';")
    tie_count = cursor.fetchone()[0]
    print(f"9. Tie Matches Count: {tie_count}")

    # 10. D/L matches
    cursor.execute("SELECT COUNT(*) FROM matches WHERE method IN ('D/L', 'DLS');")
    dl_count = cursor.fetchone()[0]
    print(f"10. D/L or DLS Matches Count: {dl_count}")

    # 11. Matches with unusual innings counts (<1 or >2)
    cursor.execute("""
        SELECT match_id, COUNT(innings_id) as inn_cnt 
        FROM innings 
        GROUP BY match_id 
        HAVING inn_cnt < 1 OR inn_cnt > 2;
    """)
    unusual_innings_matches = cursor.fetchall()
    print(f"11. Matches with Unusual Innings Counts (<1 or >2): {len(unusual_innings_matches)}")

    # 12. Innings with zero runs
    cursor.execute("SELECT COUNT(*) FROM innings WHERE total_runs = 0;")
    zero_runs_innings_count = cursor.fetchone()[0]
    print(f"12. Innings with Zero Runs: {zero_runs_innings_count}")

    # 13. Parsing errors count
    error_count = 0
    if LOG_PATH.exists():
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            error_count = len([line for line in f if line.strip()])
    print(f"13. Parsing Errors Recorded in Log: {error_count}")

    # 14. Duplicate match IDs
    cursor.execute("SELECT match_id, COUNT(*) FROM matches GROUP BY match_id HAVING COUNT(*) > 1;")
    duplicate_match_ids = cursor.fetchall()
    print(f"14. Duplicate Match IDs: {len(duplicate_match_ids)}")

    # 15. Every innings references an existing match
    cursor.execute("""
        SELECT COUNT(*) FROM innings 
        WHERE match_id NOT IN (SELECT match_id FROM matches);
    """)
    orphaned_innings = cursor.fetchone()[0]
    print(f"15. Orphaned Innings (Orphan count): {orphaned_innings}")

    # 16. Every match has at least one innings
    cursor.execute("""
        SELECT COUNT(*) FROM matches 
        WHERE match_id NOT IN (SELECT DISTINCT match_id FROM innings);
    """)
    matches_without_innings = cursor.fetchone()[0]
    print(f"16. Matches Without Innings: {matches_without_innings}")

    # 17. Format separation check
    cursor.execute("SELECT DISTINCT format FROM matches;")
    formats = [r[0] for r in cursor.fetchall()]
    print(f"17. Formats Discovered: {formats} (ODI and T20I strictly separated: {set(formats).issubset({'ODI', 'T20I'})})")

    # DB Size
    db_size_mb = DB_PATH.stat().st_size / (1024 * 1024)
    print(f"\nDatabase File Size: {db_size_mb:.2f} MB")

    print("\n" + "=" * 60)
    print(" VALIDATION COMPLETE ")
    print("=" * 60)

    conn.close()

    return {
        "odi_count": matches_by_format.get("ODI", 0),
        "t20i_count": matches_by_format.get("T20I", 0),
        "total_matches": total_matches,
        "total_innings": total_innings,
        "venues_count": unique_venues_count,
        "parsing_errors": error_count,
        "no_result_count": no_result_count,
        "tie_count": tie_count,
        "dl_count": dl_count,
        "db_size_mb": db_size_mb,
    }


if __name__ == "__main__":
    validate_database()
