from __future__ import annotations
from pathlib import Path
import math, random
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter
from models import Petition
from layout import BASE_W, BASE_H, FIELDS, CHECKBOXES, SIGNER_ROWS, SIGNER_MUNI_CHECKBOX_OFFSETS

INKS = [
    (10, 20, 110),
    (20, 35, 145),
    (15, 15, 15),
    (40, 40, 55),
]

def _scale_xy(img, xy):
    sx, sy = img.width / BASE_W, img.height / BASE_H
    return int(xy[0]*sx), int(xy[1]*sy)

def _scale_px(img, px):
    return max(1, int(px * img.width / BASE_W))

def discover_fonts(font_dir: str | Path | None = None) -> list[Path]:
    found = []
    if font_dir:
        p = Path(font_dir)
        if p.exists():
            found.extend(p.glob("*.ttf"))
            found.extend(p.glob("*.otf"))

    for candidate in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        "/usr/share/fonts/opentype/urw-base35/URWChanceryL-MediumItalic.otf",
    ]:
        q = Path(candidate)
        if q.exists():
            found.append(q)

    # stable de-dup
    out, seen = [], set()
    for p in found:
        s = str(p)
        if s not in seen:
            seen.add(s)
            out.append(p)
    if not out:
        raise RuntimeError("No fonts found. Put .ttf/.otf handwriting fonts in ./fonts")
    return out

def _font(path: Path, size: int):
    return ImageFont.truetype(str(path), size=size)

def _text_layer(text, font, ink, rotate_deg=0, opacity=255):
    # oversized layer to avoid clipping handwritten text
    layer = Image.new("RGBA", (900, 150), (255,255,255,0))
    d = ImageDraw.Draw(layer)
    d.text((12, 12), text, font=font, fill=ink + (opacity,))
    if abs(rotate_deg) > 0.01:
        layer = layer.rotate(rotate_deg, resample=Image.Resampling.BICUBIC, expand=True)
    return layer

def paste_handwriting(img, xy, text, rng, fonts, size=22, signature=False,
                      forced_font=None, illegible=False):
    if text is None or text == "":
        return

    font_path = forced_font or rng.choice(fonts)
    if signature and len(fonts) > 1:
        font_path = rng.choice(fonts)

    fontsize = _scale_px(img, size + (3 if signature else 0))
    f = _font(font_path, fontsize)
    ink = rng.choice(INKS)
    rotation = rng.uniform(-2.2, 2.2)
    opacity = 255

    if illegible:
        rotation = rng.uniform(-6, 6)
        opacity = rng.randint(110, 190)

    layer = _text_layer(str(text), f, ink, rotation, opacity)
    x, y = _scale_xy(img, xy)
    x += _scale_px(img, rng.randint(-3, 4))
    y += _scale_px(img, rng.randint(-3, 3))
    img.alpha_composite(layer, (x, y))

    if illegible:
        # add a couple of pen strokes through the value
        dr = ImageDraw.Draw(img)
        for _ in range(2):
            yoff = y + rng.randint(5, 18)
            dr.line((x, yoff, x + _scale_px(img, rng.randint(40, 110)), yoff+rng.randint(-4,4)),
                    fill=ink+(170,), width=_scale_px(img, 2))

def mark_checkbox(img, xy, rng, style="check"):
    x, y = _scale_xy(img, xy)
    d = ImageDraw.Draw(img)
    ink = rng.choice(INKS) + (255,)
    w = _scale_px(img, 2)
    r = _scale_px(img, 5)
    if style == "x":
        d.line((x-r, y-r, x+r, y+r), fill=ink, width=w)
        d.line((x-r, y+r, x+r, y-r), fill=ink, width=w)
    else:
        d.line((x-r, y, x-1, y+r), fill=ink, width=w)
        d.line((x-1, y+r, x+r+3, y-r), fill=ink, width=w)

def _defect_for(defects, kind, row=None, field=None):
    for d in defects:
        if d.get("type") != kind:
            continue
        if row is not None and int(d.get("row", -999)) != row:
            continue
        if field is not None and d.get("field") != field:
            continue
        return d
    return None

