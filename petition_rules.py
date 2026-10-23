"""Validation rules for scanned Wisconsin nomination papers.

The OCR stage is deliberately permissive: it records what it sees and lets a
human decide what is legally acceptable.  This module is the deterministic
layer that turns those observations into review flags.  It does not contact
any API and does not depend on a particular OCR vendor, so it can be reused
for CSV rows, JSON rows, or hand-entered test data.

Status values:
    valid     no errors and no warnings
    review    at least one warning, but no error
    invalid   at least one error
    excluded  signature missing or row crossed out (not counted at all)

A row can be both excluded and have other errors; the status is still
``excluded`` so downstream counts do not include it.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Iterable, Mapping, Sequence

STATUS_VALID = "valid"
STATUS_REVIEW = "review"
STATUS_INVALID = "invalid"
STATUS_EXCLUDED = "excluded"

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"

ALLOWED_MUNICIPALITY_TYPES = {"town", "village", "city"}

# The EL-168 form asks for the municipality type by checkbox.  These values are
# what OCR should return; anything else needs a human to look at the page.
DITTO_MARKS = {'"', "'", "''", "ditto", "do.", "same", "same as above", "-", "--"}
PLACEHOLDER_VALUES = {
    "", "n/a", "na", "n.a.", "none", "null", "unknown", "?", "??", "x",
}

STREET_SUFFIXES = {
    "street": "st",
    "avenue": "ave",
    "road": "rd",
    "drive": "dr",
    "lane": "ln",
    "court": "ct",
    "circle": "cir",
    "boulevard": "blvd",
    "place": "pl",
    "terrace": "ter",
    "parkway": "pkwy",
    "trail": "trl",
    "highway": "hwy",
}

DATE_FORMATS = (
    "%m/%d/%Y",
    "%m/%d/%y",
    "%Y-%m-%d",
    "%m-%d-%Y",
    "%m-%d-%y",
    "%m.%d.%Y",
    "%m.%d.%y",
)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
PO_BOX_RE = re.compile(
    r"\b(?:P\.?\s*O\.?\s*(?:BOX|BIN)|POB|POST\s+OFFICE\s+BOX)\b", re.I
)
RURAL_ROUTE_RE = re.compile(
    r"\b(?:RR|RURAL\s+ROUTE|HC|HIGHWAY\s+CONTRACT)\b", re.I
)
HOUSE_NUMBER_RE = re.compile(
    r"^\s*(?:[NSEW]\.?\s*)?\d+(?:-\d+)?(?:\s+\d+/\d+)?[A-Za-z]?\b", re.I
)
DISTRICT_RE = re.compile(r"\b(?:DISTRICT|DIST\.?|ASSEMBLY|SENATE)?\s*(\d{1,3})\b", re.I)
ZIP_RE = re.compile(r"^(\d{5})(?:\s*-\s*|\s+)?(\d{4})?$")


@dataclass(frozen=True)
class RowIssue:
    code: str
    message: str
    field: str = ""
    severity: str = SEVERITY_ERROR

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
            "field": self.field,
            "severity": self.severity,
        }


def as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def is_blank(value: Any) -> bool:
    return as_text(value) == ""


def is_placeholder(value: Any) -> bool:
    return as_text(value).lower() in PLACEHOLDER_VALUES


def has_value(value: Any) -> bool:
    return not is_blank(value) and not is_placeholder(value)


def is_ditto(value: Any) -> bool:
    return as_text(value).lower().strip(" .") in DITTO_MARKS


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return as_text(value).lower() in {"1", "true", "yes", "y", "on"}


def is_explicitly_false(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return not value
    return as_text(value).lower() in {"0", "false", "no", "n", "off"}


def parse_date(value: Any) -> date | None:
    """Parse the date formats commonly produced by OCR or typed by hand."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    text = as_text(value)
    if not text:
        return None
    text = text.replace("\u2013", "-").replace("\u2014", "-").strip()
    if "T" in text:
        text = text.split("T", 1)[0]

    # ISO first, then the slash/dot forms.  Try the whole string before the
    # first whitespace token so "May 1, 2026" is not truncated unnecessarily.
    candidates = [text]
    first = text.split()[0]
    if first != text:
        candidates.append(first)

    for candidate in candidates:
        try:
            return date.fromisoformat(candidate)
        except ValueError:
            pass
        for fmt in DATE_FORMATS:
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                continue
    return None


