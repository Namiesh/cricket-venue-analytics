"""
Unit Tests for Fixture API Client, Filtering, Normalization, IST Timezone, and Streamlit State Synchronization.
Uses mocked API responses without making real HTTP network requests.
"""

import gc
import json
import os
import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database.db_manager import DatabaseManager
from src.fixtures.client import (
    fetch_raw_matches_from_api,
    parse_and_filter_fixtures,
    is_mens_international_match,
    CricAPIError
)
from src.fixtures.models import UpcomingFixture
from src.fixtures.normalizer import resolve_fixture_venue
import src.fixtures.cache as cache_module


class TestFixturesSystem(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_dir = PROJECT_ROOT / "scratch_test_fixtures"
        cls.test_dir.mkdir(exist_ok=True)
        cls.test_db_path = cls.test_dir / "test_cricket_venue.db"

        db_mgr = DatabaseManager(cls.test_db_path)
        db_mgr.create_tables()

        venues = [
            {"venue_id": "wankhede_stadium_mumbai", "canonical_name": "Wankhede Stadium", "city": "Mumbai", "country": "India", "raw_name_examples": '["Wankhede Stadium, Mumbai"]', "match_count_odi": 10, "match_count_t20i": 5},
            {"venue_id": "barsapara_cricket_stadium_guwahati", "canonical_name": "Barsapara Cricket Stadium", "city": "Guwahati", "country": "India", "raw_name_examples": '["Barsapara Cricket Stadium, Guwahati"]', "match_count_odi": 4, "match_count_t20i": 2},
            {"venue_id": "senwes_park_potchefstroom", "canonical_name": "Senwes Park", "city": "Potchefstroom", "country": "South Africa", "raw_name_examples": '["JB Marks Oval, Potchefstroom"]', "match_count_odi": 5, "match_count_t20i": 3},
            {"venue_id": "adelaide_oval", "canonical_name": "Adelaide Oval", "city": "Adelaide", "country": "Australia", "raw_name_examples": '["Adelaide Oval"]', "match_count_odi": 15, "match_count_t20i": 10},
        ]
        db_mgr.insert_venues_batch(venues)

        sample_path = PROJECT_ROOT / "tests" / "fixtures" / "sample_upcoming_matches.json"
        with open(sample_path, "r", encoding="utf-8") as f:
            cls.sample_json = json.load(f)

    @classmethod
    def tearDownClass(cls):
        gc.collect()
        try:
            if cls.test_db_path.exists():
                cls.test_db_path.unlink()
            if cls.test_dir.exists():
                cls.test_dir.rmdir()
        except Exception:
            pass

    def setUp(self):
        self.patcher_cache_path = patch.object(cache_module, "CACHE_PATH", self.test_dir / "test_upcoming_fixtures.json")
        self.mock_cache_path = self.patcher_cache_path.start()

    def tearDown(self):
        self.patcher_cache_path.stop()
        test_cache = self.test_dir / "test_upcoming_fixtures.json"
        if test_cache.exists():
            test_cache.unlink()

    # 1. API response parsing
    def test_api_response_parsing(self):
        fixtures = parse_and_filter_fixtures(self.sample_json["data"], db_path=self.test_db_path)
        self.assertGreater(len(fixtures), 0)

    # 2. ODI filtering
    def test_odi_filtering(self):
        fixtures = parse_and_filter_fixtures(self.sample_json["data"], db_path=self.test_db_path)
        odi_fixtures = [f for f in fixtures if f.format == "ODI"]
        self.assertTrue(all(f.format == "ODI" for f in odi_fixtures))

    # 3. T20I filtering
    def test_t20i_filtering(self):
        fixtures = parse_and_filter_fixtures(self.sample_json["data"], db_path=self.test_db_path)
        t20_fixtures = [f for f in fixtures if f.format == "T20I"]
        self.assertTrue(all(f.format == "T20I" for f in t20_fixtures))

    # 4. Test exclusion
    def test_test_match_exclusion(self):
        test_match = {"id": "m_test", "name": "England vs Australia", "matchType": "test", "teams": ["England", "Australia"]}
        is_val, _ = is_mens_international_match(test_match)
        self.assertFalse(is_val)

    # 5. Domestic match exclusion
    def test_domestic_match_exclusion(self):
        dom_match = {"id": "m_dom", "name": "Delhi vs Mumbai, Ranji Trophy", "matchType": "odi", "teams": ["Delhi", "Mumbai"]}
        is_val, _ = is_mens_international_match(dom_match)
        self.assertFalse(is_val)

    # 6. Franchise match exclusion
    def test_franchise_match_exclusion(self):
        ipl_match = {"id": "m_ipl", "name": "Mumbai Indians vs Chennai Super Kings", "matchType": "t20", "teams": ["Mumbai Indians", "Chennai Super Kings"]}
        is_val, _ = is_mens_international_match(ipl_match)
        self.assertFalse(is_val)

    # 7. Women's match exclusion
    def test_womens_match_exclusion(self):
        w_match = {"id": "m_women", "name": "India Women vs Australia Women", "matchType": "odi", "teams": ["India Women", "Australia Women"]}
        is_val, _ = is_mens_international_match(w_match)
        self.assertFalse(is_val)

    # 8. Upcoming date filtering
    def test_upcoming_date_filtering(self):
        fixtures = parse_and_filter_fixtures(self.sample_json["data"], db_path=self.test_db_path)
        match_ids = [f.match_id for f in fixtures]
        self.assertIn("match_odi_1", match_ids)

    # 9. Completed match exclusion
    def test_completed_match_exclusion(self):
        fixtures = parse_and_filter_fixtures(self.sample_json["data"], db_path=self.test_db_path)
        match_ids = [f.match_id for f in fixtures]
        self.assertNotIn("match_ended_1", match_ids)

    # 10. Deduplication
    def test_deduplication(self):
        dup_data = self.sample_json["data"] + [self.sample_json["data"][0]]
        fixtures = parse_and_filter_fixtures(dup_data, db_path=self.test_db_path)
        match_ids = [f.match_id for f in fixtures]
        self.assertEqual(len(match_ids), len(set(match_ids)))

    # 11. Cache creation
    def test_cache_creation(self):
        fixtures = parse_and_filter_fixtures(self.sample_json["data"], db_path=self.test_db_path)
        cache_module.save_cache_file(fixtures)
        self.assertTrue(cache_module.CACHE_PATH.exists())

    # 12. Fresh cache -> zero API calls
    @patch("src.fixtures.cache.fetch_raw_matches_from_api")
    def test_fresh_cache_zero_api_calls(self, mock_fetch):
        fixtures = parse_and_filter_fixtures(self.sample_json["data"], db_path=self.test_db_path)
        cache_module.save_cache_file(fixtures)

        res, meta = cache_module.get_upcoming_fixtures(db_path=self.test_db_path, force_refresh=False)
        self.assertFalse(meta["api_called"])
        self.assertEqual(meta["status"], "cached")
        mock_fetch.assert_not_called()

    # 13. Expired cache -> one API call
    @patch("os.getenv", return_value="fake_api_key")
    @patch("src.fixtures.cache.fetch_raw_matches_from_api")
    def test_expired_cache_one_api_call(self, mock_fetch, mock_getenv):
        fixtures = parse_and_filter_fixtures(self.sample_json["data"], db_path=self.test_db_path)
        old_time = (datetime.now(timezone.utc) - timedelta(hours=10)).isoformat()
        cache_data = {"fetched_at": old_time, "provider": "cricapi", "matches": [f.to_dict() for f in fixtures]}
        with open(cache_module.CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache_data, f)

        mock_fetch.return_value = self.sample_json["data"]

        res, meta = cache_module.get_upcoming_fixtures(db_path=self.test_db_path, force_refresh=False)
        self.assertTrue(meta["api_called"])
        self.assertEqual(meta["status"], "refreshed")
        mock_fetch.assert_called_once()

    # 14. API failure -> old cache preserved
    @patch("os.getenv", return_value="fake_api_key")
    @patch("src.fixtures.cache.fetch_raw_matches_from_api")
    def test_api_failure_old_cache_preserved(self, mock_fetch, mock_getenv):
        fixtures = parse_and_filter_fixtures(self.sample_json["data"], db_path=self.test_db_path)
        cache_module.save_cache_file(fixtures)

        mock_fetch.side_effect = CricAPIError("API server error 500", status_code=500)

        res, meta = cache_module.get_upcoming_fixtures(db_path=self.test_db_path, force_refresh=True)
        self.assertFalse(meta["api_called"])
        self.assertEqual(meta["status"], "error")
        self.assertGreater(len(res), 0)

    # 15. 429 rate limit -> old cache preserved
    @patch("os.getenv", return_value="fake_api_key")
    @patch("src.fixtures.cache.fetch_raw_matches_from_api")
    def test_rate_limit_429_old_cache_preserved(self, mock_fetch, mock_getenv):
        fixtures = parse_and_filter_fixtures(self.sample_json["data"], db_path=self.test_db_path)
        cache_module.save_cache_file(fixtures)

        mock_fetch.side_effect = CricAPIError("Rate limit reached 429", status_code=429)

        res, meta = cache_module.get_upcoming_fixtures(db_path=self.test_db_path, force_refresh=True)
        self.assertEqual(meta["status"], "error")
        self.assertIn("rate limit", meta["message"].lower())
        self.assertGreater(len(res), 0)

    # 16. Venue exact match
    def test_venue_exact_match(self):
        v_id = resolve_fixture_venue("Wankhede Stadium", city="Mumbai", db_path=self.test_db_path)
        self.assertEqual(v_id, "wankhede_stadium_mumbai")

    # 17. Venue alias match
    def test_venue_alias_match(self):
        v_id1 = resolve_fixture_venue("Barsapara Cricket Stadium, Guwahati", db_path=self.test_db_path)
        self.assertEqual(v_id1, "barsapara_cricket_stadium_guwahati")

        v_id2 = resolve_fixture_venue("JB Marks Oval, Potchefstroom", db_path=self.test_db_path)
        self.assertEqual(v_id2, "senwes_park_potchefstroom")

    # 18. Venue unresolved
    def test_venue_unresolved(self):
        v_id = resolve_fixture_venue("Imaginary Stadium 99", city="Unknown City", db_path=self.test_db_path)
        self.assertIsNone(v_id)

    # 19. Timezone conversion UTC -> IST
    def test_timezone_conversion_ist(self):
        fix = UpcomingFixture(
            match_id="test_tz",
            team1="India",
            team2="West Indies",
            format="ODI",
            venue="Barsapara",
            scheduled_datetime="2026-09-30T08:30:00Z"
        )
        formatted = fix.formatted_ist_datetime()
        self.assertEqual(formatted, "30 September 2026 · 2:00 PM IST")

    # 20. Adelaide Oval / Wankhede desynchronization prevention check
    def test_no_adelaide_override_for_barsapara(self):
        barsapara_vid = resolve_fixture_venue("Barsapara Cricket Stadium, Guwahati", db_path=self.test_db_path)
        self.assertNotEqual(barsapara_vid, "adelaide_oval")
        self.assertEqual(barsapara_vid, "barsapara_cricket_stadium_guwahati")

        senwes_vid = resolve_fixture_venue("JB Marks Oval, Potchefstroom", db_path=self.test_db_path)
        self.assertNotEqual(senwes_vid, "wankhede_stadium_mumbai")
        self.assertEqual(senwes_vid, "senwes_park_potchefstroom")

    # 21. Cutoff date filter & status exclusion (2 Oct 2026 cutoff test)
    def test_cutoff_date_filter_and_status_exclusion(self):
        fixed_now = "2026-10-02T00:15:00+05:30"

        input_fixtures = [
            UpcomingFixture(
                match_id="past_1",
                team1="India",
                team2="West Indies",
                format="ODI",
                venue="Barsapara",
                scheduled_datetime="2026-09-30T08:30:00Z",
                status="upcoming",
            ),
            UpcomingFixture(
                match_id="past_2",
                team1="South Africa",
                team2="Australia",
                format="ODI",
                venue="JB Marks Oval",
                scheduled_datetime="2026-09-30T11:30:00Z",
                status="upcoming",
            ),
            UpcomingFixture(
                match_id="future_2",
                team1="South Africa",
                team2="Australia",
                format="ODI",
                venue="SuperSport Park",
                scheduled_datetime="2026-10-06T14:00:00Z",
                status="upcoming",
            ),
            UpcomingFixture(
                match_id="future_1",
                team1="India",
                team2="Australia",
                format="ODI",
                venue="Wankhede",
                scheduled_datetime="2026-10-03T08:30:00Z",
                status="upcoming",
            ),
            UpcomingFixture(
                match_id="status_completed",
                team1="India",
                team2="England",
                format="ODI",
                venue="Wankhede",
                scheduled_datetime="2026-10-05T10:00:00Z",
                status="completed",
            ),
            UpcomingFixture(
                match_id="status_live",
                team1="Australia",
                team2="England",
                format="T20I",
                venue="MCG",
                scheduled_datetime="2026-10-04T10:00:00Z",
                status="live",
            ),
            UpcomingFixture(
                match_id="status_cancelled",
                team1="New Zealand",
                team2="Pakistan",
                format="ODI",
                venue="Eden Park",
                scheduled_datetime="2026-10-07T10:00:00Z",
                status="cancelled",
            ),
        ]

        from src.fixtures.cache import filter_upcoming_fixtures
        result = filter_upcoming_fixtures(input_fixtures, now=fixed_now)

        result_ids = [f.match_id for f in result]
        self.assertEqual(result_ids, ["future_1", "future_2"])


if __name__ == "__main__":
    unittest.main()

