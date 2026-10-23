from __future__ import annotations
from copy import deepcopy
from datetime import datetime, timedelta
from models import Petition

DATE_FMT = "%m/%d/%Y"

def _row(p: Petition, defect: dict):
    idx = int(defect["row"])
    if not 0 <= idx < len(p.signers):
        raise IndexError(f"row must be 0..{len(p.signers)-1}, got {idx}")
    return p.signers[idx]

def apply_defects(petition: Petition, defects: list[dict]) -> Petition:
    p = deepcopy(petition)
    p.defects = deepcopy(defects)

    for d in defects:
        kind = d["type"]

        if kind == "missing_signature":
            _row(p, d).signature = ""

        elif kind == "signature_x":
            _row(p, d).signature = "X"

        elif kind == "missing_printed_name":
            _row(p, d).printed_name = ""

        elif kind == "missing_date":
            _row(p, d).signing_date = None

        elif kind == "partial_date":
            _row(p, d).signing_date = d.get("value", "05/__/2026")

        elif kind == "ditto_date":
            _row(p, d).signing_date = '"'

        elif kind == "missing_address":
            _row(p, d).address = ""

        elif kind == "po_box_only":
            _row(p, d).address = d.get("value", "PO Box 432")

        elif kind == "missing_municipality":
            _row(p, d).municipality = ""

        elif kind == "wrong_municipality":
            _row(p, d).municipality = d.get("value", "Middleton")

        elif kind == "abbreviated_municipality":
            _row(p, d).municipality = d.get("value", "Mad.")

        elif kind == "wrong_municipality_type":
            _row(p, d).municipality_type = d.get("value", "Village")

        elif kind == "signer_after_circulator":
            if not p.circulator.date:
                raise ValueError("circulator date required for signer_after_circulator")
            cd = datetime.strptime(p.circulator.date, DATE_FMT)
            _row(p, d).signing_date = (cd + timedelta(days=d.get("days", 1))).strftime(DATE_FMT)

        elif kind == "duplicate_signer":
            src = int(d.get("source_row", 0))
            dst = int(d["row"])
            p.signers[dst] = deepcopy(p.signers[src])

        elif kind == "out_of_district":
            s = _row(p, d)
            s.municipality = d.get("municipality", "Sun Prairie")
            s.metadata["synthetic_out_of_district"] = True

        elif kind == "missing_circulator_signature":
            p.circulator.signature = ""

        elif kind == "missing_circulator_date":
            p.circulator.date = None

        elif kind == "missing_circulator_address":
            p.circulator.address = ""

        elif kind == "wrong_district":
            p.candidate.district_number = str(d.get("value", "77"))
            p.candidate.jurisdiction = d.get("jurisdiction", "77th Assembly District")

        elif kind == "missing_district":
            p.candidate.district_number = ""
            p.candidate.jurisdiction = ""

        elif kind == "wrong_election_date":
            p.candidate.election_date = d.get("value", "11/04/2026")

        elif kind == "blank_candidate_name":
            p.candidate.name = ""

        elif kind == "blank_candidate_address":
            p.candidate.address = ""

        # Visual-only defects are handled in render.py.
        elif kind in {
            "crossed_out_signature",
            "crossed_out_row",
            "overwrite_date",
            "illegible_field",
            "scribble_field",
            "crop_edge",
            "photocopy",
            "skew",
            "blur",
            "low_contrast",
        }:
            pass

        else:
            raise ValueError(f"Unknown defect type: {kind}")

    return p