def coerce_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return parse_date(value)


def clean_city(city: Any) -> str:
    """Drop a state/zip tail that OCR sometimes leaves in the city field."""
    text = as_text(city).strip().rstrip(",")
    text = re.sub(r"[,\s]+[A-Z]{2}(\s+\d{5}(-\d{4})?)?$", "", text, flags=re.I)
    return text.strip()


def normalize_zip(value: Any) -> str | None:
    text = as_text(value)
    if not text:
        return None
    match = ZIP_RE.fullmatch(text)
    if not match:
        return None
    base, plus4 = match.groups()
    return f"{base}-{plus4}" if plus4 else base


def normalize_name(value: Any) -> str:
    text = as_text(value).lower().replace(".", "").replace(",", "")
    return re.sub(r"\s+", " ", text).strip()


def normalize_street(value: Any) -> str:
    text = as_text(value).lower().replace(".", " ").replace(",", " ")
    text = re.sub(
        r"\b(" + "|".join(STREET_SUFFIXES) + r")\b",
        lambda m: STREET_SUFFIXES[m.group(1)],
        text,
    )
    return re.sub(r"\s+", " ", text).strip()


def normalize_municipality(value: Any) -> str:
    text = clean_city(value).lower()
    text = re.sub(r"[^a-z0-9 ]+", "", text)
    return re.sub(r"\s+", " ", text).strip()


def municipalities_match(left: Any, right: Any) -> bool:
    """Accept abbreviations such as Mad. for Madison and Sis Bay for Sister Bay."""
    a = normalize_municipality(left)
    b = normalize_municipality(right)
    if not a or not b:
        return False
    if a == b:
        return True

    a_tokens = a.split()
    b_tokens = b.split()
    if len(a_tokens) == len(b_tokens) and len(a_tokens) > 1:
        for left, right in zip(a_tokens, b_tokens):
            if left == right:
                continue
            shorter, longer = sorted((left, right), key=len)
            if len(shorter) < 3 or not longer.startswith(shorter):
                break
        else:
            return True

    shorter, longer = sorted((a, b), key=len)
    if len(shorter) >= 3 and longer.startswith(shorter):
        return True
    return _edit_distance(a, b) <= 1 and min(len(a), len(b)) >= 4


def _edit_distance(a: str, b: str) -> int:
    if a == b:
        return 0
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(
                current[-1] + 1,
                previous[j] + 1,
                previous[j - 1] + (ca != cb),
            ))
        previous = current
    return previous[-1]


def name_issues(value: Any, field: str = "print_name") -> list[RowIssue]:
    text = as_text(value)
    if not has_value(text):
        return [RowIssue("missing_name", "printed name is missing", field)]

    tokens = re.findall(r"[A-Za-z][A-Za-z'\u2019\-.]*", text)
    if not tokens:
        return [RowIssue("invalid_name", "printed name has no letters", field)]

    if len(tokens) < 2:
        return [RowIssue(
            "name_missing_last_name",
            "printed name needs at least a first and last name",
            field,
        )]

    last = tokens[-1].strip(".'")
    if len(last) <= 1:
        return [RowIssue(
            "name_last_name_initial",
            "last name appears to be only an initial",
            field,
            SEVERITY_WARNING,
        )]
    return []


