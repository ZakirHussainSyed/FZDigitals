#!/usr/bin/env python3
"""
Download mosques from OpenStreetMap for USA West Coast (WA, OR, CA) and save to JSON.
Uses Overpass API with retries.
Run this script locally to refresh the mosque data.
Usage: python scripts/fetch_usa_west_coast_mosques.py
"""

import urllib.request
import urllib.parse
import json
import hashlib
import time
import os
from datetime import datetime

# USA West Coast bounding box (Washington, Oregon, California)
# Split into smaller chunks to avoid Overpass timeout
USA_S, USA_W = 32.0, -124.0
USA_N, USA_E = 49.0, -114.0

OVERPASS_URL = 'https://overpass-api.de/api/interpreter'
OUTPUT_FILE = 'slideshow/static/usa_west_coast_mosques.json'


def fetch_mosques_from_overpass():
    """Fetch mosques for USA West Coast using Overpass API with retries, split into chunks."""
    # Split into 4 chunks to avoid timeout
    lat_step = (USA_N - USA_S) / 2
    lon_step = (USA_E - USA_W) / 2
    
    all_mosques = []
    seen = set()
    
    for i in range(2):
        for j in range(2):
            s = USA_S + i * lat_step
            n = USA_S + (i + 1) * lat_step
            w = USA_W + j * lon_step
            e = USA_W + (j + 1) * lon_step
            
            query = f'''
[out:json][timeout:90];
(
  node["amenity"="place_of_worship"]["religion"="muslim"]({s},{w},{n},{e});
  way["amenity"="place_of_worship"]["religion"="muslim"]({s},{w},{n},{e});
  relation["amenity"="place_of_worship"]["religion"="muslim"]({s},{w},{n},{e});
);
out center;
'''
            
            print(f"Fetching chunk {i*2 + j + 1}/4: {s:.2f},{w:.2f},{n:.2f},{e:.2f}")
            
            data = urllib.parse.urlencode({'data': query}).encode('utf-8')
            req = urllib.request.Request(
                OVERPASS_URL,
                data=data,
                headers={
                    'User-Agent': 'FZDigitals Mosque Data Fetcher/1.0',
                    'Content-Type': 'application/x-www-form-urlencoded'
                }
            )
            
            # Retry logic for each chunk
            for attempt in range(3):
                try:
                    with urllib.request.urlopen(req, timeout=120) as resp:
                        if resp.status == 200:
                            result = json.loads(resp.read().decode('utf-8'))
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
                                name = ' '.join(raw_name.split()[:2])
                                address = tags.get('addr:full') or tags.get('addr:city') or tags.get('addr:state') or ''
                                
                                key = f"{name.lower()}_{lat:.6f}_{lon:.6f}"
                                if key in seen:
                                    continue
                                seen.add(key)
                                
                                hash_val = hashlib.md5(key.encode()).hexdigest()[:10]
                                
                                all_mosques.append({
                                    'id': f"osm_{hash_val}",
                                    'name': name,
                                    'address': address,
                                    'latitude': lat,
                                    'longitude': lon,
                                })
                            print(f"  Chunk {i*2 + j + 1}: {len(result.get('elements', []))} elements, total so far: {len(all_mosques)}")
                            break
                        else:
                            print(f"  Chunk {i*2 + j + 1}: HTTP {resp.status}")
                            if attempt < 2:
                                time.sleep(3)
                            else:
                                print(f"  Chunk {i*2 + j + 1}: Skipping due to errors")
                except Exception as e:
                    print(f"  Chunk {i*2 + j + 1}: Error: {e}")
                    if attempt < 2:
                        time.sleep(3)
                    else:
                        print(f"  Chunk {i*2 + j + 1}: Skipping due to errors")
            
            time.sleep(2)  # Rate limiting between chunks
    
    print(f"Total mosques extracted: {len(all_mosques)}")
    return all_mosques


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
        address = tags.get('addr:full') or tags.get('addr:city') or tags.get('addr:state') or ''
        
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
    
    print(f"Extracted {len(mosques)} Muslim mosques")
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
    mosques = fetch_mosques_from_overpass()
    if mosques:
        save_json(mosques)
        print("Done!")
    else:
        print("No mosques extracted")
