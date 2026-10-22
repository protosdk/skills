"""Check one edited frame for shift: did any locked part move against the image it was edited from?

Usage: python3 -I shift.py <workdir> <frame> [image]   (image defaults to <workdir>/raw/<frame>.png)
Exit code 0: no shift. 1: shift, redo the edit.

Each locked part with a box is compared by its outlines: the offset within +-10 px that overlaps the
input's outlines best must be exactly (0, 0). Parts the frame lists in `moves` are not measured. The
input is the image the edit was made from, which is also the image it plays next to.
A frame edited from the illustration itself may be off by ART_SHIFT_PX: the illustration does not play
in the loop, and that frame becomes what every later frame is measured against.
"""
import os
import sys

sys.dont_write_bytecode = True  # no __pycache__ in the skill's folder
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ART, MIN_LINE_PX, key_green, lines, load_1024, load_config, local_shift  # noqa: E402

ART_SHIFT_PX = 1


def measure(cfg, work, name, image=None):
    fr = cfg["frames"][name]
    image = image or os.path.join(work, "raw", f"{name}.png")
    ref = lines(key_green(load_1024(os.path.join(work, "in", f"{fr['from']}.png"))))
    cur = lines(key_green(load_1024(image)))
    parts, moved = {}, []
    tol = ART_SHIFT_PX if fr["from"] == ART else 0
    for p in cfg["parts"]:
        if "box" not in p or p["name"] in fr.get("moves", []):
            continue
        x0, y0, x1, y1 = p["box"]
        n = int(ref[y0:y1, x0:x1].sum())
        dx, dy, s = local_shift(ref, cur, p["box"])
        parts[p["name"]] = {"shift": [dx, dy], "overlap": round(float(s), 3), "line_px": n}
        if max(abs(dx), abs(dy)) > tol or n < MIN_LINE_PX:
            moved.append(p["name"])
    return {"frame": name, "from": fr["from"], "image": os.path.relpath(image, work), "limit_px": tol, "pass": not moved,
            "moved": moved, "parts": parts}


def describe(r):
    parts = ", ".join(f"{k} ({v['shift'][0]:+d},{v['shift'][1]:+d}) {v['overlap']:.2f}" for k, v in r["parts"].items())
    head = "no shift" if r["pass"] else "SHIFT: " + ", ".join(r["moved"])
    return f"{r['frame']} vs {r['from']}: {head} | {parts}"


def main(work, name, image=None):
    r = measure(load_config(work), work, name, image)
    print(describe(r))
    sys.exit(0 if r["pass"] else 1)


if __name__ == "__main__":
    main(*sys.argv[1:])
