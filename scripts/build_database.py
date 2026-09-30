"""
Database Build Script for Cricket Venue Analytics.
Reads raw Cricsheet JSON files one by one, normalizes venues, parses match/innings records,
and writes to SQLite database data/processed/cricket_venue.db.
"""

import json
import logging
import sys
from pathlib import Path
from typing import Dict, Any, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ingestion.parser import parse_cricsheet_json
from src.processing.venue_normalizer import get_canonical_venue_info
from src.database.db_manager import DatabaseManager

RAW_DIR = PROJECT_ROOT / "data" / "raw"
ODI_DIR = RAW_DIR / "odi"
T20I_DIR = RAW_DIR / "t20i"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
DB_PATH = PROCESSED_DIR / "cricket_venue.db"
ERROR_LOG_PATH = PROCESSED_DIR / "ingestion_errors.log"


def setup_error_logger() -> logging.Logger:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("ingestion_error_logger")
    logger.setLevel(logging.ERROR)
    logger.handlers.clear()
    fh = logging.FileHandler(ERROR_LOG_PATH, mode="w", encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    return logger


def build_database():
    error_logger = setup_error_logger()
    db_mgr = DatabaseManager(DB_PATH)

    print("Initializing SQLite Database and creating tables...")
    db_mgr.create_tables()

    odi_files = sorted(list(ODI_DIR.glob("*.json"))) if ODI_DIR.exists() else []
    t20i_files = sorted(list(T20I_DIR.glob("*.json"))) if T20I_DIR.exists() else []

    print(f"Found {len(odi_files)} ODI files and {len(t20i_files)} T20I files.")

    # Venue accumulator: venue_id -> {canonical_name, city, country, raw_names: set(), odi_count: int, t20i_count: int}
    venue_accumulator: Dict[str, Dict[str, Any]] = {}

    batch_size = 200
    parsing_error_count = 0

    def process_file_list(files: List[Path], format_tag: str):
        nonlocal parsing_error_count
        matches_batch: List[Dict[str, Any]] = []
        innings_batch: List[Dict[str, Any]] = []

        total_files = len(files)
        print(f"\nProcessing {format_tag}:")

        for idx, file_path in enumerate(files, start=1):
            try:
                res = parse_cricsheet_json(file_path, format_tag)
                if res is None:
                    continue

                match_rec, innings_recs = res

                # Venue aggregation
                raw_v = match_rec["venue_raw"]
                v_id, c_name, c_city, c_country = get_canonical_venue_info(raw_v, match_rec["city"])
                match_rec["venue_id"] = v_id

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

                if match_rec["format"] == "ODI":
                    venue_accumulator[v_id]["match_count_odi"] += 1
                else:
                    venue_accumulator[v_id]["match_count_t20i"] += 1

                matches_batch.append(match_rec)
                innings_batch.extend(innings_recs)

            except Exception as e:
                parsing_error_count += 1
                error_msg = f"Filename: {file_path.name} | ErrorType: {type(e).__name__} | Error: {str(e)}"
                error_logger.error(error_msg)

            # Flush batch
            if len(matches_batch) >= batch_size or idx == total_files:
                db_mgr.insert_matches_batch(matches_batch)
                db_mgr.insert_innings_batch(innings_batch)
                matches_batch.clear()
                innings_batch.clear()

            # Progress printing
            if idx % 500 == 0 or idx == total_files:
                print(f"{idx} / {total_files}")

    process_file_list(odi_files, "ODI")
    process_file_list(t20i_files, "T20I")

    # Insert accumulated venue records
    print("\nInserting normalized venues into database...")
    venue_records = []
    for v_id, v_data in venue_accumulator.items():
        venue_records.append({
            "venue_id": v_id,
            "canonical_name": v_data["canonical_name"],
            "city": v_data["city"],
            "country": v_data["country"],
            "raw_name_examples": json.dumps(sorted(list(v_data["raw_names"]))),
            "match_count_odi": v_data["match_count_odi"],
            "match_count_t20i": v_data["match_count_t20i"],
        })

    db_mgr.insert_venues_batch(venue_records)
    print(f"Database build complete. Total parsing errors: {parsing_error_count}")


if __name__ == "__main__":
    build_database()
