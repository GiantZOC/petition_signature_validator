from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Optional, Any


@dataclass
class Candidate:
    name: str
    address: str
    municipality: str
    municipality_type: str = "City"
    mailing_address: str = ""
    state: str = "WI"
    zip_code: str = "53704"
    election_type: str = "general"
    election_date: str = "11/03/2026"
    party: str = "Independent"
    office: str = "Representative to the Assembly"
    district_number: str = "76"
    jurisdiction: str = "76th Assembly District"


@dataclass
class Signer:
    signature: str
    printed_name: str
    address: str
    municipality: str
    municipality_type: str = "City"
    signing_date: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Circulator:
    name: str
    address: str
    date: Optional[str]
    signature: str


@dataclass
class Petition:
    candidate: Candidate
    signers: list[Signer]
    circulator: Circulator
    page_number: str = "1"
    defects: list[dict[str, Any]] = field(default_factory=list)
    render_options: dict[str, Any] = field(default_factory=dict)
    expected: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
