import base64
import csv
import json
import os
import re
import requests
from io import BytesIO
from pathlib import Path

# --- Configuration ---
VLLM_BASE_URL = os.environ.get("VLLM_BASE_URL", "http://192.168.1.247:8000")
MODEL_NAME = os.environ.get("VLLM_MODEL", "qwen3-vl")
DPI = 300
OUTPUT_FILE = "petition_signers.csv"

PDF_FILES = [
    "PetitionDocs_1-16.pdf",
    "PetitionDocs_17-32.pdf",
    "PetitionDocs_33-48.pdf",
]

HEADERS = [
    "source_file", "page_number", "signer_row",
    "print_name", "street_address", "city", "zip",
    "municipality_type", "municipality_name",
    "date_of_signing", "email", "crossed_out",
    "circulator_name", "circulator_address", "circulator_date",
    "circulator_signature_present",
    "candidate_name", "candidate_address", "candidate_municipality",
    "candidate_municipality_type", "candidate_zip",
    "candidate_election_date", "candidate_party", "candidate_office",
    "candidate_district", "candidate_jurisdiction",
]

CANDIDATE_FIELDS = [
    "candidate_name", "candidate_address", "candidate_municipality",
    "candidate_municipality_type", "candidate_zip",
    "candidate_election_date", "candidate_party", "candidate_office",
    "candidate_district", "candidate_jurisdiction",
]

PROMPT = """You are reading a scanned Wisconsin nomination paper for partisan office. Extract all data into a JSON object.

Structure:
{
  "page_number": <integer shown in the box at bottom-right of the page>,
  "candidate": {
    "name": "<candidate printed name, or null>",
    "address": "<candidate voting street address, or null>",
    "municipality": "<candidate voting municipality, or null>",
    "municipality_type": "<exactly one of: Town, Village, City — whichever checkbox is checked — or null>",
    "zip": "<5-digit zip code, or null>",
    "election_date": "<election date as written, or null>",
    "party": "<party name or statement of principle, or null>",
    "office": "<office title, e.g. Representative to the Assembly, or null>",
    "district": "<district number, or null>",
    "jurisdiction": "<whole jurisdiction/district text, or null>"
  },
  "signers": [
    {
      "row": <1-10>,
      "signature_present": <true if there is a handwritten signature in the first column, false if blank>,
      "print_name": "<printed/written name, or null>",
      "street_address": "<street number and street name, or null>",
      "city": "<city, or null>",
      "zip": "<5-digit zip code, or null>",
      "municipality_type": "<exactly one of: Town, Village, City — whichever checkbox is checked — or null>",
      "municipality_name": "<municipality name written by the checkbox, or null>",
      "date_of_signing": "<date exactly as written, e.g. 5/1/2026 — if year appears as 26 expand to 2026, or null>",
      "email": "<email address, or null>",
      "crossed_out": <true if this row or any part of it has a line drawn through it, false otherwise>
    }
  ],
  "circulator": {
    "name": "<circulator printed name from the 'I certify' line, or null>",
    "address": "<residential address as written, or null>",
    "date": "<date as written, or null>",
    "signature_present": <true if the circulator signature line is signed, false if blank>
  }
}

Rules:
- Always include all 10 rows, even blank ones (signature_present: false, other fields null).
- Use null for any field you cannot read clearly — do not guess.
- A ditto mark means "same as above"; copy the value from the previous row when it is unambiguous.
- Return ONLY the JSON object, no explanation, no markdown fences."""


def img_to_b64(img):
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=93)
    return base64.b64encode(buf.getvalue()).decode()


def parse_json(text):
    text = text.strip()
    # Strip markdown code fences if the model wraps the output
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s*```\s*$", "", text, flags=re.MULTILINE)
    return json.loads(text.strip())


def build_rows(page_data, pdf_name, page_idx=0):
    """Turn one page of OCR JSON into CSV rows.

    Kept separate from the HTTP call so fixture pages can be tested without a
    vision model or a PDF.
    """
    page_num = page_data.get("page_number", page_idx + 1)
    circulator = page_data.get("circulator") or {}
    candidate = page_data.get("candidate") or {}
    candidate_values = {
        field: candidate.get(field.removeprefix("candidate_"))
        for field in CANDIDATE_FIELDS
    }

    rows = []
    for signer in page_data.get("signers", []):
        if not signer.get("signature_present"):
            continue
        row = {
            "source_file": pdf_name,
            "page_number": page_num,
            "signer_row": signer.get("row"),
            "print_name": signer.get("print_name"),
            "street_address": signer.get("street_address"),
            "city": signer.get("city"),
            "zip": signer.get("zip"),
            "municipality_type": signer.get("municipality_type"),
            "municipality_name": signer.get("municipality_name"),
            "date_of_signing": signer.get("date_of_signing"),
            "email": signer.get("email"),
            "crossed_out": signer.get("crossed_out", False),
            "circulator_name": circulator.get("name"),
            "circulator_address": circulator.get("address"),
            "circulator_date": circulator.get("date"),
            "circulator_signature_present": circulator.get("signature_present"),
        }
        row.update(candidate_values)
        rows.append(row)
    return rows


def process_page(img, pdf_name, page_idx):
    b64 = img_to_b64(img)
    response = requests.post(
        f"{VLLM_BASE_URL}/v1/chat/completions",
        json={
            "model": MODEL_NAME,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                        {"type": "text", "text": PROMPT},
                    ],
                }
            ],
            "max_tokens": 3000,
            "temperature": 0.0,
        },
        timeout=600,
    )
    response.raise_for_status()
    raw = response.json()["choices"][0]["message"]["content"]
    try:
        data = parse_json(raw)
    except Exception as exc:
        print(f"\n  [WARN] JSON parse failed for {pdf_name} image {page_idx + 1}: {exc}")
        print(f"  Raw (first 400 chars): {raw[:400]}")
        return []
    return build_rows(data, pdf_name, page_idx)


def process_pdf(pdf_path):
    from pdf2image import convert_from_path

    print(f"\nConverting {pdf_path} to images (DPI={DPI})...")
    images = convert_from_path(pdf_path, dpi=DPI)
    all_rows = []
    pdf_name = Path(pdf_path).name

    for i, img in enumerate(images):
        print(f"  Page image {i + 1}/{len(images)}...", end=" ", flush=True)
        rows = process_page(img, pdf_name, i)
        print(f"{len(rows)} signers")
        all_rows.extend(rows)

    return all_rows


def write_csv(all_rows):
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(all_rows)


def main():
    all_rows = []
    for pdf in PDF_FILES:
        if not Path(pdf).exists():
            print(f"WARNING: {pdf} not found, skipping.")
            continue
        all_rows.extend(process_pdf(pdf))

    write_csv(all_rows)
    print(f"\nSaved {len(all_rows)} signers to {OUTPUT_FILE}")
    for row in all_rows:
        print(f"  p{row['page_number']} row{row['signer_row']} | {row['print_name']} | "
              f"{row['street_address']}, {row['city']} {row['zip']}")


if __name__ == "__main__":
    main()
