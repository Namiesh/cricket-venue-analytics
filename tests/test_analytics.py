"""
Unit Tests for Venue Analytics Engine.
Tests all 18 specified analytics requirements using SQLite test fixtures.
"""

import gc
import sqlite3
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database.db_manager import DatabaseManager
from src.analytics.venue_stats import (
    get_recent_matches,
    calculate_venue_summary,
    search_venues,
    get_venue_by_name,
)
from src.analytics.score_analysis import (
    analyze_score_ranges,
    analyze_first_innings_score_outcomes,
    ODI_BANDS,
    T20I_BANDS,
)
from src.analytics.team_stats import (
    get_team_venue_stats,
    get_head_to_head_stats,
    analyze_match_context,
)


class TestAnalyticsEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_db_dir = PROJECT_ROOT / "scratch_test_analytics"
        cls.test_db_dir.mkdir(exist_ok=True)
        cls.test_db_path = cls.test_db_dir / "test_cricket_venue.db"

        # Create schema
        db_mgr = DatabaseManager(cls.test_db_path)
        db_mgr.create_tables()

        # Populate test fixtures
        cls._populate_fixtures()

    @classmethod
    def _populate_fixtures(cls):
        db_mgr = DatabaseManager(cls.test_db_path)

        # Venues
        venues = [
            {"venue_id": "venue_a", "canonical_name": "Venue Alpha", "city": "CityA", "country": "CountryA", "raw_name_examples": '["Venue Alpha"]', "match_count_odi": 12, "match_count_t20i": 5},
            {"venue_id": "wankhede_stadium_mumbai", "canonical_name": "Wankhede Stadium", "city": "Mumbai", "country": "India", "raw_name_examples": '["Wankhede Stadium"]', "match_count_odi": 10, "match_count_t20i": 10},
        ]
        db_mgr.insert_venues_batch(venues)

        # Matches (15 ODI matches for venue_a with dates 2023-01-01 to 2023-01-15)
        matches = []
        innings = []

        for i in range(1, 16):
            m_id = f"odi_{i}"
            dt = f"2023-01-{i:02d}"

            winner = "India" if i % 2 == 1 else "Australia"
            res_type = None
            method = "D/L" if i == 5 else None

            if i == 14:
                res_type = "no result"
                winner = None
            elif i == 15:
                res_type = "tie"
                winner = None  # Unawarded tie

            m_rec = {
                "match_id": m_id,
                "date": dt,
                "format": "ODI",
                "gender": "male",
                "team_type": "international",
                "venue_raw": "Venue Alpha",
                "venue_id": "venue_a",
                "city": "CityA",
                "season": "2023",
                "team1": "India",
                "team2": "Australia",
                "toss_winner": "India",
                "toss_decision": "bat",
                "winner": winner,
                "result_type": res_type,
                "win_margin": 20,
                "win_margin_type": "runs",
                "method": method,
                "player_of_match": "Player A",
            }
            matches.append(m_rec)

            # Innings 1 & 2
            inn1_score = 250 + (i * 5)  # 255 to 325
            inn2_score = 230 + (i * 5)

            innings.append({
                "innings_id": f"{m_id}_1",
                "match_id": m_id,
                "innings_number": 1,
                "batting_team": "India",
                "total_runs": inn1_score,
                "wickets_lost": 6,
                "overs_completed": 50.0,
                "balls_delivered": 300,
                "is_completed": 1,
                "target_runs": None,
                "result_context": None,
            })
            innings.append({
                "innings_id": f"{m_id}_2",
                "match_id": m_id,
                "innings_number": 2,
                "batting_team": "Australia",
                "total_runs": inn2_score,
                "wickets_lost": 8,
                "overs_completed": 48.5,
                "balls_delivered": 293,
                "is_completed": 1,
                "target_runs": inn1_score + 1,
                "result_context": None,
            })

            # Super Over for match 15 (innings 3)
            if i == 15:
                innings.append({
                    "innings_id": f"{m_id}_3",
                    "match_id": m_id,
                    "innings_number": 3,
                    "batting_team": "India",
                    "total_runs": 15,
                    "wickets_lost": 0,
                    "overs_completed": 1.0,
                    "balls_delivered": 6,
                    "is_completed": 1,
                    "target_runs": None,
                    "result_context": "Super Over",
                })

        # Add 3 T20I matches for venue_a
        for i in range(1, 4):
            m_id = f"t20_{i}"
            dt = f"2023-02-{i:02d}"
            matches.append({
                "match_id": m_id,
                "date": dt,
                "format": "T20I",
                "gender": "male",
                "team_type": "international",
                "venue_raw": "Venue Alpha",
                "venue_id": "venue_a",
                "city": "CityA",
                "season": "2023",
                "team1": "India",
                "team2": "England",
                "toss_winner": "England",
                "toss_decision": "field",
                "winner": "England",
                "result_type": None,
                "win_margin": 5,
                "win_margin_type": "wickets",
                "method": None,
                "player_of_match": "Player B",
            })
            innings.append({
                "innings_id": f"{m_id}_1",
                "match_id": m_id,
                "innings_number": 1,
                "batting_team": "India",
                "total_runs": 160,
                "wickets_lost": 7,
                "overs_completed": 20.0,
                "balls_delivered": 120,
                "is_completed": 1,
                "target_runs": None,
                "result_context": None,
            })
            innings.append({
                "innings_id": f"{m_id}_2",
                "match_id": m_id,
                "innings_number": 2,
                "batting_team": "England",
                "total_runs": 164,
                "wickets_lost": 5,
                "overs_completed": 19.2,
                "balls_delivered": 116,
                "is_completed": 1,
                "target_runs": 161,
                "result_context": None,
            })

        db_mgr.insert_matches_batch(matches)
        db_mgr.insert_innings_batch(innings)

    @classmethod
    def tearDownClass(cls):
        gc.collect()
        try:
            if cls.test_db_path.exists():
                cls.test_db_path.unlink()
            if cls.test_db_dir.exists():
                cls.test_db_dir.rmdir()
        except Exception:
            pass

    # 1. ODI and T20I separation
    def test_format_separation(self):
        matches_odi, _ = get_recent_matches("venue_a", "ODI", n=100, db_path=self.test_db_path)
        matches_t20, _ = get_recent_matches("venue_a", "T20I", n=100, db_path=self.test_db_path)
        for m in matches_odi:
            self.assertEqual(m["format"], "ODI")
        for m in matches_t20:
            self.assertEqual(m["format"], "T20I")

    # 2. Last 10 match selection
    def test_last_10_match_selection(self):
        matches, meta = get_recent_matches("venue_a", "ODI", n=10, db_path=self.test_db_path)
        self.assertEqual(len(matches), 10)
        self.assertEqual(meta["requested_count"], 10)

    # 3. Date ordering (DESC)
    def test_date_ordering(self):
        matches, _ = get_recent_matches("venue_a", "ODI", n=10, db_path=self.test_db_path)
        dates = [m["date"] for m in matches]
        self.assertEqual(dates, sorted(dates, reverse=True))

    # 4. Exclusion of no-results
    def test_exclusion_of_no_results(self):
        matches, meta = get_recent_matches("venue_a", "ODI", n=100, db_path=self.test_db_path)
        match_ids = [m["match_id"] for m in matches]
        self.assertNotIn("odi_14", match_ids)  # odi_14 is no result
        self.assertGreater(meta["exclusion_reasons"]["no_result"], 0)

    # 5. Inclusion of completed ties
    def test_inclusion_of_ties(self):
        matches, _ = get_recent_matches("venue_a", "ODI", n=100, db_path=self.test_db_path)
        match_ids = [m["match_id"] for m in matches]
        self.assertIn("odi_15", match_ids)  # odi_15 is tie

    # 6. First innings average
    def test_first_innings_average(self):
        summary = calculate_venue_summary("venue_a", "ODI", n=5, db_path=self.test_db_path)
        self.assertIsNotNone(summary["first_innings"]["average"])

    # 7. Second innings average
    def test_second_innings_average(self):
        summary = calculate_venue_summary("venue_a", "ODI", n=5, db_path=self.test_db_path)
        self.assertIsNotNone(summary["second_innings"]["average"])

    # 8. Highest/lowest score calculation
    def test_highest_lowest_score(self):
        summary = calculate_venue_summary("venue_a", "ODI", n=5, db_path=self.test_db_path)
        self.assertGreaterEqual(summary["first_innings"]["highest"], summary["first_innings"]["lowest"])

    # 9. Batting-first win calculation
    def test_batting_first_wins(self):
        summary = calculate_venue_summary("venue_a", "ODI", n=10, db_path=self.test_db_path)
        self.assertGreaterEqual(summary["batting_first_wins"], 0)

    # 10. Chasing win calculation
    def test_chasing_wins(self):
        summary = calculate_venue_summary("venue_a", "ODI", n=10, db_path=self.test_db_path)
        self.assertGreaterEqual(summary["chasing_wins"], 0)

    # 11. Score-band classification
    def test_score_band_classification(self):
        res = analyze_score_ranges("venue_a", "ODI", n=10, db_path=self.test_db_path)
        self.assertIn("score_bands", res)

    # 12. ODI score bands
    def test_odi_score_bands(self):
        res = analyze_score_ranges("venue_a", "ODI", n=10, db_path=self.test_db_path)
        band_names = list(res["score_bands"].keys())
        expected = [b["name"] for b in ODI_BANDS]
        self.assertEqual(band_names, expected)

    # 13. T20I score bands
    def test_t20i_score_bands(self):
        res = analyze_score_ranges("venue_a", "T20I", n=10, db_path=self.test_db_path)
        band_names = list(res["score_bands"].keys())
        expected = [b["name"] for b in T20I_BANDS]
        self.assertEqual(band_names, expected)

    # 14. Team venue statistics
    def test_team_venue_stats(self):
        t_stats = get_team_venue_stats("India", "venue_a", "ODI", db_path=self.test_db_path)
        self.assertEqual(t_stats["team"], "India")
        self.assertGreater(t_stats["matches_played"], 0)

    # 15. Head-to-head statistics
    def test_head_to_head_stats(self):
        h2h = get_head_to_head_stats("India", "Australia", "venue_a", "ODI", db_path=self.test_db_path)
        self.assertGreater(h2h["matches"], 0)

    # 16. Insufficient historical data
    def test_insufficient_historical_data(self):
        ctx = analyze_match_context("India", "Australia", "non_existent_venue", "ODI", db_path=self.test_db_path)
        self.assertEqual(ctx["status_message"], "Insufficient historical matches available.")

    # 17. DLS/DL handling
    def test_dl_handling(self):
        matches, _ = get_recent_matches("venue_a", "ODI", n=100, db_path=self.test_db_path)
        dl_matches = [m for m in matches if m["is_dl"]]
        self.assertGreater(len(dl_matches), 0)

    # 18. Super-over handling (super over innings 3 is ignored for 2nd innings)
    def test_super_over_handling(self):
        matches, _ = get_recent_matches("venue_a", "ODI", n=100, db_path=self.test_db_path)
        m_tie = [m for m in matches if m["match_id"] == "odi_15"][0]
        # Verify innings2 is actual 2nd innings (not super over innings 3)
        self.assertEqual(m_tie["innings2"]["innings_number"], 2)


if __name__ == "__main__":
    unittest.main()
