"""Geocoding + timezone lookup for mosque onboarding.

Uses Nominatim (OpenStreetMap) — the same service the public map page
queries from the browser — so no API key is needed. timezonefinder is an
optional dependency: if it isn't installed, timezone lookup just returns
None and the field stays manual.
"""

import logging
import re

import requests

logger = logging.getLogger(__name__)

NOMINATIM_URL = 'https://nominatim.openstreetmap.org/search'
NOMINATIM_REVERSE_URL = 'https://nominatim.openstreetmap.org/reverse'

# Coordinate patterns found in Google Maps links:
#   .../@47.6102,-122.1438,17z      (place/share URLs)
#   ?q=47.6102,-122.1438            (query links)
#   !3d47.6102!4d-122.1438          (embed/data URLs)
_GMAPS_PATTERNS = (
    re.compile(r'!3d(-?\d+(?:\.\d+)?)!4d(-?\d+(?:\.\d+)?)'),
    re.compile(r'@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)'),
    re.compile(r'[?&](?:q|query|ll)=(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)'),
)


def parse_google_maps_url(url):
    """Extract (lat, lng) floats from a Google Maps link, or None.

    Handles full share links and short maps.app.goo.gl / goo.gl links
    (resolved by following the redirect).
    """
    if not url:
        return None
    url = url.strip()
    for pattern in _GMAPS_PATTERNS:
        m = pattern.search(url)
        if m:
            return float(m.group(1)), float(m.group(2))
    if 'goo.gl' in url:
        try:
            resp = requests.get(
                url,
                headers={'User-Agent': 'FZDigitals/1.0'},
                timeout=10,
                allow_redirects=True,
            )
            for pattern in _GMAPS_PATTERNS:
                m = pattern.search(resp.url)
                if m:
                    return float(m.group(1)), float(m.group(2))
        except Exception as e:
            logger.warning(f'Could not resolve short maps link "{url}": {e}')
    return None


def reverse_geocode(latitude, longitude):
    """Resolve (lat, lng) to a display address string, or None."""
    try:
        resp = requests.get(
            NOMINATIM_REVERSE_URL,
            params={'format': 'json', 'lat': latitude, 'lon': longitude},
            headers={'User-Agent': 'FZDigitals/1.0'},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get('display_name')
    except Exception as e:
        logger.warning(f'Reverse geocode failed for {latitude},{longitude}: {e}')
        return None


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
    """Resolve coordinates to an IANA timezone name, or None.

    Uses timezonefinder when installed; falls back to a timeapi.io lookup
    so deployments without the package still get correct timezones.
    """
    try:
        from timezonefinder import TimezoneFinder
        return TimezoneFinder().timezone_at(lat=float(latitude), lng=float(longitude))
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f'Timezone lookup failed for {latitude},{longitude}: {e}')
        return None
    try:
        resp = requests.get(
            'https://timeapi.io/api/timezone/coordinate',
            params={'latitude': float(latitude), 'longitude': float(longitude)},
            headers={'User-Agent': 'FZDigitals/1.0'},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get('timeZone') or None
    except Exception as e:
        logger.warning(f'Timezone API lookup failed for {latitude},{longitude}: {e}')
        return None
