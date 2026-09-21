"""Geocoding + timezone lookup for mosque onboarding.

Uses Nominatim (OpenStreetMap) — the same service the public map page
queries from the browser — so no API key is needed. timezonefinder is an
optional dependency: if it isn't installed, timezone lookup just returns
None and the field stays manual.
"""

import logging

import requests

logger = logging.getLogger(__name__)

NOMINATIM_URL = 'https://nominatim.openstreetmap.org/search'


def geocode_address(address):
    """Resolve a street address to (lat, lon) floats, or None."""
    if not address:
        return None
    try:
        resp = requests.get(
            NOMINATIM_URL,
            params={'format': 'json', 'q': address, 'limit': 1},
            headers={'User-Agent': 'FZDigitals/1.0'},
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json()
        if not results:
            return None
        # 8 decimals ≈ 1mm precision — plenty for a map pin, keeps values clean
        return round(float(results[0]['lat']), 8), round(float(results[0]['lon']), 8)
    except Exception as e:
        logger.warning(f'Geocode failed for "{address}": {e}')
        return None


def timezone_for_coords(latitude, longitude):
    """Resolve coordinates to an IANA timezone name, or None."""
    try:
        from timezonefinder import TimezoneFinder
    except ImportError:
        return None
    try:
        return TimezoneFinder().timezone_at(lat=float(latitude), lng=float(longitude))
    except Exception as e:
        logger.warning(f'Timezone lookup failed for {latitude},{longitude}: {e}')
        return None