def address_issues(
    value: Any,
    field: str = "street_address",
    prefix: str = "",
    severity: str = SEVERITY_ERROR,
) -> list[RowIssue]:
    text = as_text(value)
    code_prefix = f"{prefix}_" if prefix else ""

    if not has_value(text):
        return [RowIssue(f"{code_prefix}missing_address", "street address is missing", field)]

    if PO_BOX_RE.search(text):
        return [RowIssue(
            f"{code_prefix}address_is_po_box",
            "street address is a PO box, not a residence",
            field,
            SEVERITY_WARNING,
        )]

    if RURAL_ROUTE_RE.search(text) and not HOUSE_NUMBER_RE.match(text):
        return [RowIssue(
            f"{code_prefix}address_is_rural_route",
            "rural-route address has no street number",
            field,
            SEVERITY_WARNING,
        )]

    match = HOUSE_NUMBER_RE.match(text)
    if not match:
        return [RowIssue(
            f"{code_prefix}address_missing_house_number",
            "street address has no house number",
            field,
            severity,
        )]

    remainder = text[match.end():].strip(" ,.")
    if not re.search(r"[A-Za-z]", remainder):
        return [RowIssue(
            f"{code_prefix}address_missing_street_name",
            "street address has a house number but no street name",
            field,
            severity,
        )]
    return []


def email_issues(value: Any, field: str = "email") -> list[RowIssue]:
    if not has_value(value):
        return []
    text = as_text(value).strip().strip(",;")
    if not EMAIL_RE.match(text):
        return [RowIssue("invalid_email", "email address is malformed", field, SEVERITY_WARNING)]
    return []


