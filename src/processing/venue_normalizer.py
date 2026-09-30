"""
Venue Normalization Module.
Provides deterministic venue ID normalization and canonical venue metadata mapping using a centralized alias registry.
"""

import json
import re
from pathlib import Path
from typing import Tuple, Dict, Any, List, Optional, Set

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_REGISTRY_PATH = PROJECT_ROOT / "data" / "processed" / "venue_aliases.json"


def _clean_string(val: Optional[str]) -> str:
    """Lowercase, strip whitespace, and normalize repeated spaces."""
    if not val:
        return ""
    val = val.strip().lower()
    val = re.sub(r"\s+", " ", val)
    return val


class VenueRegistry:
    """Singleton/Manager for venue alias resolution."""

    def __init__(self, registry_path: Optional[Path] = None):
        self.registry_path = registry_path or DEFAULT_REGISTRY_PATH
        self.alias_map: Dict[str, Tuple[str, str, Optional[str], Optional[str]]] = {}
        self.canonical_map: Dict[str, Dict[str, Any]] = {}
        self._load_registry()

    def _load_registry(self):
        self.alias_map.clear()
        self.canonical_map.clear()

        raw_data = {}
        if self.registry_path.exists():
            try:
                with open(self.registry_path, "r", encoding="utf-8") as f:
                    raw_data = json.load(f)
            except Exception as e:
                print(f"Warning: Failed to load venue alias registry from {self.registry_path}: {e}")

        for venue_id, data in raw_data.items():
            canonical_name = data.get("canonical_name", venue_id)
            city = data.get("city")
            country = data.get("country")
            aliases = data.get("aliases", [])

            entry = {
                "canonical_venue_id": venue_id,
                "canonical_name": canonical_name,
                "city": city,
                "country": country,
                "aliases": aliases
            }
            self.canonical_map[venue_id] = entry

            # Map canonical ID itself
            self.alias_map[_clean_string(venue_id)] = (venue_id, canonical_name, city, country)
            # Map canonical name
            self.alias_map[_clean_string(canonical_name)] = (venue_id, canonical_name, city, country)

            # Map all aliases
            for alias in aliases:
                self.alias_map[_clean_string(alias)] = (venue_id, canonical_name, city, country)

    def get_canonical_info(
        self, raw_name: Optional[str], city: Optional[str] = None
    ) -> Tuple[str, str, Optional[str], Optional[str]]:
        """
        Pipeline:
        RAW VENUE NAME -> normalize_venue_name() -> alias resolution -> CANONICAL VENUE ID -> CANONICAL DISPLAY NAME
        """
        if not raw_name or not raw_name.strip():
            return "unknown_venue", "Unknown Venue", city, None

        cleaned_raw = _clean_string(raw_name)

        # 1. Direct match in alias map
        if cleaned_raw in self.alias_map:
            v_id, c_name, c_city, c_country = self.alias_map[cleaned_raw]
            return v_id, c_name, c_city or city, c_country

        # 2. Check base name if raw_name contains commas
        base_name = raw_name.strip()
        extracted_city = city

        if "," in raw_name:
            parts = [p.strip() for p in raw_name.split(",")]
            base_name = parts[0]
            if not extracted_city and len(parts) > 1:
                extracted_city = parts[1]

            cleaned_base = _clean_string(base_name)
            if cleaned_base in self.alias_map:
                v_id, c_name, c_city, c_country = self.alias_map[cleaned_base]
                return v_id, c_name, c_city or extracted_city, c_country

        # 3. Level 1 Deterministic Fallback for unregistered venues
        cleaned_base = _clean_string(base_name)
        slug_base = re.sub(r"[^\w\s]", "", cleaned_base)
        slug_base = re.sub(r"\s+", "_", slug_base.strip())

        eff_city = extracted_city or city
        if eff_city and eff_city.strip():
            cleaned_city = _clean_string(eff_city)
            slug_city = re.sub(r"[^\w\s]", "", cleaned_city)
            slug_city = re.sub(r"\s+", "_", slug_city.strip())
            if slug_city not in slug_base:
                venue_id = f"{slug_base}_{slug_city}"
            else:
                venue_id = slug_base
        else:
            venue_id = slug_base

        canonical_name = base_name
        return venue_id, canonical_name, eff_city, None

    def get_aliases(self, venue_id_or_name: str) -> List[str]:
        """Returns list of all raw aliases for a canonical venue ID or raw name."""
        info = self.get_canonical_info(venue_id_or_name)
        v_id = info[0]
        if v_id in self.canonical_map:
            return self.canonical_map[v_id]["aliases"]
        return [venue_id_or_name]


# Module-level registry singleton
_REGISTRY_INSTANCE = VenueRegistry()


def reload_registry():
    """Reloads the global venue registry from disk."""
    _REGISTRY_INSTANCE._load_registry()


def normalize_venue(raw_name: Optional[str], city: Optional[str] = None) -> str:
    """Returns stable canonical_venue_id for raw venue string."""
    v_id, _, _, _ = _REGISTRY_INSTANCE.get_canonical_info(raw_name, city)
    return v_id


def get_canonical_venue_info(
    raw_name: Optional[str], city: Optional[str] = None
) -> Tuple[str, str, Optional[str], Optional[str]]:
    """Returns (canonical_venue_id, canonical_display_name, city, country)."""
    return _REGISTRY_INSTANCE.get_canonical_info(raw_name, city)


def get_venue_aliases(venue_id_or_name: str) -> List[str]:
    """Returns all known aliases for a venue."""
    return _REGISTRY_INSTANCE.get_aliases(venue_id_or_name)


def resolve_venue_search(search_term: str) -> Optional[Dict[str, Any]]:
    """Resolves search text to a canonical venue object if matched."""
    if not search_term:
        return None
    cleaned = _clean_string(search_term)
    if cleaned in _REGISTRY_INSTANCE.alias_map:
        v_id, c_name, c_city, c_country = _REGISTRY_INSTANCE.alias_map[cleaned]
        return {
            "canonical_venue_id": v_id,
            "canonical_name": c_name,
            "city": c_city,
            "country": c_country
        }
    return None
