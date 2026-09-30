"""
Regression Tests for Fixture Cache, Venue Normalization, Match Context Schema, and Streamlit Data Contracts.
"""

import unittest
import tempfile
import sqlite3
import json
from pathlib import Path

from src.fixtures.models import UpcomingFixture
from src.fixtures.cache import (
    get_upcoming_fixtures,
    save_cache_file,
    is_valid_cached_fixture,
    DEFAULT_FIXTURES,
)
from src.fixtures.client import is_mens_international_match
from src.analytics.team_stats import analyze_match_context
from src.analytics.score_analysis import analyze_score_ranges
from src.processing.venue_normalizer import get_canonical_venue_info


class TestRegressions(unittest.TestCase):

    def test_regression_a_fixture_cache_preservation(self):
        """TEST A — Valid upcoming international ODI fixtures survive parse -> normalize -> validate -> cache -> load."""
        fixtures, meta = get_upcoming_fixtures()
        self.assertGreaterEqual(len(fixtures), 2)

        match_ids = [f.match_id for f in fixtures]
        self.assertIn("cric_ind_wi_odi_2", match_ids)
        self.assertIn("cric_sa_aus_odi_3", match_ids)

        for fix in fixtures:
            self.assertTrue(is_valid_cached_fixture(fix.to_dict()))
            self.assertIn(fix.format, ["ODI", "T20I"])
            self.assertIsNotNone(fix.canonical_venue_id)
            self.assertIsNotNone(fix.canonical_display_name)

    def test_regression_b_unresolved_venue_preservation(self):
        """TEST B — Valid international fixture with unknown venue is NOT discarded."""
        m_dict = {
            "matchType": "odi",
            "name": "India vs Australia 1st ODI",
            "status": "upcoming",
            "teams": ["India", "Australia"],
            "venue": "Brand New Unregistered Stadium",
            "dateTimeGMT": "2026-10-15T09:30:00Z",
        }
        is_valid, fmt = is_mens_international_match(m_dict)
        self.assertTrue(is_valid)
        self.assertEqual(fmt, "ODI")

        # Create UpcomingFixture object
        fix = UpcomingFixture(
            match_id="test_unregistered_1",
            team1="India",
            team2="Australia",
            format=fmt,
            venue="Brand New Unregistered Stadium",
            scheduled_datetime="2026-10-15T09:30:00Z",
        )
        self.assertEqual(fix.venue, "Brand New Unregistered Stadium")
        self.assertIsNotNone(fix.canonical_venue_id)
        self.assertTrue(is_valid_cached_fixture(fix.to_dict()))

    def test_regression_c_match_context_schema(self):
        """TEST C — analyze_match_context() returns documented expected structure."""
        ctx = analyze_match_context("India", "Australia", "jb_marks_oval", "ODI")
        self.assertIn("venue_summary", ctx)
        self.assertIn("score_ranges", ctx)
        self.assertIn("score_analysis", ctx)
        self.assertIn("team1_stats", ctx)
        self.assertIn("team2_stats", ctx)
        self.assertIn("head_to_head", ctx)
        self.assertIn("status_message", ctx)

    def test_regression_d_streamlit_rendering_data_contract(self):
        """TEST D — Object used by line 454 supports batting_first_win_percentage without TypeError."""
        ctx = analyze_match_context("India", "Australia", "jb_marks_oval", "ODI")
        score_res = ctx["score_ranges"]
        bands_data = score_res.get("score_bands", score_res) if isinstance(score_res, dict) else score_res

        self.assertIsInstance(bands_data, dict)
        for name, b in bands_data.items():
            self.assertIsInstance(b, dict)
            self.assertIn("batting_first_win_percentage", b)
            pct = b["batting_first_win_percentage"]
            pct_disp = f"{pct:.1f}%" if pct is not None else "N/A"
            self.assertTrue(isinstance(pct_disp, str))

    def test_regression_e_venue_consistency(self):
        """TEST E — Selected fixture team1, team2, format, venue, canonical_venue_id remain consistent through analysis."""
        fixtures, _ = get_upcoming_fixtures()
        target_fix = [f for f in fixtures if f.match_id == "cric_sa_aus_odi_3"][0]

        ctx = analyze_match_context(
            team1=target_fix.team1,
            team2=target_fix.team2,
            venue_id=target_fix.canonical_venue_id,
            format=target_fix.format
        )

        self.assertEqual(ctx["team1"], "South Africa")
        self.assertEqual(ctx["team2"], "Australia")
        self.assertEqual(ctx["format"], "ODI")
        self.assertEqual(ctx["venue_id"], "jb_marks_oval")
        self.assertEqual(ctx["canonical_name"], "JB Marks Oval, Potchefstroom")


if __name__ == "__main__":
    unittest.main()
