"""Review sheets to look at before going on.

Usage:
  python3 -I sheet.py <workdir> boxes             review/boxes.png: the illustration with every locked part's box
  python3 -I sheet.py <workdir> [frame ...]       review/keyframes.png: the illustration and the frames side by side
                                                  (all frames drawn so far if none are named), whole body above and
                                                  the close-up box (`review.closeup` in loop.json) enlarged below
Frames are shown as drawn (matched/, before stabilising and before `mirror`).
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

sys.dont_write_bytecode = True  # no __pycache__ in the skill's folder
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ART, load_config  # noqa: E402

TILE = 300
BG = (240, 232, 216, 255)
COLORS = [(220, 40, 40), (30, 110, 220), (20, 150, 70), (200, 120, 0), (150, 50, 200), (0, 150, 160), (200, 40, 140)]


def font(size):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow before 10.1 has one fixed size
        return ImageFont.load_default()


def tile(im, box):
    c = im.crop(box)
    c = c.resize((TILE, round(c.height * TILE / c.width)), Image.LANCZOS)
    t = Image.new("RGBA", c.size, BG)
    t.alpha_composite(c)
    return t


def body_box(art):
    x0, y0, x1, y1 = art.getchannel("A").point(lambda a: 255 if a > 128 else 0).getbbox()
    return (max(0, x0 - 30), max(0, y0 - 30), min(1024, x1 + 30), min(1024, y1 + 30))


def boxes(cfg, work):
    art = Image.open(os.path.join(work, "keyed", f"{ART}.png")).convert("RGBA")
    im = Image.new("RGBA", art.size, BG)
    im.alpha_composite(art)
    d = ImageDraw.Draw(im)
    f = font(18)
    for i, p in enumerate(q for q in cfg["parts"] if "box" in q):
        c = COLORS[i % len(COLORS)]
        d.rectangle(p["box"], outline=c, width=3)
        d.text((p["box"][0] + 4, p["box"][1] + 2), p["name"], fill=c, font=f)
    out = os.path.join(work, "review", "boxes.png")
    im.convert("RGB").save(out)
    print(out)


def frames(cfg, work, names):
    names = names or [n for n in cfg["frames"] if os.path.exists(os.path.join(work, "matched", f"{n}.png"))]
    items = [(ART, Image.open(os.path.join(work, "keyed", f"{ART}.png")).convert("RGBA"))]
    items += [(n, Image.open(os.path.join(work, "matched", f"{n}.png")).convert("RGBA")) for n in names]
    body = tuple(cfg.get("review", {}).get("body") or body_box(items[0][1]))
    close = cfg.get("review", {}).get("closeup")
    rows = [(label, tile(im, body), tile(im, tuple(close)) if close else None) for label, im in items]
    gap, label_h = 10, 28
    bh = rows[0][1].height
    ch = rows[0][2].height if close else 0
    sheet = Image.new("RGBA", (len(rows) * (TILE + gap) - gap, label_h + bh + (gap + ch if close else 0)), (255, 255, 255, 255))
    d = ImageDraw.Draw(sheet)
    f = font(18)
    for i, (label, b, c) in enumerate(rows):
        x = i * (TILE + gap)
        d.text((x + 6, 4), label, fill=(60, 45, 30), font=f)
        sheet.alpha_composite(b, (x, label_h))
        if c:
            sheet.alpha_composite(c, (x, label_h + bh + gap))
    out = os.path.join(work, "review", "keyframes.png")
    sheet.convert("RGB").save(out)
    print(out, sheet.size)


def main(work, *args):
    cfg = load_config(work)
    os.makedirs(os.path.join(work, "review"), exist_ok=True)
    if args and args[0] == "boxes":
        boxes(cfg, work)
    else:
        frames(cfg, work, list(args))


if __name__ == "__main__":
    main(*sys.argv[1:])
