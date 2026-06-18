import csv
import json
import sys
import time
import requests
from pathlib import Path
from shapely.geometry import shape, Point

GEOJSON_FILE = "district76.geojson"
INPUT_FILE = "petition_signers_validated.csv"
OUTPUT_FILE = "petition_signers_geofenced.csv"

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_HEADERS = {"User-Agent": "zoe-canvassing-district76-check"}


def load_district():
    with open(GEOJSON_FILE) as f:
        gj = json.load(f)
    geometries = [shape(feat["geometry"]) for feat in gj["features"]]
    # Union all features in case the district is multi-part
    if len(geometries) == 1:
        return geometries[0]
    from shapely.ops import unary_union
    return unary_union(geometries)


def geocode(street, city, state, zipcode):
    query = f"{street}, {city}, {state} {zipcode}"
    resp = requests.get(NOMINATIM_URL, params={
        "q": query,
        "format": "json",
        "limit": 1,
        "countrycodes": "us",
    }, headers=NOMINATIM_HEADERS, timeout=15)
    resp.raise_for_status()
    results = resp.json()
    if results:
        return float(results[0]["lat"]), float(results[0]["lon"])
    return None, None


def main():
    district = load_district()
    print(f"Loaded district geometry from {GEOJSON_FILE}")

    with open(INPUT_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        input_headers = reader.fieldnames
        rows = list(reader)

    output_headers = input_headers + ["latitude", "longitude", "in_district"]

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=output_headers)
        writer.writeheader()

        for i, row in enumerate(rows):
            # Prefer USPS-standardized address if available
            street = row.get("usps_street") or row.get("street_address", "")
            city = row.get("usps_city") or row.get("city", "")
            state = row.get("usps_state") or "WI"
            zipcode = row.get("usps_zip") or row.get("zip", "")
            name = row.get("print_name", "(unknown)")

            print(f"  [{i+1}/{len(rows)}] {name} | {street}, {city} {zipcode}...", end=" ", flush=True)

            if not street or not city:
                print("skipped (no address)")
                writer.writerow({**row, "latitude": "", "longitude": "", "in_district": "unknown"})
                continue

            lat, lon = geocode(street, city, state, zipcode)
            time.sleep(1.1)  # Nominatim rate limit: 1 req/sec

            if lat is None:
                print("geocode failed")
                writer.writerow({**row, "latitude": "", "longitude": "", "in_district": "unknown"})
                continue

            point = Point(lon, lat)
            in_district = "yes" if district.contains(point) else "no"
            print(f"{'IN' if in_district == 'yes' else 'OUT'} ({lat:.5f}, {lon:.5f})")
            writer.writerow({**row, "latitude": lat, "longitude": lon, "in_district": in_district})

    print(f"\nSaved to {OUTPUT_FILE}")

    # Summary
    with open(OUTPUT_FILE, newline="", encoding="utf-8") as f:
        results = list(csv.DictReader(f))
    yes = sum(1 for r in results if r["in_district"] == "yes")
    no = sum(1 for r in results if r["in_district"] == "no")
    unk = sum(1 for r in results if r["in_district"] == "unknown")
    print(f"  In district:     {yes}")
    print(f"  Out of district: {no}")
    print(f"  Unknown:         {unk}")


def test_single():
    district = load_district()
    print(f"Loaded district geometry\n")

    # Sample known-good address for a smoke test of the geocode/contains pipeline
    street, city, state, zipcode = "2 E MIFFLIN ST", "MADISON", "WI", "53703"
    print(f"Geocoding: {street}, {city} {zipcode}")
    lat, lon = geocode(street, city, state, zipcode)
    if lat is None:
        print("Geocode failed")
        return
    print(f"Coordinates: {lat}, {lon}")
    point = Point(lon, lat)
    print(f"In district 76: {district.contains(point)}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        test_single()
    else:
        main()
