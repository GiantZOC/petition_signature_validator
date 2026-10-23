from __future__ import annotations
import random
from models import Candidate, Signer, Circulator, Petition

FIRST = [
    "Jordan", "Emily", "Noah", "Sofia", "Liam", "Ava", "Mason", "Chloe",
    "Ethan", "Mia", "Caleb", "Nora", "Owen", "Leah", "Miles", "Grace",
]
LAST = [
    "Pike", "Carter", "Bennett", "Ramirez", "Turner", "Collins", "Reed",
    "Foster", "Brooks", "Sullivan", "Hayes", "Morgan", "Lane", "Parker",
]
STREETS = [
    "Maple Grove Dr", "Westmorland Blvd", "Lake Edge Rd", "High Point Cir",
    "Oak Crest Ave", "Cedar Ln", "Rolling Meadow Rd", "Spruce Way",
    "Hilldale Ave", "Northern Lights Trl", "Birch Hollow Dr", "Meadow Park Ave",
]

def fake_name(rng: random.Random) -> str:
    return f"{rng.choice(FIRST)} {rng.choice(LAST)}"

def fake_address(rng: random.Random) -> str:
    return f"{rng.randint(101, 6499)} {rng.choice(STREETS)}"

def make_base_petition(seed: int = 42) -> Petition:
    rng = random.Random(seed)

    candidate = Candidate(
        name="Alex Monroe",
        address="1842 Birch Hollow Dr",
        municipality="Madison",
        municipality_type="City",
        mailing_address="1842 Birch Hollow Dr, Madison, WI 53704",
        state="WI",
        zip_code="53704",
        election_type="general",
        election_date="11/03/2026",
        party="Independent",
        office="Representative to the Assembly",
        district_number="76",
        jurisdiction="76th Assembly District",
    )

    dates = [
        "04/28/2026", "04/29/2026", "05/01/2026", "05/02/2026", "05/03/2026",
        "05/04/2026", "05/06/2026", "05/08/2026", "05/10/2026", "05/12/2026",
    ]

    signers = []
    used = set()
    for i in range(10):
        while True:
            n = fake_name(rng)
            if n not in used:
                used.add(n)
                break
        signers.append(Signer(
            signature=n,
            printed_name=n,
            address=fake_address(rng),
            municipality="Madison",
            municipality_type="City",
            signing_date=dates[i],
        ))

    circulator = Circulator(
        name="Taylor Jensen",
        address="2210 Meadow Park Ave, Madison, WI 53704",
        date="05/14/2026",
        signature="Taylor Jensen",
    )

    return Petition(
        candidate=candidate,
        signers=signers,
        circulator=circulator,
        page_number="1",
    )
