"""
Database Manager Module for SQLite database operations.
"""

import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Tuple


class DatabaseManager:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def create_tables(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # matches table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS matches (
                match_id TEXT PRIMARY KEY,
                date TEXT,
                format TEXT NOT NULL,
                gender TEXT,
                team_type TEXT,
                venue_raw TEXT,
                venue_id TEXT NOT NULL,
                city TEXT,
                season TEXT,
                team1 TEXT,
                team2 TEXT,
                toss_winner TEXT,
                toss_decision TEXT,
                winner TEXT,
                result_type TEXT,
                win_margin INTEGER,
                win_margin_type TEXT,
                method TEXT,
                player_of_match TEXT
            );
            """)

            # innings table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS innings (
                innings_id TEXT PRIMARY KEY,
                match_id TEXT NOT NULL,
                innings_number INTEGER NOT NULL,
                batting_team TEXT,
                total_runs INTEGER,
                wickets_lost INTEGER,
                overs_completed REAL,
                balls_delivered INTEGER,
                is_completed INTEGER,
                target_runs INTEGER,
                result_context TEXT,
                FOREIGN KEY (match_id) REFERENCES matches (match_id) ON DELETE CASCADE
            );
            """)

            # venues table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS venues (
                venue_id TEXT PRIMARY KEY,
                canonical_name TEXT NOT NULL,
                city TEXT,
                country TEXT,
                raw_name_examples TEXT,
                match_count_odi INTEGER DEFAULT 0,
                match_count_t20i INTEGER DEFAULT 0
            );
            """)

            # indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_matches_format ON matches(format);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_matches_venue_id ON matches(venue_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_matches_date ON matches(date);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_matches_format_venue_date ON matches(format, venue_id, date);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_innings_match_id ON innings(match_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_innings_match_innings ON innings(match_id, innings_number);")

            conn.commit()

    def insert_matches_batch(self, matches: List[Dict[str, Any]]):
        if not matches:
            return
        query = """
        INSERT OR REPLACE INTO matches (
            match_id, date, format, gender, team_type, venue_raw, venue_id, city, season,
            team1, team2, toss_winner, toss_decision, winner, result_type, win_margin,
            win_margin_type, method, player_of_match
        ) VALUES (
            :match_id, :date, :format, :gender, :team_type, :venue_raw, :venue_id, :city, :season,
            :team1, :team2, :toss_winner, :toss_decision, :winner, :result_type, :win_margin,
            :win_margin_type, :method, :player_of_match
        );
        """
        with self.get_connection() as conn:
            conn.executemany(query, matches)
            conn.commit()

    def insert_innings_batch(self, innings: List[Dict[str, Any]]):
        if not innings:
            return
        query = """
        INSERT OR REPLACE INTO innings (
            innings_id, match_id, innings_number, batting_team, total_runs, wickets_lost,
            overs_completed, balls_delivered, is_completed, target_runs, result_context
        ) VALUES (
            :innings_id, :match_id, :innings_number, :batting_team, :total_runs, :wickets_lost,
            :overs_completed, :balls_delivered, :is_completed, :target_runs, :result_context
        );
        """
        with self.get_connection() as conn:
            conn.executemany(query, innings)
            conn.commit()

    def insert_venues_batch(self, venues: List[Dict[str, Any]]):
        if not venues:
            return
        query = """
        INSERT OR REPLACE INTO venues (
            venue_id, canonical_name, city, country, raw_name_examples, match_count_odi, match_count_t20i
        ) VALUES (
            :venue_id, :canonical_name, :city, :country, :raw_name_examples, :match_count_odi, :match_count_t20i
        );
        """
        with self.get_connection() as conn:
            conn.executemany(query, venues)
            conn.commit()
