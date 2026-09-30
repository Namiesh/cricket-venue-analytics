"""
Audit Venue Aliases Script.
Scans SQLite database cricket_venue.db and reports venue normalization metrics.
"""

import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.processing.venue_normalizer import get_canonical_venue_info, VenueRegistry, DEFAULT_REGISTRY_PATH
from src.database.db_manager import DatabaseManager

DB_PATH = PROJECT_ROOT / "data" / "processed" / "cricket_venue.db"


def audit_venue_aliases():
    if not DB_PATH.exists():
        print(f"Error: Database not found at {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT DISTINCT venue_raw, city FROM matches WHERE venue_raw IS NOT NULL AND venue_raw != '' ORDER BY venue_raw")
    raw_venue_records = cursor.fetchall()
    conn.close()

    total_raw_venue_names = len(raw_venue_records)

    registry = VenueRegistry(DEFAULT_REGISTRY_PATH)

    canonical_venues_set = set()
    mapped_aliases_count = 0
    unresolved_venues_count = 0

    mappings_list = []

    for raw_name, city in raw_venue_records:
        v_id, c_name, c_city, c_country = registry.get_canonical_info(raw_name, city)
        canonical_venues_set.add(v_id)

        cleaned_raw = raw_name.strip().lower()
        if cleaned_raw in registry.alias_map or ("," in raw_name and raw_name.split(",")[0].strip().lower() in registry.alias_map):
            mapped_aliases_count += 1
            is_mapped = True
        else:
            unresolved_venues_count += 1
            is_mapped = False

        mappings_list.append({
            "raw_name": raw_name,
            "canonical_id": v_id,
            "canonical_name": c_name,
            "is_mapped": is_mapped
        })

    print("==================================================")
    print("VENUE NORMALIZATION AUDIT REPORT")
    print("==================================================")
    print(f"Total raw venue names: {total_raw_venue_names}")
    print(f"Canonical venues: {len(canonical_venues_set)}")
    print(f"Mapped aliases: {mapped_aliases_count}")
    print(f"Unresolved venue names: {unresolved_venues_count}")
    print("==================================================\n")

    print(f"{'RAW NAME':<45} | {'CANONICAL VENUE DISPLAY NAME':<40} | {'CANONICAL ID'}")
    print("-" * 110)
    for m in mappings_list[:50]:  # Display sample
        print(f"{m['raw_name']:<45} | {m['canonical_name']:<40} | {m['canonical_id']}")

    print("\nAudit completed successfully.")


if __name__ == "__main__":
    audit_venue_aliases()
