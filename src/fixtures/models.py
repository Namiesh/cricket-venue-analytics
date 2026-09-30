"""
Upcoming Fixtures Data Models with IST Timezone Formatting and Canonical Venue Normalization.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
from src.processing.venue_normalizer import get_canonical_venue_info


@dataclass
class UpcomingFixture:
    match_id: str
    team1: str
    team2: str
    format: str  # "ODI" or "T20I"
    venue: str  # Kept for backward compatibility (same as raw_venue_name)
    raw_venue_name: str = ""
    canonical_venue_id: str = ""
    canonical_display_name: str = ""
    city: Optional[str] = None
    country: Optional[str] = None
    scheduled_datetime: str = ""  # ISO/UTC datetime string
    status: str = "upcoming"
    series: Optional[str] = None
    resolved_venue_id: Optional[str] = None
    raw_data: Optional[Dict[str, Any]] = field(default_factory=dict)

    def __post_init__(self):
        if not self.raw_venue_name:
            self.raw_venue_name = self.venue or ""
        if not self.venue:
            self.venue = self.raw_venue_name

        v_id, c_display_name, c_city, c_country = get_canonical_venue_info(self.raw_venue_name or self.venue, self.city)

        if not self.canonical_venue_id:
            self.canonical_venue_id = self.resolved_venue_id or v_id
        if not self.resolved_venue_id:
            self.resolved_venue_id = self.canonical_venue_id

        if not self.canonical_display_name:
            self.canonical_display_name = c_display_name

        if not self.city:
            self.city = c_city
        if not self.country:
            self.country = c_country

    def formatted_ist_datetime(self) -> str:
        """Converts UTC scheduled_datetime to formatted Asia/Kolkata (IST) string."""
        if not self.scheduled_datetime:
            return "Date TBD"
        try:
            dt_str = self.scheduled_datetime.replace("Z", "+00:00")
            if "T" in dt_str:
                dt_utc = datetime.fromisoformat(dt_str)
            else:
                dt_utc = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")

            if dt_utc.tzinfo is None:
                dt_utc = dt_utc.replace(tzinfo=timezone.utc)

            ist_tz = timezone(timedelta(hours=5, minutes=30))
            dt_ist = dt_utc.astimezone(ist_tz)

            # Format as DD Month YYYY · H:MM AM/PM IST
            formatted_date = dt_ist.strftime("%d %B %Y · %I:%M %p IST")
            # Clean leading zeros in hour e.g. 02:00 PM -> 2:00 PM
            formatted_date = formatted_date.replace(" 0", " ")
            return formatted_date
        except Exception:
            return self.scheduled_datetime

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["raw_venue_name"] = self.raw_venue_name
        d["canonical_venue_id"] = self.canonical_venue_id
        d["canonical_display_name"] = self.canonical_display_name
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "UpcomingFixture":
        raw_v = d.get("raw_venue_name") or d.get("venue", "")
        c_id = d.get("canonical_venue_id") or d.get("resolved_venue_id") or ""
        c_name = d.get("canonical_display_name") or ""
        return cls(
            match_id=str(d.get("match_id", "")),
            team1=str(d.get("team1", "")),
            team2=str(d.get("team2", "")),
            format=str(d.get("format", "ODI")),
            venue=str(d.get("venue", raw_v)),
            raw_venue_name=str(raw_v),
            canonical_venue_id=str(c_id),
            canonical_display_name=str(c_name),
            city=d.get("city"),
            country=d.get("country"),
            scheduled_datetime=str(d.get("scheduled_datetime", "")),
            status=str(d.get("status", "upcoming")),
            series=d.get("series"),
            resolved_venue_id=str(c_id) if c_id else d.get("resolved_venue_id"),
            raw_data=d.get("raw_data", {}),
        )
