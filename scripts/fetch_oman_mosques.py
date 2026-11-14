#!/usr/bin/env python3
"""
Download mosques from OpenStreetMap for Oman using Overpass API with retries.
Run this script locally to refresh the mosque data.
Usage: python scripts/fetch_oman_mosques.py
"""

import urllib.request
import urllib.parse
import json
import hashlib
import time
import os
from datetime import datetime

# Oman bounding box
OMAN_S, OMAN_W = 16.5, 52.0
OMAN_N, OMAN_E = 26.5, 60.0

OVERPASS_URL = 'https://overpass-api.de/api/interpreter'
OUTPUT_FILE = 'slideshow/static/oman_mosques.json'


def fetch_mosques_from_overpass():
    """Fetch mosques for Oman using Overpass API with retries."""
    query = f'''
[out:json][timeout:60];
(
  node["amenity"="place_of_worship"]["religion"="muslim"]({OMAN_S},{OMAN_W},{OMAN_N},{OMAN_E});
  way["amenity"="place_of_worship"]["religion"="muslim"]({OMAN_S},{OMAN_W},{OMAN_N},{OMAN_E});
  relation["amenity"="place_of_worship"]["religion"="muslim"]({OMAN_S},{OMAN_W},{OMAN_N},{OMAN_E});
);
out center;
'''
    
    print(f"Fetching mosques from Overpass API for Oman bbox: {OMAN_S},{OMAN_W},{OMAN_N},{OMAN_E}")
    
    data = urllib.parse.urlencode({'data': query}).encode('utf-8')
    req = urllib.request.Request(
        OVERPASS_URL,
        data=data,
        headers={
            'User-Agent': 'FZDigitals Mosque Data Fetcher/1.0',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
    )
    
    # Retry logic for Overpass 502 errors
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode('utf-8'))
                else:
                    print(f"Attempt {attempt + 1}: HTTP {resp.status}")
                    if attempt < 4:
                        time.sleep(5)
                    else:
                        raise RuntimeError(f"Overpass returned HTTP {resp.status}")
        except Exception as e:
            print(f"Attempt {attempt + 1}: {e}")
            if attempt < 4:
                time.sleep(5)
            else:
                raise RuntimeError(f"Overpass fetch failed after 5 attempts: {e}")


def parse_overpass_result(result):
    """Parse Overpass result and extract mosque data."""
    mosques = []
    seen = set()
    
    for elem in result.get('elements', []):
        lat = lon = None
        if elem['type'] == 'node':
            lat = elem.get('lat')
            lon = elem.get('lon')
        else:
            center = elem.get('center', {})
            lat = center.get('lat')
            lon = center.get('lon')
        
        if lat is None or lon is None:
            continue
        
        tags = elem.get('tags', {})
        raw_name = tags.get('name') or tags.get('name:en') or 'Mosque'
        # Truncate to 2 words (phrases) for long names
        name = ' '.join(raw_name.split()[:2])
        address = tags.get('addr:full') or tags.get('addr:city') or ''
        
        # Dedup by name+coords (hash-based ID)
        key = f"{name.lower()}_{lat:.6f}_{lon:.6f}"
        if key in seen:
            continue
        seen.add(key)
        
        # Stable ID from hash
        hash_val = hashlib.md5(key.encode()).hexdigest()[:10]
        
        mosques.append({
            'id': f"osm_{hash_val}",
            'name': name,
            'address': address,
            'latitude': lat,
            'longitude': lon,
        })
    
    print(f"Extracted {len(mosques)} mosques from Overpass")
    return mosques


def save_json(mosques, output_file=OUTPUT_FILE):
    """Save mosques to JSON file."""
    data = {
        'version': '1.0',
        'fetched_at': datetime.utcnow().isoformat(),
        'count': len(mosques),
        'mosques': mosques
    }
    
    with open(output_file, 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"Saved {len(mosques)} mosques to {output_file}")
    print(f"JSON size: {os.path.getsize(output_file)} bytes")


if __name__ == '__main__':
    result = fetch_mosques_from_overpass()
    mosques = parse_overpass_result(result)
    if mosques:
        save_json(mosques)
        print("Done!")
    else:
        print("No mosques extracted")
