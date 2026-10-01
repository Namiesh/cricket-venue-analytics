"""
Unit Tests for Incremental Completed Match Ingestion and Analytics Integration.
Validates idempotency, venue canonical resolution, combined innings averages, and analytics inclusion.
"""

import unittest
import sqlite3
import tempfile
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database.db_manager import DatabaseManager
from src.fixtures.ingestion import ingest_completed_matches
from src.analytics.venue_stats import calculate_venue_summary, get_recent_matches
from src.analytics.team_stats import get_team_venue_analysis


class TestCompletedMatchIngestion(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.test_dir = PROJECT_ROOT / "scratch_test_ingestion"
        cls.test_dir.mkdir(exist_ok=True)
        cls.test_db_path = cls.test_dir / "test_cricket_venue_ingestion.db"

        # Create schema
        db_mgr = DatabaseManager(cls.test_db_path)
        db_mgr.create_tables()

        # Seed initial historical matches
        venues = [{
            "venue_id": "wankhede_stadium_mumbai",
            "canonical_name": "Wankhede Stadium, Mumbai",
            "city": "Mumbai",
            "country": "India",
            "raw_name_examples": '["Wankhede Stadium"]',
            "match_count_odi": 2,
            "match_count_t20i": 0
        }]
        db_mgr.insert_venues_batch(venues)

        matches = [
            {
                "match_id": "hist_1", "date": "2025-01-01", "format": "ODI", "gender": "male",
                "team_type": "international", "venue_raw": "Wankhede Stadium", "venue_id": "wankhede_stadium_mumbai",
                "city": "Mumbai", "season": "2025", "team1": "India", "team2": "Australia", "toss_winner": "India",
                "toss_decision": "bat", "winner": "India", "result_type": "normal", "win_margin": 10,
                "win_margin_type": "runs", "method": None, "player_of_match": None
            },
            {
                "match_id": "hist_2", "date": "2025-01-02", "format": "ODI", "gender": "male",
                "team_type": "international", "venue_raw": "Wankhede Stadium", "venue_id": "wankhede_stadium_mumbai",
                "city": "Mumbai", "season": "2025", "team1": "Australia", "team2": "India", "toss_winner": "Australia",
                "toss_decision": "bat", "winner": "India", "result_type": "normal", "win_margin": 6,
                "win_margin_type": "wickets", "method": None, "player_of_match": None
            },
        ]
        innings = [
            {"innings_id": "hist_1_1", "match_id": "hist_1", "innings_number": 1, "batting_team": "India", "total_runs": 250, "wickets_lost": 8, "overs_completed": 50.0, "balls_delivered": 300, "is_completed": 1, "target_runs": None, "result_context": None},
            {"innings_id": "hist_1_2", "match_id": "hist_1", "innings_number": 2, "batting_team": "Australia", "total_runs": 240, "wickets_lost": 10, "overs_completed": 48.0, "balls_delivered": 288, "is_completed": 1, "target_runs": 251, "result_context": None},
            {"innings_id": "hist_2_1", "match_id": "hist_2", "innings_number": 1, "batting_team": "Australia", "total_runs": 300, "wickets_lost": 6, "overs_completed": 50.0, "balls_delivered": 300, "is_completed": 1, "target_runs": None, "result_context": None},
            {"innings_id": "hist_2_2", "match_id": "hist_2", "innings_number": 2, "batting_team": "India", "total_runs": 270, "wickets_lost": 4, "overs_completed": 45.0, "balls_delivered": 270, "is_completed": 1, "target_runs": 301, "result_context": None},
        ]
        db_mgr.insert_matches_batch(matches)
        db_mgr.insert_innings_batch(innings)

    @classmethod
    def tearDownClass(cls):
        import gc
        gc.collect()
        try:
            if cls.test_db_path.exists():
                cls.test_db_path.unlink()
            if cls.test_dir.exists():
                cls.test_dir.rmdir()
        except Exception:
            pass

    def test_01_idempotency_and_analytics_integration(self):
        # Initial baseline analytics: 1st inn avg = (250+300)/2 = 275, 2nd inn avg = (240+270)/2 = 255
        summary1 = calculate_venue_summary("wankhede_stadium_mumbai", "ODI", n=10, db_path=self.test_db_path)
        self.assertEqual(summary1["actual_match_count"], 2)
        self.assertEqual(summary1["first_innings"]["average"], 275.0)
        self.assertEqual(summary1["second_innings"]["average"], 255.0)

        # Candidate newly completed match: 1st inn = 350, 2nd inn = 280 on 2026-10-02
        new_candidate_matches = [
            {
                "id": "cric_new_001",
                "name": "India vs Australia 3rd ODI",
                "matchType": "odi",
                "status": "India won by 70 runs",
                "matchEnded": True,
                "venue": "Wankhede Stadium, Mumbai",
                "date": "2026-10-02",
                "teams": ["India", "Australia"],
                "winner": "India",
                "score": [
                    {"r": 350, "w": 4, "o": 50, "inning": "India Inning 1"},
                    {"r": 280, "w": 10, "o": 46.2, "inning": "Australia Inning 1"}
                ]
            }
        ]

        # First run: Should ingest 1 new match
        res1 = ingest_completed_matches(raw_matches=new_candidate_matches, db_path=self.test_db_path)
        self.assertEqual(res1["imported_count"], 1)
        self.assertEqual(res1["api_calls_made"], 0)

        # Immediate Second run with same candidate: Should ingest 0 new matches (Idempotency!)
        res2 = ingest_completed_matches(raw_matches=new_candidate_matches, db_path=self.test_db_path)
        self.assertEqual(res2["imported_count"], 0)
        self.assertEqual(res2["api_calls_made"], 0)

        # Combined Analytics Verification:
        # 1st Innings: (250 + 300 + 350) / 3 = 300.0
        # 2nd Innings: (240 + 270 + 280) / 3 = 263.333...
        summary2 = calculate_venue_summary("wankhede_stadium_mumbai", "ODI", n=10, db_path=self.test_db_path)
        self.assertEqual(summary2["actual_match_count"], 3)
        self.assertAlmostEqual(summary2["first_innings"]["average"], 300.0, places=1)
        self.assertAlmostEqual(summary2["second_innings"]["average"], 263.33, places=1)

        # Recent Matches ordering: the new 2026-10-02 match MUST be 1st
        recent_matches, _ = get_recent_matches("wankhede_stadium_mumbai", "ODI", n=10, db_path=self.test_db_path)
        self.assertEqual(recent_matches[0]["match_id"], "cricapi_cric_new_001")
        self.assertEqual(recent_matches[0]["date"], "2026-10-02")

        # Team Venue Analysis for India: 3 matches analyzed, 3 wins
        india_analysis = get_team_venue_analysis("India", "wankhede_stadium_mumbai", "ODI", n=10, db_path=self.test_db_path)
        self.assertEqual(india_analysis["actual_match_count"], 3)
        self.assertEqual(india_analysis["wins"], 3)


if __name__ == "__main__":
    unittest.main()
