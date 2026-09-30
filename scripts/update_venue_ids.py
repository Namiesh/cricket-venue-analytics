"""
Update Database Venue IDs Script.
Re-calculates canonical venue IDs for all matches in cricket_venue.db and updates the matches and venues tables.
Preserves raw venue strings (venue_raw) for historical auditability.
"""

import sqlite3
import sys
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.processing.venue_normalizer import get_canonical_venue_info, reload_registry
from src.database.db_manager import DatabaseManager

DB_PATH = PROJECT_ROOT / "data" / "processed" / "cricket_venue.db"


def update_database_venues():
    if not DB_PATH.exists():
        print(f"Error: Database not found at {DB_PATH}")
        sys.exit(1)

    reload_registry()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT match_id, venue_raw, city, format FROM matches")
    matches = cursor.fetchall()
    print(f"Updating venue_id for {len(matches)} historical matches...")

    # Venue accumulator: venue_id -> {canonical_name, city, country, raw_names: set(), odi_count: int, t20i_count: int}
    venue_accumulator = {}

    update_batch = []
    for m in matches:
        match_id = m["match_id"]
        raw_v = m["venue_raw"]
        city = m["city"]
        fmt = m["format"]

        v_id, c_name, c_city, c_country = get_canonical_venue_info(raw_v, city)
        update_batch.append((v_id, match_id))

        if v_id not in venue_accumulator:
            venue_accumulator[v_id] = {
                "venue_id": v_id,
                "canonical_name": c_name,
                "city": c_city,
                "country": c_country,
                "raw_names": set(),
                "match_count_odi": 0,
                "match_count_t20i": 0,
            }

        if raw_v:
            venue_accumulator[v_id]["raw_names"].add(raw_v)

        if fmt == "ODI":
            venue_accumulator[v_id]["match_count_odi"] += 1
        else:
            venue_accumulator[v_id]["match_count_t20i"] += 1

    cursor.executemany("UPDATE matches SET venue_id = ? WHERE match_id = ?", update_batch)
    conn.commit()
    print(f"Successfully updated venue_id for {len(update_batch)} matches.")

    # Rebuild venues table
    print("Rebuilding venues table with canonical venues...")
    cursor.execute("DELETE FROM venues;")

    venue_records = []
    for v_id, v_data in venue_accumulator.items():
        venue_records.append((
            v_id,
            v_data["canonical_name"],
            v_data["city"],
            v_data["country"],
            json.dumps(sorted(list(v_data["raw_names"]))),
            v_data["match_count_odi"],
            v_data["match_count_t20i"]
        ))

    cursor.executemany("""
        INSERT INTO venues (
            venue_id, canonical_name, city, country, raw_name_examples, match_count_odi, match_count_t20i
        ) VALUES (?, ?, ?, ?, ?, ?, ?);
    """, venue_records)

    conn.commit()
    conn.close()

    print(f"Successfully updated venues table. Total canonical venues: {len(venue_records)}.")


if __name__ == "__main__":
    update_database_venues()
