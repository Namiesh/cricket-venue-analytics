"""
Data Inspection Script for Cricsheet ODI & T20I Dataset.
Performs lightweight inspection and schema analysis without loading full dataset into memory.
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Set

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
ODI_DIR = RAW_DIR / "odi"
T20I_DIR = RAW_DIR / "t20i"


def get_json_files(folder: Path) -> List[Path]:
    if not folder.exists():
        return []
    return list(folder.glob("*.json"))


def inspect_dataset():
    print("=" * 60)
    print(" CRICSHEET DATASET INSPECTION ")
    print("=" * 60)

    odi_files = get_json_files(ODI_DIR)
    t20i_files = get_json_files(T20I_DIR)

    print(f"\n[1] FILE COUNTS:")
    print(f"  - ODI JSON files count : {len(odi_files)}")
    print(f"  - T20I JSON files count: {len(t20i_files)}")
    print(f"  - Total JSON files     : {len(odi_files) + len(t20i_files)}")

    all_files = [(f, "ODI") for f in odi_files] + [(f, "T20I") for f in t20i_files]

    if not all_files:
        print("\n[!] No JSON files found in data/raw/odi or data/raw/t20i.")
        return

    venues: Set[str] = set()
    genders: Set[str] = set()
    match_types: Set[str] = set()
    team_types: Set[str] = set()
    outcome_types: Set[str] = set()
    sample_match_data = None
    sample_file_path = None

    gender_counts: Dict[str, int] = {}

    # Stream across files efficiently to inspect metadata and find all genders present
    for file_path, category in all_files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if sample_match_data is None:
                sample_match_data = data
                sample_file_path = file_path

            info = data.get("info", {})
            venue = info.get("venue")
            if venue:
                venues.add(venue)

            gender = info.get("gender", "unknown")
            genders.add(gender)
            gender_counts[gender] = gender_counts.get(gender, 0) + 1

            m_type = info.get("match_type")
            if m_type:
                match_types.add(m_type)

            t_type = info.get("team_type")
            if t_type:
                team_types.add(t_type)

            outcome = info.get("outcome", {})
            if "winner" in outcome:
                outcome_types.add("winner")
            if "result" in outcome:
                outcome_types.add(f"result:{outcome['result']}")
            if "method" in outcome:
                outcome_types.add(f"method:{outcome['method']}")

        except Exception as e:
            print(f"Error reading {file_path.name}: {e}")

    print(f"\n[2] FORMAT & GENDER FIELDS IDENTIFIED (across all {len(all_files)} files):")
    print(f"  - Match Types found : {sorted(list(match_types))}")
    print(f"  - Team Types found  : {sorted(list(team_types))}")
    print(f"  - Genders found     : {sorted(list(genders))}")
    print(f"  - Gender Counts     : {gender_counts}")
    print(f"  - Men & Women present: {'Yes (Both male and female matches present)' if 'male' in genders and 'female' in genders else 'Only ' + ', '.join(genders)}")

    print(f"\n[3] SAMPLE VENUES (Discovered {len(venues)} unique venues in total, showing 5 samples):")
    for v in sorted(list(venues))[:5]:
        print(f"  - {v}")

    print(f"\n[4] OUTCOME INFORMATION STRUCTURES FOUND:")
    print(f"  - Outcome Attributes: {sorted(list(outcome_types))}")

    if sample_match_data:
        info = sample_match_data.get("info", {})
        print(f"\n[5] SAMPLE MATCH METADATA (File: {sample_file_path.name}):")
        print(f"  - Teams       : {info.get('teams')}")
        print(f"  - Format      : {info.get('match_type')}")
        print(f"  - Gender      : {info.get('gender')}")
        print(f"  - Dates       : {info.get('dates')}")
        print(f"  - Venue       : {info.get('venue')}")
        print(f"  - City        : {info.get('city')}")
        print(f"  - Event       : {info.get('event')}")
        print(f"  - Toss        : {info.get('toss')}")
        print(f"  - Outcome     : {info.get('outcome')}")
        print(f"  - Season      : {info.get('season')}")
        print(f"  - Player of Match: {info.get('player_of_match')}")

        print(f"\n[6] TOP-LEVEL JSON KEYS:")
        print(f"  - {list(sample_match_data.keys())}")

        print(f"\n[7] INNINGS & DELIVERIES STRUCTURE SAMPLE:")
        innings = sample_match_data.get("innings", [])
        print(f"  - Total Innings: {len(innings)}")
        if len(innings) > 0:
            first_inn = innings[0]
            print(f"  - Innings 1 Team: {first_inn.get('team')}")
            overs = first_inn.get("overs", [])
            print(f"  - Total Overs in Innings 1: {len(overs)}")
            if len(overs) > 0:
                first_over = overs[0]
                print(f"  - Over Number: {first_over.get('over')}")
                deliveries = first_over.get("deliveries", [])
                print(f"  - Deliveries in Over 0: {len(deliveries)}")
                if len(deliveries) > 0:
                    print(f"  - Delivery 0.1 Sample Keys: {list(deliveries[0].keys())}")
                    print(f"  - Delivery 0.1 Details    : {deliveries[0]}")

    print("\n" + "=" * 60)
    print(" INSPECTION COMPLETE ")
    print("=" * 60)


if __name__ == "__main__":
    inspect_dataset()
