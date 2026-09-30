"""
Unit Tests for Data Ingestion, Venue Normalization, and Score Calculation using unittest.
"""

import json
import unittest
from pathlib import Path
from src.processing.venue_normalizer import normalize_venue, get_canonical_venue_info
from src.ingestion.parser import parse_cricsheet_json


class TestIngestionAndProcessing(unittest.TestCase):
    def test_venue_normalization(self):
        # Test known aliases mapping to same ID
        v1 = normalize_venue("Wankhede Stadium, Mumbai")
        v2 = normalize_venue("Wankhede Stadium")
        self.assertEqual(v1, "wankhede_stadium_mumbai")
        self.assertEqual(v2, "wankhede_stadium_mumbai")

        # Test Chinnaswamy variants
        v3 = normalize_venue("M. Chinnaswamy Stadium", "Bengaluru")
        v4 = normalize_venue("M Chinnaswamy Stadium")
        self.assertEqual(v3, "m_chinnaswamy_stadium_bengaluru")
        self.assertEqual(v4, "m_chinnaswamy_stadium_bengaluru")

        # Test unknown venue fallback
        v5_id, c_name, city, country = get_canonical_venue_info("Custom New Stadium", "Leeds")
        self.assertEqual(v5_id, "custom_new_stadium_leeds")
        self.assertEqual(c_name, "Custom New Stadium")
        self.assertEqual(city, "Leeds")

    def test_parser_sample_data(self):
        sample_match = {
            "info": {
                "balls_per_over": 6,
                "city": "Sydney",
                "dates": ["2023-01-01"],
                "gender": "male",
                "match_type": "ODI",
                "team_type": "international",
                "teams": ["Australia", "England"],
                "toss": {"decision": "bat", "winner": "Australia"},
                "venue": "Sydney Cricket Ground",
                "outcome": {
                    "winner": "Australia",
                    "by": {"runs": 50},
                    "method": "D/L"
                }
            },
            "innings": [
                {
                    "team": "Australia",
                    "overs": [
                        {
                            "over": 0,
                            "deliveries": [
                                # 1 wide (not legal ball, 1 run extra)
                                {"runs": {"batter": 0, "extras": 1, "total": 1}, "extras": {"wides": 1}},
                                # 1 legal ball (4 runs)
                                {"runs": {"batter": 4, "extras": 0, "total": 4}},
                                # 1 legbye (legal ball, 1 run)
                                {"runs": {"batter": 0, "extras": 1, "total": 1}, "extras": {"legbyes": 1}},
                                # 1 wicket (legal ball)
                                {"runs": {"batter": 0, "extras": 0, "total": 0}, "wickets": [{"player_out": "A"}]}
                            ]
                        }
                    ]
                }
            ]
        }

        tmp_dir = Path("scratch_test_dir")
        tmp_dir.mkdir(exist_ok=True)
        file_path = tmp_dir / "12345.json"
        try:
            file_path.write_text(json.dumps(sample_match), encoding="utf-8")

            res = parse_cricsheet_json(file_path, "ODI")
            self.assertIsNotNone(res)
            match_rec, innings_recs = res

            # Format classification
            self.assertEqual(match_rec["format"], "ODI")
            self.assertEqual(match_rec["gender"], "male")
            self.assertEqual(match_rec["team_type"], "international")
            self.assertEqual(match_rec["method"], "D/L")
            self.assertEqual(match_rec["winner"], "Australia")
            self.assertEqual(match_rec["win_margin"], 50)
            self.assertEqual(match_rec["win_margin_type"], "runs")
            self.assertEqual(match_rec["venue_id"], "scg_sydney")

            # Innings calculations
            self.assertEqual(len(innings_recs), 1)
            inn = innings_recs[0]
            self.assertEqual(inn["total_runs"], 6)  # 1 wide + 4 + 1 legbye
            self.assertEqual(inn["wickets_lost"], 1)
            self.assertEqual(inn["balls_delivered"], 3)  # 1 wide ignored, 3 legal balls
            self.assertEqual(inn["overs_completed"], 0.3)
        finally:
            if file_path.exists():
                file_path.unlink()
            if tmp_dir.exists():
                tmp_dir.rmdir()

    def test_t20i_format_classification(self):
        sample_match = {
            "info": {
                "dates": ["2023-01-01"],
                "gender": "male",
                "match_type": "T20",
                "team_type": "international",
                "teams": ["India", "Pakistan"],
                "venue": "Gabba",
                "outcome": {"result": "tie"}
            },
            "innings": []
        }
        tmp_dir = Path("scratch_test_dir")
        tmp_dir.mkdir(exist_ok=True)
        file_path = tmp_dir / "99999.json"
        try:
            file_path.write_text(json.dumps(sample_match), encoding="utf-8")

            res = parse_cricsheet_json(file_path, "T20I")
            self.assertIsNotNone(res)
            match_rec, _ = res
            self.assertEqual(match_rec["format"], "T20I")
            self.assertEqual(match_rec["result_type"], "tie")
            self.assertIsNone(match_rec["winner"])
        finally:
            if file_path.exists():
                file_path.unlink()
            if tmp_dir.exists():
                tmp_dir.rmdir()

    def test_no_result_handling(self):
        sample_match = {
            "info": {
                "dates": ["2023-01-01"],
                "gender": "male",
                "match_type": "ODI",
                "team_type": "international",
                "teams": ["India", "Pakistan"],
                "venue": "Gabba",
                "outcome": {"result": "no result"}
            },
            "innings": []
        }
        tmp_dir = Path("scratch_test_dir")
        tmp_dir.mkdir(exist_ok=True)
        file_path = tmp_dir / "88888.json"
        try:
            file_path.write_text(json.dumps(sample_match), encoding="utf-8")

            res = parse_cricsheet_json(file_path, "ODI")
            self.assertIsNotNone(res)
            match_rec, _ = res
            self.assertEqual(match_rec["result_type"], "no result")
            self.assertIsNone(match_rec["winner"])
        finally:
            if file_path.exists():
                file_path.unlink()
            if tmp_dir.exists():
                tmp_dir.rmdir()


if __name__ == "__main__":
    unittest.main()
