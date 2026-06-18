# Petition Signature Validator

Pipeline for processing scanned nomination/petition papers: OCR extraction,
USPS address validation, and geofencing against a legislative district boundary.

## Pipeline

1. **`ocr_petitions.py`** — converts scanned petition PDFs to images and sends
   them to a vision-capable LLM (via an OpenAI-compatible endpoint) to extract
   signer rows into `petition_signers.csv`.
2. **`validate_addresses.py`** — runs each address through the USPS Address
   API to standardize it, producing `petition_signers_validated.csv`.
3. **`geofence_addresses.py`** — geocodes each (USPS-standardized) address via
   Nominatim and checks whether it falls inside the district boundary defined
   in `district76.geojson`, producing `petition_signers_geofenced.csv`.

## Setup

```
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

`pdf2image` requires the `poppler-utils` system package (`poppler` on macOS via
Homebrew, `poppler-utils` on Debian/Ubuntu).

Copy `.env.example` to `.env` and fill in your USPS API credentials
(`USPS_CLIENT_ID` / `USPS_CLIENT_SECRET`, from https://developers.usps.com/).

`ocr_petitions.py` points at a local OpenAI-compatible vision model endpoint
(`VLLM_BASE_URL`) — update that constant to point at your own server.

## Usage

```
python ocr_petitions.py
python validate_addresses.py
python geofence_addresses.py
```

Each script also has a `test` mode for a one-off smoke test, e.g.:

```
python validate_addresses.py test
python geofence_addresses.py test
```

## Data

Input PDFs and all generated CSVs contain personal data (names, addresses,
signatures) and are gitignored — never commit them. Replace `district76.geojson`
with the boundary file for your own district.

## TODO

- Validate `date_of_signing` on each signer row (e.g. falls within the
  petition circulation window, not in the future, parses as a real date).
- Flag signer rows with missing required data (name, address, city, zip, or
  date) so they can be reviewed instead of silently passed downstream.
- Validate the circulator signature/date block at the bottom of each petition
  page (`circulator_name`, `circulator_address`, `circulator_date` present
  and the date is on/after the last signature date on that page).
