from PIL import Image, ImageDraw, ImageFont
import argparse

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("template")
    ap.add_argument("output")
    ap.add_argument("--step", type=int, default=50)
    args = ap.parse_args()

    img = Image.open(args.template).convert("RGB")
    d = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
    except Exception:
        font = ImageFont.load_default()

    sx = img.width / 1103
    sy = img.height / 1426

    for x in range(0, 1104, args.step):
        px = int(x * sx)
        d.line((px, 0, px, img.height), fill=(190,190,190), width=1)
        d.text((px+2, 2), str(x), fill=(120,120,120), font=font)

    for y in range(0, 1427, args.step):
        py = int(y * sy)
        d.line((0, py, img.width, py), fill=(190,190,190), width=1)
        d.text((2, py+2), str(y), fill=(120,120,120), font=font)

    img.save(args.output)

if __name__ == "__main__":
    main()
