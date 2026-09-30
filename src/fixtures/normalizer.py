"""
Fixture Venue Normalizer Module.
Resolves CricAPI / external venue strings to historical database venue_ids.
"""

import json
import sqlite3
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.processing.venue_normalizer import normalize_venue, get_canonical_venue_info
from src.database.db_manager import DatabaseManager

DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "processed" / "cricket_venue.db"


def get_db_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    target_path = db_path or DEFAULT_DB_PATH
    conn = sqlite3.connect(target_path)
    conn.row_factory = sqlite3.Row
    return conn


def resolve_fixture_venue(
    raw_venue: Optional[str],
    city: Optional[str] = None,
    db_path: Optional[Path] = None
) -> Optional[str]:
    """
    Resolves an external fixture venue string to a valid venue_id in the database.
    Returns venue_id if safely resolved, otherwise None.

    Priority:
    1. Exact canonical_name match in DB venues table
    2. Exact raw_name / raw_name_examples match in DB venues table
    3. Deterministic alias in venue_normalizer matching DB venue_id
    4. Base venue_id + city matching DB venue_id
    5. Unresolved (None)
    """
    if not raw_venue or not raw_venue.strip():
        return None

    cleaned_venue = raw_venue.strip()

    if "," in cleaned_venue and not city:
        parts = [p.strip() for p in cleaned_venue.split(",")]
        base_v = parts[0]
        extracted_city = parts[1] if len(parts) > 1 else None
    else:
        base_v = cleaned_venue
        extracted_city = city

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()

        # Priority 1: Exact canonical_name match
        cursor.execute("SELECT venue_id FROM venues WHERE LOWER(canonical_name) = LOWER(?);", (cleaned_venue,))
        row = cursor.fetchone()
        if row:
            return row["venue_id"]

        if base_v != cleaned_venue:
            cursor.execute("SELECT venue_id FROM venues WHERE LOWER(canonical_name) = LOWER(?);", (base_v,))
            row = cursor.fetchone()
            if row:
                return row["venue_id"]

        # Priority 2: Exact raw_name / raw_name_examples match
        cursor.execute("SELECT venue_id, raw_name_examples FROM venues;")
        all_venues = cursor.fetchall()

        cleaned_lower = cleaned_venue.lower()
        base_lower = base_v.lower()

        for v in all_venues:
            v_id = v["venue_id"]
            raw_ex = v["raw_name_examples"]
            if raw_ex:
                try:
                    ex_list = [ex.lower() for ex in json.loads(raw_ex)]
                    if cleaned_lower in ex_list or base_lower in ex_list:
                        return v_id
                except Exception:
                    pass

        # Priority 3: Existing deterministic alias mapping from venue_normalizer
        norm_id = normalize_venue(cleaned_venue, extracted_city)
        cursor.execute("SELECT venue_id FROM venues WHERE venue_id = ?;", (norm_id,))
        row = cursor.fetchone()
        if row:
            return row["venue_id"]

        if base_v != cleaned_venue:
            norm_id_base = normalize_venue(base_v, extracted_city)
            cursor.execute("SELECT venue_id FROM venues WHERE venue_id = ?;", (norm_id_base,))
            row = cursor.fetchone()
            if row:
                return row["venue_id"]

        # Priority 4: Partial substring match in canonical_name
        cursor.execute("SELECT venue_id FROM venues WHERE LOWER(canonical_name) LIKE ?;", (f"%{base_lower}%",))
        rows = cursor.fetchall()
        if len(rows) == 1:
            return rows[0]["venue_id"]

    # Priority 5: Unresolved
    return None
