import csv
import json
import os
import sys
import time
import requests
from dotenv import load_dotenv

load_dotenv()

# --- Configuration ---
CLIENT_ID = os.environ["USPS_CLIENT_ID"]
CLIENT_SECRET = os.environ["USPS_CLIENT_SECRET"]

INPUT_FILE = "petition_signers.csv"
OUTPUT_FILE = "petition_signers_validated.csv"

TOKEN_URL = "https://apis.usps.com/oauth2/v3/token"
ADDRESS_URL = "https://apis.usps.com/addresses/v3/address"

ADDED_HEADERS = [
    "usps_street", "usps_city", "usps_state", "usps_zip", "usps_zip4",
    "usps_valid", "usps_notes",
]


def get_token():
    resp = requests.post(TOKEN_URL, json={
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "client_credentials",
    })
    resp.raise_for_status()
    return resp.json()["access_token"]


def clean_city(city):
    # OCR sometimes produces "Madison, WI" or "Madison WI 53714" in the city field
    import re
    city = city.strip().rstrip(",")
    # Strip trailing state abbreviation (e.g. ", WI" or " WI")
    city = re.sub(r"[,\s]+[A-Z]{2}(\s+\d{5}(-\d{4})?)?$", "", city).strip()
    return city


def validate_address(token, street, city, state, zipcode):
    params = {"streetAddress": street, "city": city, "state": state}
    if zipcode:
        params["ZIPCode"] = str(zipcode)[:5]

    resp = requests.get(ADDRESS_URL, headers={
        "accept": "application/json",
        "authorization": f"Bearer {token}",
    }, params=params, timeout=30)

    if resp.status_code == 200:
        data = resp.json().get("address", {})
        return {
            "usps_street": data.get("streetAddress", ""),
            "usps_city": data.get("city", ""),
            "usps_state": data.get("state", ""),
            "usps_zip": data.get("ZIPCode", ""),
            "usps_zip4": data.get("ZIPPlus4", ""),
            "usps_valid": "yes",
            "usps_notes": "",
        }
    else:
        try:
            detail = resp.json()
        except Exception:
            detail = resp.text
        return {
            "usps_street": "", "usps_city": "", "usps_state": "",
            "usps_zip": "", "usps_zip4": "",
            "usps_valid": "no",
            "usps_notes": str(detail),
        }


def test_single():
    print("Getting token...")
    token = get_token()
    print(f"Token OK: {token[:20]}...")

    print("\nValidating test address: 2 E Mifflin St, Madison WI 53703")
    result = validate_address(token, "2 E Mifflin St", "Madison", "WI", "53703")
    print(json.dumps(result, indent=2))


def main():
    print("Getting token...")
    token = get_token()
    print("Token OK\n")

    with open(INPUT_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        input_headers = reader.fieldnames
        rows = list(reader)

    output_headers = input_headers + ADDED_HEADERS

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=output_headers)
        writer.writeheader()

        for i, row in enumerate(rows):
            street = row.get("street_address", "")
            city = clean_city(row.get("city", ""))
            zipcode = row.get("zip", "").strip()[:5]

            print(f"  [{i+1}/{len(rows)}] {row.get('print_name')} | {street}, {city} {zipcode}...", end=" ", flush=True)

            if not street or not city:
                result = {k: "" for k in ADDED_HEADERS}
                result["usps_valid"] = "skipped"
                result["usps_notes"] = "missing street or city"
            else:
                result = validate_address(token, street, city, "WI", zipcode)
                time.sleep(0.25)

            print(result["usps_valid"])
            writer.writerow({**row, **result})

    print(f"\nSaved to {OUTPUT_FILE}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        test_single()
    else:
        main()
