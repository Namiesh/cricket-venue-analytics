"""
Validation & Debugging Script for Upcoming Fixtures.
Inspects cached upcoming fixtures, validates venue resolution, and formats UTC -> IST timestamps.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.fixtures import get_upcoming_fixtures, resolve_fixture_venue


def validate_fixtures():
    print("=" * 70)
    print(" UPCOMING FIXTURES VALIDATION & INSPECTION ")
    print("=" * 70)

    # Use cached fixtures (force_refresh=False to avoid unnecessary API hits)
    fixtures, meta = get_upcoming_fixtures(force_refresh=False)

    print(f"\nCache Meta: Status='{meta['status']}' | API Called={meta['api_called']} | Message='{meta['message']}'")
    print(f"Total Fixtures Returned: {len(fixtures)}")

    if not fixtures:
        print("[!] No fixtures found in cache.")
        return

    odi_count = sum(1 for f in fixtures if f.format == "ODI")
    t20i_count = sum(1 for f in fixtures if f.format == "T20I")

    print(f"Format Breakdown -> ODI: {odi_count} | T20I: {t20i_count}")

    print("\n" + "-" * 70)
    print(" UPCOMING FIXTURES DETAIL (IST FORMATTED) ")
    print("-" * 70)

    for idx, f in enumerate(fixtures[:10], start=1):
        v_resolved = f.resolved_venue_id or resolve_fixture_venue(f.venue, city=f.city)

        print(f"\n[{idx}] {f.team1} vs {f.team2}")
        print(f"    Match ID   : {f.match_id}")
        print(f"    Format     : {f.format}")
        print(f"    Venue (API): {f.venue}")
        print(f"    Venue (ID) : {v_resolved or 'UNRESOLVED (None)'}")
        print(f"    City       : {f.city or 'N/A'}")
        print(f"    UTC Time   : {f.scheduled_datetime}")
        print(f"    IST Time   : {f.formatted_ist_datetime()}")
        print(f"    Series     : {f.series or 'N/A'}")
        print(f"    Status     : {f.status}")

        if "wankhede" in f.venue.lower() and "south africa" in f.team1.lower() and f.format == "T20I":
            print("    [!] ERROR: Suspicious dummy record detected for South Africa vs Australia T20I at Wankhede.")

        if not v_resolved:
            print(f"    [!] WARNING: Unresolved historical venue mapping for '{f.venue}'.")

    print("\n" + "=" * 70)
    print(" VALIDATION COMPLETE ")
    print("=" * 70)


if __name__ == "__main__":
    validate_fixtures()
