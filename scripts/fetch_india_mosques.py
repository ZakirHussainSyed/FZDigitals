#!/usr/bin/env python3
"""
Download mosques from OpenStreetMap for India and save to JSON.
Uses Geofabrik India extract + osmium (Overpass is dead/406).
Run this script locally to refresh the mosque data.
Usage: python scripts/fetch_india_mosques.py
"""

import urllib.request
import json
import hashlib
import subprocess
import os
from datetime import datetime

# India bounding box
INDIA_S, INDIA_W = 6.5, 68.0
INDIA_N, INDIA_E = 37.0, 97.0

# Geofabrik India extract URL
GEOFABRIK_URL = 'https://download.geofabrik.de/asia/india-latest.osm.pbf'
PBF_PATH = '/tmp/india-latest.osm.pbf'
FILTERED_PBF = '/tmp/pow.osm.pbf'
GEOJSONSEQ = '/tmp/pow.geojsonseq'
OUTPUT_FILE = 'slideshow/static/india_mosques.json'


def download_pbf():
    """Download the India Geofabrik extract if not present or outdated."""
    if os.path.exists(PBF_PATH):
        size = os.path.getsize(PBF_PATH)
        # Expected size is ~1.7GB; if too small, redownload
        if size > 1_500_000_000:
            print(f"Using existing PBF ({size} bytes)")
            return
    
    print(f"Downloading {GEOFABRIK_URL} to {PBF_PATH}...")
    urllib.request.urlretrieve(GEOFABRIK_URL, PBF_PATH)
    print(f"Downloaded {os.path.getsize(PBF_PATH)} bytes")


def filter_place_of_worship():
    """Filter for place_of_worship using osmium."""
    print("Filtering place_of_worship elements...")
    cmd = [
        'osmium', 'tags-filter',
        PBF_PATH, 'a/amenity=place_of_worship',
        '-o', FILTERED_PBF,
        '--overwrite'
    ]
    subprocess.run(cmd, check=True)
    print(f"Filtered PBF size: {os.path.getsize(FILTERED_PBF)} bytes")


def export_geojsonseq():
    """Export to GeoJSONSeq with point/linestring/polygon geometry."""
    print("Exporting to GeoJSONSeq...")
    cmd = [
        'osmium', 'export',
        FILTERED_PBF,
        '-o', GEOJSONSEQ,
        '--geometry-types=point,linestring,polygon',
        '--output-format=geojsonseq',
        '--overwrite'
    ]
    subprocess.run(cmd, check=True)
    print(f"GeoJSONSeq size: {os.path.getsize(GEOJSONSEQ)} bytes")


def parse_geojsonseq():
    """Parse GeoJSONSeq and extract Muslim mosques."""
    print("Parsing GeoJSONSeq and filtering Muslim mosques...")
    mosques = []
    seen = set()
    
    with open(GEOJSONSEQ, 'r') as f:
        for line in f:
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            
            props = obj.get('properties', {})
            religion = props.get('religion')
            if religion != 'muslim':
                continue
            
            # Get coordinates
            geom = obj.get('geometry', {})
            geom_type = geom.get('type')
            coords = geom.get('coordinates')
            
            lat, lon = None, None
            if geom_type == 'Point' and coords:
                lon, lat = coords
            elif geom_type in ('LineString', 'Polygon') and coords:
                # Calculate centroid
                flat = []
                if geom_type == 'LineString':
                    flat = coords
                elif geom_type == 'Polygon':
                    flat = coords[0] if coords else []
                if flat:
                    lat = sum(c[1] for c in flat) / len(flat)
                    lon = sum(c[0] for c in flat) / len(flat)
            
            if lat is None or lon is None:
                continue
            
            # India bounds check
            if not (INDIA_S <= lat <= INDIA_N and INDIA_W <= lon <= INDIA_E):
                continue
            
            raw_name = props.get('name') or props.get('name:en') or 'Mosque'
            # Truncate to 2 words (phrases) for long names
            name = ' '.join(raw_name.split()[:2])
            address = props.get('addr:full') or props.get('addr:city') or ''
            
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
    download_pbf()
    filter_place_of_worship()
    export_geojsonseq()
    mosques = parse_geojsonseq()
    if mosques:
        save_json(mosques)
        print("Done!")
    else:
        print("No mosques extracted")
