# Cricket Venue Analytics

A high-performance cricket venue analytics application for international ODI and T20I matches, powered by Cricsheet historical data, SQLite, CricAPI fixture integration, and Streamlit.

---

## Project Purpose
The purpose of this project is to provide statistical venue-level insights (such as average first/second innings scores, toss win vs match win correlations, chasing vs defending win rates, and head-to-head venue trends) for international ODI and T20I cricket matches, and automatically map upcoming international fixtures to historical venue records.

---

## Stage 5: Automatic Upcoming Match Integration

### API Provider & Environment Setup
- **Provider**: CricAPI (`https://api.cricapi.com/v1/matches`)
- **API Key Configuration**: Environment variable `CRICKET_API_KEY` (configured in `.env`).
- **Cache TTL Configuration**: `FIXTURE_CACHE_TTL_HOURS=6` (default 6 hours).

To configure your API key, copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
And add your key:
```env
CRICKET_API_KEY=your_cricapi_key_here
FIXTURE_CACHE_TTL_HOURS=6
```

### Rate-Limit Protection & Caching Architecture
- **Cache Location**: `data/processed/upcoming_fixtures.json`
- **Zero API Requests**: Normal UI browsing (changing venue, format, historical window, tabs, or clicking "ANALYZE MATCH") executes **0 API requests**.
- **Max 1 API Request**: Triggered only when the 6-hour cache expires or when the user explicitly clicks the `[ 🔄 Refresh Matches ]` button.
- **Error Resilience**: If CricAPI fails (401, 403, 429 rate limit, 5xx, or network error), the application preserves the previous cache without deleting data and displays a non-intrusive status warning.

### Automatic Match Filtering
- **Included**: Retains ONLY Men's International ODI and Men's International T20I upcoming matches.
- **Excluded**: Test matches, T10, domestic competitions, franchise leagues (IPL, BBL, PSL, CPL, ILT20, SA20, MLC, Super Smash, etc.), Women's matches, completed, abandoned, or cancelled games.
- **Sorting**: Matches are sorted chronologically from earliest to latest.

### Venue Resolution Pipeline (`resolve_fixture_venue`)
Matches upcoming fixture venue names to historical database venue IDs using a 5-tier resolution hierarchy:
1. Exact match with `canonical_name` in DB `venues` table.
2. Exact match with `venue_raw` or `raw_name_examples` JSON list in DB `venues` table.
3. Existing deterministic alias in `KNOWN_VENUE_MAPPINGS` matching DB `venue_id`.
4. Normalized venue ID + city matching DB `venue_id`.
5. Fallback: If unresolved, displays warning and allows manual venue selection in sidebar.

---

## Database Schema Overview

* **`matches`**: Match metadata, teams, toss, venue_raw, venue_id, format (`ODI`/`T20I`), winner, result_type, win_margin, method (`D/L`).
* **`innings`**: Innings scores (`total_runs`), wickets, overs, balls_delivered, target_runs, innings_number.
* **`venues`**: Canonical venue registry, city, country, match counts per format.

---

## Command Reference

1. **Build Historical Database** (Stage 2):
   ```bash
   python scripts/build_database.py
   ```
2. **Validate Database** (Stage 2):
   ```bash
   python scripts/validate_database.py
   ```
3. **Run All Unit Tests** (Stage 2-5):
   ```bash
   python -m unittest discover tests
   ```
4. **Run Analytics Demo Script** (Stage 3):
   ```bash
   python scripts/test_venue_analysis.py
   ```
5. **Launch Interactive Streamlit Dashboard** (Stage 4 & 5):
   ```bash
   streamlit run app/streamlit_app.py
   ```
