"""
Coordinates for a page rendered at 1103 x 1426 pixels.

These are intentionally centralized so you can calibrate them once against
your exact EL-168 blank image. The renderer scales them automatically if the
template has a different size.

The map is designed for the current EL-168-style layout:
candidate/header at top, ten signer rows, circulator certification at bottom.
"""

BASE_W = 1103
BASE_H = 1426

# x, y anchors for handwritten text
FIELDS = {
    "candidate_name": (65, 102),
    "candidate_address": (420, 102),
    "candidate_municipality": (855, 112),
    "candidate_mailing": (65, 180),
    "candidate_state": (515, 180),
    "candidate_zip": (580, 180),
    "candidate_election_date": (770, 180),
    "candidate_party": (915, 180),

    "candidate_office": (65, 258),
    "candidate_district": (590, 258),
    "candidate_jurisdiction": (845, 258),

    "circulator_name": (165, 1245),
    "circulator_address": (520, 1245),
    "circulator_date": (155, 1360),
    "circulator_signature": (485, 1360),
    "page_number": (1015, 1360),
}

# Checkbox centers. Adjust if needed after rendering a calibration page.
CHECKBOXES = {
    "candidate_municipality": {
        "Town": (830, 92),
        "Village": (830, 112),
        "City": (830, 132),
    },
    "election_type": {
        "general": (720, 156),
        "special": (720, 176),
    },
    "district_number": (565, 238),
}

# Signer table row anchors. Columns:
# signature, printed_name, address, municipality, date
SIGNER_ROWS = [
    {"signature": (45, 520), "printed_name": (250, 520), "address": (455, 520), "municipality": (745, 520), "date": (980, 520)},
    {"signature": (45, 585), "printed_name": (250, 585), "address": (455, 585), "municipality": (745, 585), "date": (980, 585)},
    {"signature": (45, 650), "printed_name": (250, 650), "address": (455, 650), "municipality": (745, 650), "date": (980, 650)},
    {"signature": (45, 715), "printed_name": (250, 715), "address": (455, 715), "municipality": (745, 715), "date": (980, 715)},
    {"signature": (45, 780), "printed_name": (250, 780), "address": (455, 780), "municipality": (745, 780), "date": (980, 780)},
    {"signature": (45, 845), "printed_name": (250, 845), "address": (455, 845), "municipality": (745, 845), "date": (980, 845)},
    {"signature": (45, 910), "printed_name": (250, 910), "address": (455, 910), "municipality": (745, 910), "date": (980, 910)},
    {"signature": (45, 975), "printed_name": (250, 975), "address": (455, 975), "municipality": (745, 975), "date": (980, 975)},
    {"signature": (45, 1040), "printed_name": (250, 1040), "address": (455, 1040), "municipality": (745, 1040), "date": (980, 1040)},
    {"signature": (45, 1105), "printed_name": (250, 1105), "address": (455, 1105), "municipality": (745, 1105), "date": (980, 1105)},
]

# Municipality checkbox centers relative to each signer row anchor.
# The renderer can draw the checkbox marker near the municipality text.
SIGNER_MUNI_CHECKBOX_OFFSETS = {
    "Town": (-18, -15),
    "Village": (-18, 0),
    "City": (-18, 15),
}