def apply_ditto_marks(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Carry a ditto mark down the page for the fields where the form allows it."""
    ditto_fields = ("date_of_signing", "municipality_name", "municipality_type", "city", "zip")
    result = [dict(row) for row in rows]
    last: dict[str, Any] = {}
    current_page = object()

    for row in result:
        page = (as_text(row.get("source_file")), as_text(row.get("page_number")))
        if page != current_page:
            current_page = page
            last = {}

        for field in ditto_fields:
            value = row.get(field)
            if is_ditto(value):
                if last.get(field):
                    row[field] = last[field]
            elif has_value(value):
                last[field] = value
    return result


def _page_key(row: Mapping[str, Any]) -> tuple[str, str]:
    return as_text(row.get("source_file")), as_text(row.get("page_number"))


def _group_by_page(rows: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str], list[int]]:
    groups: dict[tuple[str, str], list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        groups[_page_key(row)].append(index)
    return groups


def _first_value(rows: Sequence[Mapping[str, Any]], field: str) -> str:
    for row in rows:
        if has_value(row.get(field)):
            return as_text(row.get(field))
    return ""


def _inconsistent(rows: Sequence[Mapping[str, Any]], field: str) -> bool:
    values = {as_text(row.get(field)).lower() for row in rows if has_value(row.get(field))}
    return len(values) > 1


def _summarize_circulator(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    signature_values = [
        truthy(row.get("circulator_signature_present"))
        for row in rows
        if has_value(row.get("circulator_signature_present"))
    ]
    if not signature_values:
        signature_present: bool | None = None
    elif all(signature_values):
        signature_present = True
    elif not any(signature_values):
        signature_present = False
    else:
        signature_present = False  # conservative: one page says no signature

    return {
        "name": _first_value(rows, "circulator_name"),
        "address": _first_value(rows, "circulator_address"),
        "date": _first_value(rows, "circulator_date"),
        "signature_present": signature_present,
        "inconsistent": _inconsistent(rows, "circulator_name")
        or _inconsistent(rows, "circulator_address")
        or _inconsistent(rows, "circulator_date"),
    }


def circulator_issues(
    summary: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    today: date,
    start_date: date | None,
    end_date: date | None,
) -> list[RowIssue]:
    issues: list[RowIssue] = []

    if summary.get("inconsistent"):
        issues.append(RowIssue(
            "circulator_inconsistent",
            "circulator block differs across rows on the same page",
            "circulator_name",
            SEVERITY_WARNING,
        ))

    if not has_value(summary.get("name")):
        issues.append(RowIssue("missing_circulator_name", "circulator name is missing", "circulator_name"))
    if not has_value(summary.get("address")):
        issues.append(RowIssue(
            "missing_circulator_address",
            "circulator address is missing",
            "circulator_address",
        ))
    else:
        issues.extend(address_issues(
            summary.get("address"), "circulator_address", prefix="circulator"
        ))

    signature_present = summary.get("signature_present")
    if signature_present is False:
        issues.append(RowIssue(
            "missing_circulator_signature",
            "circulator signature is missing",
            "circulator_signature_present",
        ))

    if not has_value(summary.get("date")):
        issues.append(RowIssue("missing_circulator_date", "circulator date is missing", "circulator_date"))
    else:
        circ_date = parse_date(summary.get("date"))
        if circ_date is None:
            issues.append(RowIssue(
                "invalid_circulator_date",
                "circulator date cannot be parsed",
                "circulator_date",
            ))
        else:
            if circ_date > today:
                issues.append(RowIssue(
                    "circulator_date_future",
                    "circulator date is in the future",
                    "circulator_date",
                ))
            if start_date and circ_date < start_date:
                issues.append(RowIssue(
                    "circulator_date_before_window",
                    "circulator date is before the circulation window",
                    "circulator_date",
                ))
            if end_date and circ_date > end_date:
                issues.append(RowIssue(
                    "circulator_date_after_window",
                    "circulator date is after the circulation window",
                    "circulator_date",
                ))
            signer_dates = [parse_date(row.get("date_of_signing")) for row in rows]
            signer_dates = [d for d in signer_dates if d]
            if signer_dates and circ_date < max(signer_dates):
                issues.append(RowIssue(
                    "circulator_date_before_signer",
                    "circulator date is before the last signature date on the page",
                    "circulator_date",
                ))
    return issues


def _summarize_header(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    fields = (
        "candidate_name",
        "candidate_address",
        "candidate_municipality",
        "candidate_municipality_type",
        "candidate_zip",
        "candidate_election_date",
        "candidate_party",
        "candidate_office",
        "candidate_district",
        "candidate_jurisdiction",
    )
    return {
        field: _first_value(rows, field) for field in fields
    } | {"inconsistent": any(_inconsistent(rows, field) for field in fields)}


def _has_any_candidate(row: Mapping[str, Any]) -> bool:
    return any(
        has_value(row.get(field))
        for field in (
            "candidate_name",
            "candidate_address",
            "candidate_district",
            "candidate_election_date",
        )
    )


def header_issues(
    summary: Mapping[str, Any],
    header_seen_anywhere: bool,
    today: date,
    expected_district: str | None,
) -> list[RowIssue]:
    issues: list[RowIssue] = []
    present = any(
        has_value(summary.get(field))
        for field in (
            "candidate_name",
            "candidate_address",
            "candidate_district",
            "candidate_election_date",
            "candidate_party",
            "candidate_office",
            "candidate_jurisdiction",
        )
    )
    if not present:
        if header_seen_anywhere:
            issues.append(RowIssue(
                "missing_candidate_header",
                "candidate header is missing on this page",
                "candidate_name",
                SEVERITY_WARNING,
            ))
        return issues

    if summary.get("inconsistent"):
        issues.append(RowIssue(
            "candidate_header_inconsistent",
            "candidate header differs across rows on the same page",
            "candidate_name",
            SEVERITY_WARNING,
        ))

    if not has_value(summary.get("candidate_name")):
        issues.append(RowIssue("missing_candidate_name", "candidate name is missing", "candidate_name"))
    else:
        issues.extend(name_issues(summary.get("candidate_name"), "candidate_name"))

    if not has_value(summary.get("candidate_address")):
        issues.append(RowIssue(
            "missing_candidate_address",
            "candidate address is missing",
            "candidate_address",
        ))
    else:
        issues.extend(address_issues(
            summary.get("candidate_address"), "candidate_address", prefix="candidate"
        ))

    district = as_text(summary.get("candidate_district"))
    if not district:
        issues.append(RowIssue(
            "missing_candidate_district",
            "candidate district is missing",
            "candidate_district",
        ))
    else:
        match = DISTRICT_RE.search(district)
        if not match:
            issues.append(RowIssue(
                "unparsed_candidate_district",
                "candidate district cannot be read as a number",
                "candidate_district",
                SEVERITY_WARNING,
            ))
        elif expected_district and match.group(1) != str(expected_district):
            issues.append(RowIssue(
                "wrong_candidate_district",
                f"candidate district is {match.group(1)}, expected {expected_district}",
                "candidate_district",
            ))

    election_date = as_text(summary.get("candidate_election_date"))
    if not election_date:
        issues.append(RowIssue(
            "missing_candidate_election_date",
            "candidate election date is missing",
            "candidate_election_date",
        ))
    else:
        parsed = parse_date(election_date)
        if parsed is None:
            issues.append(RowIssue(
                "invalid_candidate_election_date",
                "candidate election date cannot be parsed",
                "candidate_election_date",
            ))
        elif parsed < today:
            issues.append(RowIssue(
                "candidate_election_date_in_past",
                "candidate election date is in the past",
                "candidate_election_date",
            ))

    for field, label in (
        ("candidate_party", "party"),
        ("candidate_office", "office"),
        ("candidate_jurisdiction", "jurisdiction"),
        ("candidate_municipality", "municipality"),
    ):
        if not has_value(summary.get(field)):
            issues.append(RowIssue(
                f"missing_{field}",
                f"candidate {label} is missing",
                field,
                SEVERITY_WARNING,
            ))

    municipality_type = as_text(summary.get("candidate_municipality_type")).lower()
    if municipality_type and municipality_type not in ALLOWED_MUNICIPALITY_TYPES:
        issues.append(RowIssue(
            "invalid_candidate_municipality_type",
            "candidate municipality type is not Town, Village, or City",
            "candidate_municipality_type",
            SEVERITY_WARNING,
        ))

    candidate_zip = summary.get("candidate_zip")
    if not has_value(candidate_zip):
        issues.append(RowIssue(
            "missing_candidate_zip",
            "candidate ZIP code is missing",
            "candidate_zip",
            SEVERITY_WARNING,
        ))
    elif normalize_zip(candidate_zip) is None:
        issues.append(RowIssue(
            "invalid_candidate_zip",
            "candidate ZIP code is malformed",
            "candidate_zip",
        ))
    return issues


def _signer_date_issues(
    value: Any,
    today: date,
    start_date: date | None,
    end_date: date | None,
) -> list[RowIssue]:
    if not has_value(value):
        return [RowIssue("missing_date", "date of signing is missing", "date_of_signing")]

    parsed = parse_date(value)
    if parsed is None:
        return [RowIssue(
            "invalid_date",
            "date of signing cannot be parsed",
            "date_of_signing",
        )]

    issues: list[RowIssue] = []
    if parsed > today:
        issues.append(RowIssue("future_date", "date of signing is in the future", "date_of_signing"))
    if start_date and parsed < start_date:
        issues.append(RowIssue(
            "date_before_window",
            "date of signing is before the circulation window",
            "date_of_signing",
        ))
    if end_date and parsed > end_date:
        issues.append(RowIssue(
            "date_after_window",
            "date of signing is after the circulation window",
            "date_of_signing",
        ))
    return issues


def _municipality_issues(row: Mapping[str, Any]) -> list[RowIssue]:
    issues: list[RowIssue] = []
    city = row.get("city")
    municipality = row.get("municipality_name")
    municipality_type = row.get("municipality_type")

    if not has_value(municipality):
        if not has_value(city):
            issues.append(RowIssue(
                "missing_municipality",
                "municipality is missing",
                "municipality_name",
            ))
        else:
            issues.append(RowIssue(
                "municipality_name_missing",
                "municipality name is missing even though a city is present",
                "municipality_name",
                SEVERITY_WARNING,
            ))
    elif has_value(city) and not municipalities_match(city, municipality):
        issues.append(RowIssue(
            "municipality_mismatch",
            "city in the address does not match the voting municipality",
            "municipality_name",
            SEVERITY_WARNING,
        ))

    if has_value(municipality_type):
        normalized = as_text(municipality_type).lower()
        if normalized not in ALLOWED_MUNICIPALITY_TYPES:
            issues.append(RowIssue(
                "invalid_municipality_type",
                "municipality type is not Town, Village, or City",
                "municipality_type",
                SEVERITY_WARNING,
            ))
    return issues


def _zip_issues(value: Any, require_zip: bool) -> list[RowIssue]:
    if not has_value(value):
        return [RowIssue(
            "missing_zip",
            "ZIP code is missing",
            "zip",
            SEVERITY_ERROR if require_zip else SEVERITY_WARNING,
        )]
    if normalize_zip(value) is None:
        return [RowIssue("invalid_zip", "ZIP code is malformed", "zip")]
    return []


def _is_excluded(row: Mapping[str, Any]) -> bool:
    return truthy(row.get("crossed_out")) or is_explicitly_false(row.get("signature_present"))


def _duplicate_key(row: Mapping[str, Any]) -> tuple[str, str, str, str] | None:
    name = normalize_name(row.get("print_name"))
    street = normalize_street(row.get("street_address"))
    if not name or not street:
        return None
    municipality = normalize_municipality(row.get("municipality_name") or row.get("city"))
    zipcode = normalize_zip(row.get("zip")) or ""
    return name, street, municipality, zipcode


def _row_issues(
    row: Mapping[str, Any],
    today: date,
    start_date: date | None,
    end_date: date | None,
    require_zip: bool,
) -> list[RowIssue]:
    issues: list[RowIssue] = []

    if truthy(row.get("crossed_out")):
        issues.append(RowIssue(
            "crossed_out",
            "row or signature is crossed out",
            "crossed_out",
        ))
    if is_explicitly_false(row.get("signature_present")):
        issues.append(RowIssue(
            "missing_signature",
            "no handwritten signature in the signature column",
            "signature_present",
        ))

    signature = as_text(row.get("signature"))
    if signature and signature.upper() in {"X", "XX"}:
        issues.append(RowIssue(
            "signature_is_x",
            "signature is only an X mark",
            "signature",
            SEVERITY_WARNING,
        ))

    if not has_value(row.get("print_name")):
        issues.append(RowIssue("missing_name", "printed name is missing", "print_name"))
    else:
        issues.extend(name_issues(row.get("print_name")))

    issues.extend(address_issues(row.get("street_address"), "street_address"))
    issues.extend(_municipality_issues(row))
    issues.extend(_zip_issues(row.get("zip"), require_zip))
    issues.extend(_signer_date_issues(
        row.get("date_of_signing"), today, start_date, end_date
    ))
    issues.extend(email_issues(row.get("email")))

    usps_valid = as_text(row.get("usps_valid")).lower()
    if usps_valid in {"no", "false", "0"}:
        issues.append(RowIssue(
            "address_not_validated",
            "USPS did not validate the address",
            "usps_valid",
        ))
    elif usps_valid == "skipped":
        issues.append(RowIssue(
            "address_validation_skipped",
            "USPS validation was skipped",
            "usps_valid",
            SEVERITY_WARNING,
        ))

    if "in_district" in row:
        in_district = as_text(row.get("in_district")).lower()
        if in_district in {"no", "false", "0"}:
            issues.append(RowIssue(
                "out_of_district",
                "address is outside the district",
                "in_district",
            ))
        elif in_district == "unknown":
            issues.append(RowIssue(
                "district_unknown",
                "district membership could not be determined",
                "in_district",
                SEVERITY_WARNING,
            ))
    return issues


def _annotate(row: Mapping[str, Any], issues: Iterable[RowIssue]) -> dict[str, Any]:
    unique: list[RowIssue] = []
    seen: set[tuple[str, str]] = set()
    for issue in issues:
        key = (issue.code, issue.field)
        if key in seen:
            continue
        seen.add(key)
        unique.append(issue)

    errors = [issue.code for issue in unique if issue.severity == SEVERITY_ERROR]
    warnings = [issue.code for issue in unique if issue.severity == SEVERITY_WARNING]

    if _is_excluded(row):
        status = STATUS_EXCLUDED
    elif errors:
        status = STATUS_INVALID
    elif warnings:
        status = STATUS_REVIEW
    else:
        status = STATUS_VALID

    result = dict(row)
    result["validation_status"] = status
    result["validation_errors"] = ";".join(errors)
    result["validation_warnings"] = ";".join(warnings)
    result["validation_notes"] = " | ".join(issue.message for issue in unique)
    return result


def validate_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    today: Any = None,
    start_date: Any = None,
    end_date: Any = None,
    election_date: Any = None,
    expected_district: str | None = None,
    require_zip: bool = False,
    check_circulator: bool = True,
    check_header: bool = True,
    check_duplicates: bool = True,
) -> list[dict[str, Any]]:
    """Validate OCR rows and return copies annotated with review fields.

    ``start_date`` and ``end_date`` describe the circulation window.  If only
    ``election_date`` is supplied, it is used as the end of the window.  Dates
    may be ``date`` objects or strings in any format accepted by
    :func:`parse_date`.
    """
    if not rows:
        return []

    today_date = coerce_date(today) or date.today()
    start = coerce_date(start_date)
    end = coerce_date(end_date)
    election = coerce_date(election_date)
    if end is None:
        end = election

    working = apply_ditto_marks(rows)
    groups = _group_by_page(working)
    header_seen_anywhere = any(_has_any_candidate(row) for row in working)

    page_issues: dict[tuple[str, str], list[RowIssue]] = {}
    page_circulator_date: dict[tuple[str, str], date | None] = {}

    for key, indices in groups.items():
        page_rows = [working[index] for index in indices]
        issues: list[RowIssue] = []
        circulator_date: date | None = None

        if check_circulator:
            summary = _summarize_circulator(page_rows)
            issues.extend(circulator_issues(summary, page_rows, today_date, start, end))
            circulator_date = parse_date(summary.get("date"))

        if check_header:
            header = _summarize_header(page_rows)
            issues.extend(header_issues(header, header_seen_anywhere, today_date, expected_district))

        page_issues[key] = issues
        page_circulator_date[key] = circulator_date

    seen: set[tuple[str, str, str, str]] = set()
    result: list[dict[str, Any]] = []

    for row in working:
        key = _page_key(row)
        issues = list(page_issues.get(key, ()))
        issues.extend(_row_issues(row, today_date, start, end, require_zip))

        circulator_date = page_circulator_date.get(key)
        signer_date = parse_date(row.get("date_of_signing"))
        if circulator_date and signer_date and signer_date > circulator_date:
            issues.append(RowIssue(
                "date_after_circulator",
                "signer date is after the circulator certification date",
                "date_of_signing",
            ))

        if check_duplicates and not _is_excluded(row):
            duplicate_key = _duplicate_key(row)
            if duplicate_key and duplicate_key in seen:
                issues.append(RowIssue(
                    "duplicate_signer",
                    "same name and address already appears in this file",
                    "print_name",
                    SEVERITY_WARNING,
                ))
            elif duplicate_key:
                seen.add(duplicate_key)

        result.append(_annotate(row, issues))

    return result


def summarize(validated_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    counts = {
        STATUS_VALID: 0,
        STATUS_REVIEW: 0,
        STATUS_INVALID: 0,
        STATUS_EXCLUDED: 0,
    }
    codes: Counter[str] = Counter()

    for row in validated_rows:
        status = as_text(row.get("validation_status")) or STATUS_VALID
        counts[status] = counts.get(status, 0) + 1
        for field in ("validation_errors", "validation_warnings"):
            for code in as_text(row.get(field)).split(";"):
                if code:
                    codes[code] += 1

    return {"counts": counts, "codes": dict(codes.most_common())}
