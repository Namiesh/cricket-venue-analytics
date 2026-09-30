"""
Unit Tests for Team-Specific Venue Analysis (Mode B), Venue-Wide Analysis (Mode A), and Two-Team Analysis (Mode C).
Validates all 17 specified requirements in Section 21 using SQLite test fixtures.
"""

import unittest
import tempfile
import sqlite3
from pathlib import Path

from src.database.db_manager import DatabaseManager
from src.analytics.team_stats import (
    get_team_venue_analysis,
    analyze_match_context,
    get_team_venue_stats,
    get_head_to_head_stats,
)
from src.analytics.venue_stats import calculate_venue_summary


class TestTeamVenueAnalysis(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.test_db_dir = Path(__file__).resolve().parent.parent / "scratch_test_team_venue"
        cls.test_db_dir.mkdir(exist_ok=True)
        cls.test_db_path = cls.test_db_dir / "test_team_venue.db"

        # Create schema
        db_mgr = DatabaseManager(cls.test_db_path)
        db_mgr.create_tables()

        cls._populate_fixtures()

    @classmethod
    def _populate_fixtures(cls):
        db_mgr = DatabaseManager(cls.test_db_path)

        # Venues
        venues = [
            {"venue_id": "jb_marks_oval", "canonical_name": "JB Marks Oval, Potchefstroom", "city": "Potchefstroom", "country": "South Africa", "raw_name_examples": '["Senwes Park", "JB Marks Oval"]', "match_count_odi": 15, "match_count_t20i": 5},
            {"venue_id": "wankhede_stadium_mumbai", "canonical_name": "Wankhede Stadium, Mumbai", "city": "Mumbai", "country": "India", "raw_name_examples": '["Wankhede Stadium"]', "match_count_odi": 10, "match_count_t20i": 10},
        ]
        db_mgr.insert_venues_batch(venues)

        matches = []
        innings = []

        # 1. Matches at Wankhede Stadium (wankhede_stadium_mumbai):
        # 12 total matches: 10 with India (5 batting 1st, 5 batting 2nd), 2 without India
        for i in range(1, 13):
            m_id = f"wankhede_{i}"
            dt = f"2023-01-{i:02d}"

            if i <= 10:
                team1 = "India"
                team2 = "Australia" if i % 2 == 1 else "England"
            else:
                team1 = "Australia"
                team2 = "England"

            winner = "India" if (i <= 10 and i % 3 != 0) else ("Australia" if i % 2 == 1 else "England")
            res_type = "normal"

            matches.append({
                "match_id": m_id,
                "date": dt,
                "format": "ODI",
                "gender": "male",
                "team_type": "international",
                "venue_raw": "Wankhede Stadium",
                "venue_id": "wankhede_stadium_mumbai",
                "city": "Mumbai",
                "season": "2023",
                "team1": team1,
                "team2": team2,
                "toss_winner": team1,
                "toss_decision": "bat",
                "winner": winner,
                "result_type": res_type,
                "win_margin": 30,
                "win_margin_type": "runs",
                "method": None,
                "player_of_match": "Player X",
            })

            # India bats 1st in odd matches, 2nd in even matches (for India matches)
            if i <= 10:
                if i % 2 == 1:
                    inn1_team, inn2_team = "India", team2
                    inn1_score, inn2_score = 300 + i * 5, 250 + i * 2  # 305 to 345
                else:
                    inn1_team, inn2_team = team2, "India"
                    inn1_score, inn2_score = 240 + i * 2, 220 + i * 5  # 230 to 270
            else:
                inn1_team, inn2_team = "Australia", "England"
                inn1_score, inn2_score = 280, 260

            innings.append({
                "innings_id": f"{m_id}_1",
                "match_id": m_id,
                "innings_number": 1,
                "batting_team": inn1_team,
                "total_runs": inn1_score,
                "wickets_lost": 5,
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
                "batting_team": inn2_team,
                "total_runs": inn2_score,
                "wickets_lost": 7,
                "overs_completed": 49.0,
                "balls_delivered": 294,
                "is_completed": 1,
                "target_runs": inn1_score + 1,
                "result_context": None,
            })

        # 2. Matches for Team with ONLY 1st innings appearances (TeamAlpha)
        matches.append({
            "match_id": "alpha_1",
            "date": "2023-03-01",
            "format": "ODI",
            "gender": "male",
            "team_type": "international",
            "venue_raw": "Wankhede Stadium",
            "venue_id": "wankhede_stadium_mumbai",
            "city": "Mumbai",
            "season": "2023",
            "team1": "TeamAlpha",
            "team2": "England",
            "toss_winner": "TeamAlpha",
            "toss_decision": "bat",
            "winner": "TeamAlpha",
            "result_type": "normal",
            "win_margin": 10,
            "win_margin_type": "runs",
            "method": None,
            "player_of_match": None,
        })
        innings.append({
            "innings_id": "alpha_1_1", "match_id": "alpha_1", "innings_number": 1,
            "batting_team": "TeamAlpha", "total_runs": 290, "wickets_lost": 4,
            "overs_completed": 50.0, "balls_delivered": 300, "is_completed": 1,
            "target_runs": None, "result_context": None
        })
        innings.append({
            "innings_id": "alpha_1_2", "match_id": "alpha_1", "innings_number": 2,
            "batting_team": "England", "total_runs": 280, "wickets_lost": 9,
            "overs_completed": 50.0, "balls_delivered": 300, "is_completed": 1,
            "target_runs": 291, "result_context": None
        })

        # 3. Matches for Team with ONLY 2nd innings appearances (TeamBeta)
        matches.append({
            "match_id": "beta_1",
            "date": "2023-03-02",
            "format": "ODI",
            "gender": "male",
            "team_type": "international",
            "venue_raw": "Wankhede Stadium",
            "venue_id": "wankhede_stadium_mumbai",
            "city": "Mumbai",
            "season": "2023",
            "team1": "England",
            "team2": "TeamBeta",
            "toss_winner": "England",
            "toss_decision": "bat",
            "winner": "TeamBeta",
            "result_type": "normal",
            "win_margin": 4,
            "win_margin_type": "wickets",
            "method": None,
            "player_of_match": None,
        })
        innings.append({
            "innings_id": "beta_1_1", "match_id": "beta_1", "innings_number": 1,
            "batting_team": "England", "total_runs": 250, "wickets_lost": 8,
            "overs_completed": 50.0, "balls_delivered": 300, "is_completed": 1,
            "target_runs": None, "result_context": None
        })
        innings.append({
            "innings_id": "beta_1_2", "match_id": "beta_1", "innings_number": 2,
            "batting_team": "TeamBeta", "total_runs": 254, "wickets_lost": 6,
            "overs_completed": 47.2, "balls_delivered": 284, "is_completed": 1,
            "target_runs": 251, "result_context": None
        })

        # 4. Alias test match at Senwes Park (jb_marks_oval)
        matches.append({
            "match_id": "alias_1",
            "date": "2023-04-01",
            "format": "ODI",
            "gender": "male",
            "team_type": "international",
            "venue_raw": "Senwes Park",
            "venue_id": "jb_marks_oval",
            "city": "Potchefstroom",
            "season": "2023",
            "team1": "South Africa",
            "team2": "Australia",
            "toss_winner": "South Africa",
            "toss_decision": "bat",
            "winner": "South Africa",
            "result_type": "normal",
            "win_margin": 50,
            "win_margin_type": "runs",
            "method": None,
            "player_of_match": None,
        })
        innings.append({
            "innings_id": "alias_1_1", "match_id": "alias_1", "innings_number": 1,
            "batting_team": "South Africa", "total_runs": 310, "wickets_lost": 5,
            "overs_completed": 50.0, "balls_delivered": 300, "is_completed": 1,
            "target_runs": None, "result_context": None
        })
        innings.append({
            "innings_id": "alias_1_2", "match_id": "alias_1", "innings_number": 2,
            "batting_team": "Australia", "total_runs": 260, "wickets_lost": 10,
            "overs_completed": 45.0, "balls_delivered": 270, "is_completed": 1,
            "target_runs": 311, "result_context": None
        })

        db_mgr.insert_matches_batch(matches)
        db_mgr.insert_innings_batch(innings)

    @classmethod
    def tearDownClass(cls):
        import gc
        gc.collect()
        try:
            if cls.test_db_path.exists():
                cls.test_db_path.unlink()
            if cls.test_db_dir.exists():
                cls.test_db_dir.rmdir()
        except Exception:
            pass

    # 1. No team selected -> existing venue-wide behavior unchanged
    def test_01_no_team_selected_venue_wide(self):
        ctx = analyze_match_context(None, None, "wankhede_stadium_mumbai", "ODI", n_venue_matches=10, db_path=self.test_db_path)
        self.assertEqual(ctx["mode"], "venue_wide")
        self.assertIsNotNone(ctx["venue_summary"])

    # 2. One team selected -> team-specific venue analysis
    def test_02_one_team_selected_single_team(self):
        ctx = analyze_match_context("India", None, "wankhede_stadium_mumbai", "ODI", n_venue_matches=10, db_path=self.test_db_path)
        self.assertEqual(ctx["mode"], "single_team")
        self.assertEqual(ctx["team1"], "India")
        self.assertIsNone(ctx["team2"])
        summary = ctx["venue_summary"]
        self.assertEqual(summary["team"], "India")

    # 3. Two teams selected -> existing two-team behavior unchanged
    def test_03_two_teams_selected(self):
        ctx = analyze_match_context("India", "Australia", "wankhede_stadium_mumbai", "ODI", n_venue_matches=10, db_path=self.test_db_path)
        self.assertEqual(ctx["mode"], "two_team")
        self.assertIsNotNone(ctx["head_to_head"])

    # 4. Historical window is applied AFTER team filtering
    def test_04_window_applied_after_team_filtering(self):
        # India played 10 matches at Wankhede in test dataset.
        # If we ask for Last 5, we should get India's 5 newest matches out of India's 10 matches.
        res = get_team_venue_analysis("India", "wankhede_stadium_mumbai", "ODI", n=5, db_path=self.test_db_path)
        self.assertEqual(res["actual_match_count"], 5)
        self.assertEqual(res["total_team_venue_matches"], 10)

    # 5. Team batting first is correctly identified
    def test_05_team_batting_first_identified(self):
        res = get_team_venue_analysis("India", "wankhede_stadium_mumbai", "ODI", n=10, db_path=self.test_db_path)
        matches = res["qualifying_matches"]
        for m in matches:
            if m["innings1"]["batting_team"] == "India":
                self.assertEqual(m["team_batting_pos"], 1)

    # 6. Team batting second is correctly identified
    def test_06_team_batting_second_identified(self):
        res = get_team_venue_analysis("India", "wankhede_stadium_mumbai", "ODI", n=10, db_path=self.test_db_path)
        matches = res["qualifying_matches"]
        for m in matches:
            if m["innings2"]["batting_team"] == "India":
                self.assertEqual(m["team_batting_pos"], 2)

    # 7. Team-specific average first-innings runs
    def test_07_team_specific_avg_1st_innings(self):
        res = get_team_venue_analysis("India", "wankhede_stadium_mumbai", "ODI", n=10, db_path=self.test_db_path)
        f_inn = res["first_innings"]
        self.assertIsNotNone(f_inn["average"])
        self.assertGreater(f_inn["average"], 250)

    # 8. Team-specific average second-innings runs
    def test_08_team_specific_avg_2nd_innings(self):
        res = get_team_venue_analysis("India", "wankhede_stadium_mumbai", "ODI", n=10, db_path=self.test_db_path)
        s_inn = res["second_innings"]
        self.assertIsNotNone(s_inn["average"])
        self.assertGreater(s_inn["average"], 200)

    # 9. Team-specific highest/lowest scores
    def test_09_team_specific_highest_lowest(self):
        res = get_team_venue_analysis("India", "wankhede_stadium_mumbai", "ODI", n=10, db_path=self.test_db_path)
        f_inn = res["first_innings"]
        self.assertGreaterEqual(f_inn["highest"], f_inn["lowest"])

    # 10. Team win/loss calculation
    def test_10_team_win_loss_calculation(self):
        res = get_team_venue_analysis("India", "wankhede_stadium_mumbai", "ODI", n=10, db_path=self.test_db_path)
        self.assertEqual(res["wins"] + res["losses"] + res["ties"], res["actual_match_count"])

    # 11. Team with fewer than N matches
    def test_11_team_fewer_than_n_matches(self):
        # India played 10 matches. We ask for n=50. Should return actual_match_count = 10.
        res = get_team_venue_analysis("India", "wankhede_stadium_mumbai", "ODI", n=50, db_path=self.test_db_path)
        self.assertEqual(res["actual_match_count"], 10)

    # 12. Team with zero matches
    def test_12_team_zero_matches(self):
        res = get_team_venue_analysis("NonExistentTeam", "wankhede_stadium_mumbai", "ODI", n=10, db_path=self.test_db_path)
        self.assertEqual(res["actual_match_count"], 0)
        self.assertIn("No qualifying matches found", res["status_message"])

    # 13. Team with only first-innings appearances
    def test_13_team_only_first_innings(self):
        res = get_team_venue_analysis("TeamAlpha", "wankhede_stadium_mumbai", "ODI", n=10, db_path=self.test_db_path)
        self.assertEqual(res["actual_match_count"], 1)
        self.assertIsNotNone(res["first_innings"]["average"])
        self.assertIsNone(res["second_innings"]["average"])

    # 14. Team with only second-innings appearances
    def test_14_team_only_second_innings(self):
        res = get_team_venue_analysis("TeamBeta", "wankhede_stadium_mumbai", "ODI", n=10, db_path=self.test_db_path)
        self.assertEqual(res["actual_match_count"], 1)
        self.assertIsNone(res["first_innings"]["average"])
        self.assertIsNotNone(res["second_innings"]["average"])

    # 15. Canonical venue aliases
    def test_15_canonical_venue_aliases(self):
        # Querying Senwes Park resolves to jb_marks_oval and finds South Africa's match
        res = get_team_venue_analysis("South Africa", "Senwes Park", "ODI", n=10, db_path=self.test_db_path)
        self.assertEqual(res["venue_id"], "jb_marks_oval")
        self.assertEqual(res["actual_match_count"], 1)

    # 16. ODI/T20I separation
    def test_16_format_separation(self):
        res_odi = get_team_venue_analysis("India", "wankhede_stadium_mumbai", "ODI", n=10, db_path=self.test_db_path)
        res_t20 = get_team_venue_analysis("India", "wankhede_stadium_mumbai", "T20I", n=10, db_path=self.test_db_path)
        self.assertEqual(res_odi["format"], "ODI")
        self.assertEqual(res_t20["format"], "T20I")
        self.assertNotEqual(res_odi["actual_match_count"], res_t20["actual_match_count"])

    # 17. No duplicate matches
    def test_17_no_duplicate_matches(self):
        res = get_team_venue_analysis("India", "wankhede_stadium_mumbai", "ODI", n=10, db_path=self.test_db_path)
        m_ids = [m["match_id"] for m in res["qualifying_matches"]]
        self.assertEqual(len(m_ids), len(set(m_ids)))


if __name__ == "__main__":
    unittest.main()
