"""Apply nomination-paper validation rules to OCR output.

This is the review step that runs before address validation.  It never changes
the OCR data; it adds ``validation_status``, ``validation_errors``,
``validation_warnings``, and ``validation_notes`` columns so a human can sort
or filter the CSV.

Examples::

    python validate_petitions.py petition_signers.csv \
        --start-date 2026-04-01 --election-date 2026-11-03 --district 76

    python validate_petitions.py petition_signers.csv --today 2026-10-21
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any

from petition_rules import parse_date, summarize, validate_rows

INPUT_FILE = "petition_signers.csv"
OUTPUT_FILE = "petition_signers_checked.csv"

ADDED_HEADERS = [
    "validation_status",
    "validation_errors",
    "validation_warnings",
    "validation_notes",
]


def read_csv(path: Path) -> tuple[list[str], list[dict[str, Any]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    return fieldnames, rows


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    output_headers = list(fieldnames)
    for header in ADDED_HEADERS:
        if header not in output_headers:
            output_headers.append(header)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=output_headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", default=INPUT_FILE, help="OCR CSV to validate")
    parser.add_argument("-o", "--output", default=OUTPUT_FILE, help="annotated CSV output path")
    parser.add_argument("--today", default=None, help="override today's date (YYYY-MM-DD)")
    parser.add_argument("--start-date", default=None, help="first day signatures may be dated")
    parser.add_argument("--end-date", default=None, help="last day signatures may be dated")
    parser.add_argument(
        "--election-date",
        default=None,
        help="election date; used as the end of the window when --end-date is omitted",
    )
    parser.add_argument(
        "--district",
        default=None,
        help="expected district number, e.g. 76; enables candidate-header checks",
    )
    parser.add_argument(
        "--require-zip",
        action="store_true",
        help="treat a missing ZIP code as an error instead of a warning",
    )
    parser.add_argument("--no-circulator", action="store_true", help="skip circulator checks")
    parser.add_argument("--no-header", action="store_true", help="skip candidate-header checks")
    parser.add_argument("--no-duplicates", action="store_true", help="skip duplicate detection")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    if not input_path.exists():
        parser.error(f"input file not found: {input_path}")

    for label, value in (
        ("--today", args.today),
        ("--start-date", args.start_date),
        ("--end-date", args.end_date),
        ("--election-date", args.election_date),
    ):
        if value is not None and parse_date(value) is None:
            parser.error(f"{label} is not a date: {value!r}")

    fieldnames, rows = read_csv(input_path)
    if not rows:
        print(f"No rows found in {input_path}")
        return 0

    validated = validate_rows(
        rows,
        today=args.today,
        start_date=args.start_date,
        end_date=args.end_date,
        election_date=args.election_date,
        expected_district=args.district,
        require_zip=args.require_zip,
        check_circulator=not args.no_circulator,
        check_header=not args.no_header,
        check_duplicates=not args.no_duplicates,
    )

    output_path = Path(args.output)
    write_csv(output_path, fieldnames, validated)

    summary = summarize(validated)
    counts = summary["counts"]
    print(f"Validated {len(validated)} signer rows from {input_path}")
    print(f"  valid:    {counts.get('valid', 0)}")
    print(f"  review:   {counts.get('review', 0)}")
    print(f"  invalid:  {counts.get('invalid', 0)}")
    print(f"  excluded: {counts.get('excluded', 0)}")
    if summary["codes"]:
        print("Top findings:")
        for code, count in list(summary["codes"].items())[:10]:
            print(f"  {code}: {count}")
    print(f"Saved to {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
