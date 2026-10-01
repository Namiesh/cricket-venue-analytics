"""
CLI Script: Update Completed Matches.
Fetches newly completed Men's International ODI & T20I matches from Cricket Data API
and ingests them into the local SQLite database data/processed/cricket_venue.db.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.fixtures.ingestion import ingest_completed_matches


def main():
    print("Starting completed match ingestion...")
    result = ingest_completed_matches()
    print(f"Status: {result['status']}")
    print(f"Imported matches: {result['imported_count']}")
    print(f"API calls made: {result['api_calls_made']}")
    print(f"Message: {result['message']}")


if __name__ == "__main__":
    main()
