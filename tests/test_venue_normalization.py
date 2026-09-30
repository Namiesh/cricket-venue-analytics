"""
Unit Tests for Global Venue Normalization Module.
Tests case, whitespace, punctuation, city suffix handling, alias resolution, analytics across aliases, and canonical naming.
"""

import unittest
import sqlite3
import tempfile
import json
from pathlib import Path

from src.processing.venue_normalizer import (
    normalize_venue,
    get_canonical_venue_info,
    get_venue_aliases,
    resolve_venue_search,
    VenueRegistry,
)
from src.analytics.venue_stats import (
    get_recent_matches,
    calculate_venue_summary,
    get_venue_by_name
)
from src.analytics.team_stats import (
    get_team_venue_stats,
    get_head_to_head_stats,
    get_teams_for_venue_format
)


class TestVenueNormalization(unittest.TestCase):

    def test_01_case_normalization(self):
        """Test case normalization."""
        vid1, cname1, _, _ = get_canonical_venue_info("senwes park")
        vid2, cname2, _, _ = get_canonical_venue_info("SENWES PARK")
        self.assertEqual(vid1, "jb_marks_oval")
        self.assertEqual(vid1, vid2)
        self.assertEqual(cname1, "JB Marks Oval, Potchefstroom")

    def test_02_whitespace_normalization(self):
        """Test whitespace leading/trailing/multiple spaces normalization."""
        vid = normalize_venue("  JB   Marks   Oval  ")
        self.assertEqual(vid, "jb_marks_oval")

    def test_03_punctuation_normalization(self):
        """Test punctuation normalization (apostrophes, quotes, etc.)."""
        vid, cname, _, _ = get_canonical_venue_info("Lord's")
        self.assertEqual(vid, "lords_london")
        self.assertEqual(cname, "Lord's, London")

    def test_04_city_suffix_handling(self):
        """Test handling of city suffix appended after commas."""
        vid1, cname1, _, _ = get_canonical_venue_info("JB Marks Oval, Potchefstroom")
        vid2, cname2, _, _ = get_canonical_venue_info("JB Marks Oval")
        self.assertEqual(vid1, "jb_marks_oval")
        self.assertEqual(vid1, vid2)
        self.assertEqual(cname1, cname2)

    def test_05_historical_venue_aliases(self):
        """Test historical venue names resolve to canonical ID."""
        vid_senwes = normalize_venue("Senwes Park")
        vid_sedgars = normalize_venue("Sedgars Park")
        vid_jb = normalize_venue("JB Marks Oval")
        self.assertEqual(vid_senwes, "jb_marks_oval")
        self.assertEqual(vid_sedgars, "jb_marks_oval")
        self.assertEqual(vid_jb, "jb_marks_oval")

    def test_06_sponsor_and_name_changes(self):
        """Test sponsor name changes and renames resolve correctly."""
        # Optus Stadium -> Perth Stadium
        vid_optus = normalize_venue("Optus Stadium")
        vid_perth = normalize_venue("Perth Stadium")
        self.assertEqual(vid_optus, "perth_stadium_perth")
        self.assertEqual(vid_optus, vid_perth)

        # Beausejour Stadium -> Darren Sammy Stadium
        vid_beau = normalize_venue("Beausejour Stadium, Gros Islet")
        vid_ds = normalize_venue("Darren Sammy National Cricket Stadium, Gros Islet")
        self.assertEqual(vid_beau, "darren_sammy_stadium_st_lucia")
        self.assertEqual(vid_beau, vid_ds)

    def test_07_upcoming_api_venue_to_canonical(self):
        """Test upcoming API venue strings resolve to canonical ID and display name."""
        vid, cname, city, country = get_canonical_venue_info("JB Marks Oval", "Potchefstroom")
        self.assertEqual(vid, "jb_marks_oval")
        self.assertEqual(cname, "JB Marks Oval, Potchefstroom")
        self.assertEqual(city, "Potchefstroom")
        self.assertEqual(country, "South Africa")

    def test_08_historical_cricsheet_venue_to_canonical(self):
        """Test historical Cricsheet raw venue strings resolve to canonical ID."""
        vid, cname, _, _ = get_canonical_venue_info("Feroz Shah Kotla, Delhi")
        self.assertEqual(vid, "arun_jaitley_stadium_delhi")
        self.assertEqual(cname, "Arun Jaitley Stadium, Delhi")

    def test_09_same_physical_venue_produces_same_canonical_id(self):
        """Specific test: Senwes Park, JB Marks Oval, JB Marks Oval, Potchefstroom produce same canonical ID."""
        id1 = normalize_venue("Senwes Park")
        id2 = normalize_venue("JB Marks Oval")
        id3 = normalize_venue("JB Marks Oval, Potchefstroom")
        self.assertEqual(id1, id2)
        self.assertEqual(id2, id3)
        self.assertEqual(id1, "jb_marks_oval")

    def test_10_different_venues_do_not_accidentally_merge(self):
        """Test different physical stadiums do not accidentally merge."""
        id_wankhede = normalize_venue("Wankhede Stadium, Mumbai")
        id_brabourne = normalize_venue("Brabourne Stadium, Mumbai")
        self.assertNotEqual(id_wankhede, id_brabourne)

        id_mcg = normalize_venue("Melbourne Cricket Ground")
        id_scg = normalize_venue("Sydney Cricket Ground")
        self.assertNotEqual(id_mcg, id_scg)

    def test_11_unknown_venue_remains_unresolved_safely(self):
        """Test unregistered/unknown venue gets safe deterministic fallback without crashing."""
        vid, cname, city, _ = get_canonical_venue_info("XYZ Completely Unknown Oval", "Atlantis")
        self.assertEqual(vid, "xyz_completely_unknown_oval_atlantis")
        self.assertIn("XYZ Completely Unknown Oval", cname)

    def test_12_analytics_retrieves_historical_matches_across_aliases(self):
        """Test analytics queries retrieve matches stored under different alias names."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            conn = sqlite3.connect(tmp_path)
            conn.execute("""
                CREATE TABLE matches (
                    match_id TEXT PRIMARY KEY, date TEXT, format TEXT, venue_raw TEXT, venue_id TEXT,
                    city TEXT, team1 TEXT, team2 TEXT, winner TEXT, result_type TEXT, win_margin INT,
                    win_margin_type TEXT, method TEXT, gender TEXT, team_type TEXT, season TEXT,
                    toss_winner TEXT, toss_decision TEXT, player_of_match TEXT
                );
            """)
            conn.execute("""
                CREATE TABLE innings (
                    innings_id TEXT PRIMARY KEY, match_id TEXT, innings_number INT, batting_team TEXT,
                    total_runs INT, wickets_lost INT, overs_completed REAL, balls_delivered INT,
                    is_completed INT, target_runs INT, result_context TEXT
                );
            """)
            conn.execute("""
                CREATE TABLE venues (
                    venue_id TEXT PRIMARY KEY, canonical_name TEXT, city TEXT, country TEXT,
                    raw_name_examples TEXT, match_count_odi INT, match_count_t20i INT
                );
            """)

            # Insert 2 matches: one recorded as "Senwes Park", one as "JB Marks Oval"
            conn.execute("""
                INSERT INTO matches (match_id, date, format, venue_raw, venue_id, team1, team2, winner, result_type)
                VALUES ('m1', '2020-01-01', 'ODI', 'Senwes Park', 'jb_marks_oval', 'South Africa', 'Australia', 'South Africa', 'normal');
            """)
            conn.execute("""
                INSERT INTO matches (match_id, date, format, venue_raw, venue_id, team1, team2, winner, result_type)
                VALUES ('m2', '2022-01-01', 'ODI', 'JB Marks Oval', 'jb_marks_oval', 'South Africa', 'India', 'India', 'normal');
            """)
            conn.execute("""
                INSERT INTO innings (innings_id, match_id, innings_number, batting_team, total_runs, wickets_lost)
                VALUES ('i1_1', 'm1', 1, 'South Africa', 270, 7), ('i1_2', 'm1', 2, 'Australia', 250, 10),
                       ('i2_1', 'm2', 1, 'South Africa', 240, 8), ('i2_2', 'm2', 2, 'India', 243, 4);
            """)
            conn.execute("""
                INSERT INTO venues (venue_id, canonical_name, city, country, match_count_odi)
                VALUES ('jb_marks_oval', 'JB Marks Oval, Potchefstroom', 'Potchefstroom', 'South Africa', 2);
            """)
            conn.commit()
            conn.close()

            # Query via alias "Senwes Park"
            matches_senwes, meta_senwes = get_recent_matches("Senwes Park", "ODI", db_path=tmp_path)
            self.assertEqual(len(matches_senwes), 2)

            # Query via canonical ID "jb_marks_oval"
            matches_jb, meta_jb = get_recent_matches("jb_marks_oval", "ODI", db_path=tmp_path)
            self.assertEqual(len(matches_jb), 2)

            summary = calculate_venue_summary("Senwes Park", "ODI", db_path=tmp_path)
            self.assertEqual(summary["canonical_name"], "JB Marks Oval, Potchefstroom")
            self.assertEqual(summary["actual_match_count"], 2)

        finally:
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except OSError:
                pass

    def test_13_ui_displays_only_canonical_name(self):
        """Test canonical display name is formatted without redundant legacy slashes or combo strings."""
        info = resolve_venue_search("Senwes Park")
        self.assertIsNotNone(info)
        self.assertEqual(info["canonical_name"], "JB Marks Oval, Potchefstroom")
        self.assertNotIn("/", info["canonical_name"])
        self.assertNotIn("formerly", info["canonical_name"])


if __name__ == "__main__":
    unittest.main()