def render_petition(template_path, petition: Petition, out_path,
                    seed=42, font_dir="fonts"):
    rng = random.Random(seed)
    fonts = discover_fonts(font_dir)

    img = Image.open(template_path).convert("RGBA")

    # Header
    header_values = {
        "candidate_name": petition.candidate.name,
        "candidate_address": petition.candidate.address,
        "candidate_municipality": petition.candidate.municipality,
        "candidate_mailing": petition.candidate.mailing_address,
        "candidate_state": petition.candidate.state,
        "candidate_zip": petition.candidate.zip_code,
        "candidate_election_date": petition.candidate.election_date,
        "candidate_party": petition.candidate.party,
        "candidate_office": petition.candidate.office,
        "candidate_district": petition.candidate.district_number,
        "candidate_jurisdiction": petition.candidate.jurisdiction,
        "circulator_name": petition.circulator.name,
        "circulator_address": petition.circulator.address,
        "circulator_date": petition.circulator.date or "",
        "circulator_signature": petition.circulator.signature,
        "page_number": petition.page_number,
    }

    for field, value in header_values.items():
        defect = _defect_for(petition.defects, "illegible_field", field=field)
        paste_handwriting(
            img, FIELDS[field], value, rng, fonts,
            size=19 if field.startswith("candidate_") else 18,
            signature=(field=="circulator_signature"),
            illegible=bool(defect),
        )

    if petition.candidate.municipality_type in CHECKBOXES["candidate_municipality"]:
        mark_checkbox(img, CHECKBOXES["candidate_municipality"][petition.candidate.municipality_type], rng)

    if petition.candidate.election_type in CHECKBOXES["election_type"]:
        mark_checkbox(img, CHECKBOXES["election_type"][petition.candidate.election_type], rng)

    if petition.candidate.district_number:
        mark_checkbox(img, CHECKBOXES["district_number"], rng)

    # Signer rows
    for i, signer in enumerate(petition.signers[:len(SIGNER_ROWS)]):
        row = SIGNER_ROWS[i]

        for field, value, signature in [
            ("signature", signer.signature, True),
            ("printed_name", signer.printed_name, False),
            ("address", signer.address, False),
            ("municipality", signer.municipality, False),
            ("date", signer.signing_date or "", False),
        ]:
            illeg = bool(_defect_for(petition.defects, "illegible_field", row=i, field=field))
            paste_handwriting(
                img, row[field], value, rng, fonts,
                size=17 if field != "signature" else 20,
                signature=signature,
                illegible=illeg,
            )

        # Municipality check mark (approximate near municipality column)
        if signer.municipality_type in SIGNER_MUNI_CHECKBOX_OFFSETS:
            mx, my = row["municipality"]
            ox, oy = SIGNER_MUNI_CHECKBOX_OFFSETS[signer.municipality_type]
            mark_checkbox(img, (mx + ox, my + oy), rng)

        # Visual defects
        if _defect_for(petition.defects, "crossed_out_signature", row=i):
            x, y = _scale_xy(img, row["signature"])
            d = ImageDraw.Draw(img)
            d.line((x, y+_scale_px(img, 14), x+_scale_px(img, 175), y+_scale_px(img, 7)),
                   fill=rng.choice(INKS)+(255,), width=_scale_px(img, 2))

        if _defect_for(petition.defects, "crossed_out_row", row=i):
            x1, y = _scale_xy(img, (35, row["signature"][1] + 16))
            x2, _ = _scale_xy(img, (1065, row["signature"][1] + 16))
            d = ImageDraw.Draw(img)
            d.line((x1, y, x2, y+rng.randint(-3,3)),
                   fill=rng.choice(INKS)+(230,), width=_scale_px(img, 2))

        od = _defect_for(petition.defects, "overwrite_date", row=i)
        if od:
            paste_handwriting(img, row["date"], od.get("value", "05/14/2026"),
                              rng, fonts, size=17)

    # Page-level degradation
    rgba = img
    rgb = rgba.convert("RGB")

    for d in petition.defects:
        kind = d["type"]

        if kind == "skew":
            deg = float(d.get("degrees", rng.uniform(-1.2, 1.2)))
            rgb = rgb.rotate(deg, resample=Image.Resampling.BICUBIC, expand=False, fillcolor="white")

        elif kind == "blur":
            rgb = rgb.filter(ImageFilter.GaussianBlur(float(d.get("radius", 0.7))))

        elif kind == "low_contrast":
            rgb = ImageEnhance.Contrast(rgb).enhance(float(d.get("factor", 0.72)))

        elif kind == "photocopy":
            gray = rgb.convert("L")
            contrast = float(d.get("contrast", 1.45))
            gray = ImageEnhance.Contrast(gray).enhance(contrast)
            threshold = int(d.get("threshold", 210))
            # keep grayscale rather than hard threshold so OCR sees realistic copy noise
            gray = gray.point(lambda p: max(0, min(255, int((p-threshold)*1.1 + threshold))))
            rgb = gray.convert("RGB")

        elif kind == "crop_edge":
            side = d.get("side", "right")
            amount = int(d.get("pixels", max(10, rgb.width // 40)))
            canvas = Image.new("RGB", rgb.size, "white")
            if side == "right":
                canvas.paste(rgb.crop((0,0,rgb.width-amount,rgb.height)), (0,0))
            elif side == "left":
                canvas.paste(rgb.crop((amount,0,rgb.width,rgb.height)), (amount,0))
            elif side == "top":
                canvas.paste(rgb.crop((0,amount,rgb.width,rgb.height)), (0,amount))
            else:
                canvas.paste(rgb.crop((0,0,rgb.width,rgb.height-amount)), (0,0))
            rgb = canvas

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    rgb.save(out_path, quality=95)
