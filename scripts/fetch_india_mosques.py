#!/usr/bin/env python3
"""
Download mosques from OpenStreetMap for India and save to JSON.
Run this script locally to refresh the mosque data.
Usage: python scripts/fetch_india_mosques.py
"""

import urllib.request
import urllib.parse
import json
import time

# India bounding box
INDIA_S, INDIA_W = 6.5, 68.0
INDIA_N, INDIA_E = 37.0, 97.0

# overpass-api.de is the only public instance covering India — other
# "mirrors" are region-locked (osm.ch = Switzerland only) or down.
# NB: Geofabrik extract + osmium-tool is the reliable path while
# overpass-api.de returns 406; see india_mosques.json provenance.
OVERPASS_HOSTS = [
    'https://overpass-api.de/api/interpreter',
]


def post_overpass(query):
    last_err = None
    for url in OVERPASS_HOSTS:
        try:
            data = urllib.parse.urlencode({'data': query}).encode('utf-8')
            req = urllib.request.Request(
                url,
                data=data,
                headers={
                    'User-Agent': 'FZDigitals Mosque Data Fetcher/1.0',
                    'Content-Type': 'application/x-www-form-urlencoded'
                }
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode('utf-8'))
                last_err = f'{url}: HTTP {resp.status}'
        except Exception as e:
            last_err = f'{url}: {e}'
    raise RuntimeError(f'All Overpass mirrors failed: {last_err}')


def fetch_mosques_for_bbox(s, w, n, e):
    """Fetch mosques for a specific bounding box."""
    query = f'''
[out:json][timeout:60];
(
  node["amenity"="place_of_worship"]["religion"="muslim"]({s},{w},{n},{e});
  way["amenity"="place_of_worship"]["religion"="muslim"]({s},{w},{n},{e});
  relation["amenity"="place_of_worship"]["religion"="muslim"]({s},{w},{n},{e});
);
out center;
'''
    
    try:
        result = post_overpass(query)
        
        mosques = []
        for elem in result.get('elements', []):
            lat = lon = name = address = None
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
            name = tags.get('name') or tags.get('name:en') or 'Mosque'
            address = tags.get('addr:full') or tags.get('addr:city') or ''
            
            mosques.append({
                'id': f"osm_{elem['id']}",
                'name': name,
                'address': address,
                'latitude': lat,
                'longitude': lon,
            })
        
        return mosques
    except Exception as e:
        print(f"  Error for bbox {s},{w},{n},{e}: {e}")
        return []

def fetch_mosques():
    """Fetch mosques from Overpass API for India in chunks."""
    print("Fetching mosques from Overpass API...")
    print(f"Bounding box: {INDIA_S},{INDIA_W},{INDIA_N},{INDIA_E}")
    
    # Split India into 5x5 grid (25 chunks)
    lat_step = (INDIA_N - INDIA_S) / 5
    lon_step = (INDIA_E - INDIA_W) / 5
    
    all_mosques = []
    chunk_num = 0
    
    for i in range(5):
        for j in range(5):
            s = INDIA_S + i * lat_step
            n = INDIA_S + (i + 1) * lat_step
            w = INDIA_W + j * lon_step
            e = INDIA_W + (j + 1) * lon_step
            
            chunk_num += 1
            print(f"Fetching chunk {chunk_num}/25: {s:.2f},{w:.2f},{n:.2f},{e:.2f}")
            
            mosques = fetch_mosques_for_bbox(s, w, n, e)
            all_mosques.extend(mosques)
            
            # Rate limiting: wait 1 second between chunks
            if chunk_num < 25:
                time.sleep(1)
    
    print(f"Total mosques fetched: {len(all_mosques)}")
    return all_mosques

def save_json(mosques, output_file='slideshow/static/india_mosques.json'):
    """Save mosques to JSON file."""
    data = {
        'version': '1.0',
        'fetched_at': None,  # Will be set by the caller
        'count': len(mosques),
        'mosques': mosques
    }
    
    from datetime import datetime
    data['fetched_at'] = datetime.utcnow().isoformat()
    
    with open(output_file, 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"Saved {len(mosques)} mosques to {output_file}")

if __name__ == '__main__':
    mosques = fetch_mosques()
    if mosques:
        save_json(mosques)
        print("Done!")
    else:
        print("No mosques fetched")
