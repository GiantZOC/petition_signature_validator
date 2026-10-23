from __future__ import annotations
import argparse, json
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

from synthetic import make_base_petition
from defects import apply_defects
from render import render_petition


def load_case(path: Path):
    text = path.read_text()
    if path.suffix.lower() in {".yaml", ".yml"}:
        if yaml is None:
            raise RuntimeError("Install PyYAML or use JSON case files")
        return yaml.safe_load(text)
    return json.loads(text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", required=True, help="Blank EL-168 page rendered as PNG/JPG")
    ap.add_argument("--case", required=True, help="YAML or JSON test case")
    ap.add_argument("--out", default="generated", help="Output directory")
    ap.add_argument("--fonts", default="fonts", help="Folder containing handwriting fonts")
    args = ap.parse_args()

    case = load_case(Path(args.case))
    seed = int(case.get("seed", 42))

    petition = make_base_petition(seed)

    # Optional field overrides
    c = case.get("candidate", {})
    for k, v in c.items():
        setattr(petition.candidate, k, v)

    circ = case.get("circulator", {})
    for k, v in circ.items():
        setattr(petition.circulator, k, v)

    petition.page_number = str(case.get("page_number", petition.page_number))
    petition.expected = case.get("expected", {})

    defects = case.get("defects", [])
    petition = apply_defects(petition, defects)

    case_name = Path(args.case).stem
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    image_path = outdir / f"{case_name}.png"
    truth_path = outdir / f"{case_name}.json"

    render_petition(
        args.template,
        petition,
        image_path,
        seed=seed,
        font_dir=args.fonts,
    )

    truth = petition.to_dict()
    truth["seed"] = seed
    truth["source_case"] = str(args.case)
    truth["generated_image"] = str(image_path)

    truth_path.write_text(json.dumps(truth, indent=2))
    print(image_path)
    print(truth_path)


if __name__ == "__main__":
    main()
