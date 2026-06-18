import base64
import csv
import json
import re
import requests
from io import BytesIO
from pathlib import Path

from pdf2image import convert_from_path

# --- Configuration ---
VLLM_BASE_URL = "http://192.168.1.247:8000"
MODEL_NAME = "qwen3-vl"
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
]

PROMPT = """You are reading a scanned Wisconsin nomination paper for partisan office. Extract all data into a JSON object.

Structure:
{
  "page_number": <integer shown in the box at bottom-right of the page>,
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
    "date": "<date as written, or null>"
  }
}

Rules:
- Always include all 10 rows, even blank ones (signature_present: false, other fields null).
- Use null for any field you cannot read clearly — do not guess.
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
            "max_tokens": 2048,
            "temperature": 0.0,
        },
        timeout=600,
    )
    response.raise_for_status()
    raw = response.json()["choices"][0]["message"]["content"]
    try:
        data = parse_json(raw)
    except Exception as e:
        print(f"\n  [WARN] JSON parse failed for {pdf_name} image {page_idx + 1}: {e}")
        print(f"  Raw (first 400 chars): {raw[:400]}")
        return []

    page_num = data.get("page_number", page_idx + 1)
    circ = data.get("circulator") or {}
    rows = []

    for s in data.get("signers", []):
        if not s.get("signature_present"):
            continue
        rows.append({
            "source_file": pdf_name,
            "page_number": page_num,
            "signer_row": s.get("row"),
            "print_name": s.get("print_name"),
            "street_address": s.get("street_address"),
            "city": s.get("city"),
            "zip": s.get("zip"),
            "municipality_type": s.get("municipality_type"),
            "municipality_name": s.get("municipality_name"),
            "date_of_signing": s.get("date_of_signing"),
            "email": s.get("email"),
            "crossed_out": s.get("crossed_out", False),
            "circulator_name": circ.get("name"),
            "circulator_address": circ.get("address"),
            "circulator_date": circ.get("date"),
        })

    return rows


def process_pdf(pdf_path):
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
        writer = csv.DictWriter(f, fieldnames=HEADERS)
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
    for r in all_rows:
        print(f"  p{r['page_number']} row{r['signer_row']} | {r['print_name']} | {r['street_address']}, {r['city']} {r['zip']}")


if __name__ == "__main__":
    main()
