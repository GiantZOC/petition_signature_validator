# EL-168 Synthetic Petition Test Generator

Creates synthetic Wisconsin EL-168-style petition sheets for OCR, document
understanding, and validator testing without storing real voter data.

## What it produces

For every test case:

- `case_name.png` — rendered petition
- `case_name.json` — exact synthetic ground truth and injected defects

The generator intentionally keeps **observed defects** separate from **legal
validity**. Your validator should apply the current Wisconsin rules.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Place a clean rendered image of page 1 of the blank EL-168 in the project, e.g.:

```text
template_el168.png
```

A 300-DPI render is ideal. Any resolution works because the coordinate map is
scaled from a 1103 x 1426 baseline.

## Handwriting fonts

Put several `.ttf` or `.otf` handwriting fonts in:

```text
fonts/
```

Do not commit fonts unless their licenses allow redistribution.

The generator falls back to a few common system fonts if `fonts/` is empty,
but multiple handwriting fonts will make the tests much more realistic.

## Generate a clean valid example

```bash
python generate.py \
  --template template_el168.png \
  --case cases/valid.yaml \
  --out generated
```

## Generate mixed edge cases

```bash
python generate.py \
  --template template_el168.png \
  --case cases/mixed_edge_cases.yaml \
  --out generated
```

## Coordinate calibration

The initial coordinates are approximations for the current EL-168 layout.
Generate a numbered grid over your exact blank template:

```bash
python make_calibration_grid.py template_el168.png calibration.png --step 25
```

Open `calibration.png`, then adjust `layout.py`.

You only need to calibrate once for each template revision/resolution family.

## Supported semantic defects

- `missing_signature`
- `signature_x`
- `missing_printed_name`
- `missing_date`
- `partial_date`
- `ditto_date`
- `missing_address`
- `po_box_only`
- `missing_municipality`
- `wrong_municipality`
- `abbreviated_municipality`
- `wrong_municipality_type`
- `signer_after_circulator`
- `duplicate_signer`
- `out_of_district`
- `missing_circulator_signature`
- `missing_circulator_date`
- `missing_circulator_address`
- `wrong_district`
- `missing_district`
- `wrong_election_date`
- `blank_candidate_name`
- `blank_candidate_address`

## Supported visual defects

- `crossed_out_signature`
- `crossed_out_row`
- `overwrite_date`
- `illegible_field`
- `skew`
- `blur`
- `low_contrast`
- `photocopy`
- `crop_edge`

Example:

```yaml
seed: 18342

defects:
  - type: missing_date
    row: 2

  - type: illegible_field
    row: 4
    field: printed_name

  - type: crossed_out_signature
    row: 7

  - type: photocopy
    contrast: 1.5

  - type: skew
    degrees: -0.7
```

Signer rows are zero-based (`0` through `9`).

## Recommended test split

### Unit tests

Use clean images and one defect per sheet:

```text
valid/
missing_date/
missing_address/
wrong_municipality/
...
```

This isolates validation logic.

### Integration tests

Combine several defects with mild rendering noise.

### OCR robustness tests

Use valid data but add:

- handwriting variation
- skew
- blur
- photocopy degradation
- overwritten values
- clipped edges

This distinguishes OCR failures from legal-validation failures.

## Important

The names and addresses produced by `synthetic.py` are generated from a small
fictional pool. They are not copied from real Wisconsin petition signers.

For current legal behavior, use the current Wisconsin Elections Commission
rules and training materials rather than treating the generator's defect names
as a legal determination.
