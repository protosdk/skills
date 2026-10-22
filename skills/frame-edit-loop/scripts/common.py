"""Shared helpers: loop.json, green-screen keying, outline maps, shift measurement, premultiplied alpha.

Every script in this folder imports from here, so they all key, resize and measure the same way.
All image coordinates are on the 1024 square work canvas that prep.py makes (the illustration centred on
a square and scaled to 1024).
"""
import json
import os
import re

import numpy as np
from PIL import Image

N = 1024  # side of the work canvas and of every image handed to the image model
GREEN_LO, GREEN_HI = 30.0, 130.0  # greenness (G - max(R, B)) in this band becomes a soft edge
LINE_MAX = 70  # mean RGB below this, on an opaque pixel, is outline ink (what the shift check compares)
SHIFT_SEARCH = 10  # px searched around (0, 0) for the best match of a locked part
MIN_LINE_PX = 50  # a locked part with fewer outline pixels than this cannot be measured
ART = "art"  # frame name of the prepared illustration


def load_config(work):
    """Read <work>/loop.json and check what later steps rely on. See references/loop-config.md."""
    path = os.path.join(work, "loop.json")
    with open(path) as f:
        cfg = json.load(f)
    problems = []
    for key in ("subject", "parts", "frames"):
        if key not in cfg:
            problems.append(f"missing {key!r}")
    parts = {p["name"]: p for p in cfg.get("parts", [])}
    frames = cfg.get("frames", {})
    for name, fr in frames.items():
        if not re.fullmatch(r"[a-z0-9][a-z0-9_]*", name) or name == ART:
            problems.append(f"frame name {name!r}: lower-case letters, digits and _ only, and not {ART!r}")
        src = fr.get("from")
        if src != ART and src not in frames:
            problems.append(f"{name}.from {src!r} is neither {ART!r} nor a frame")
        elif src != ART and list(frames).index(src) > list(frames).index(name):
            problems.append(f"{name} is edited from {src}, which is listed after it: list frames in drawing order")
        if not fr.get("change"):
            problems.append(f"{name}: 'change' is empty")
        for p in fr.get("moves", []):
            if p not in parts:
                problems.append(f"{name}.moves: {p!r} is not a part")
        if fr.get("smear") and cfg.get("motion", "slow") != "fast":
            problems.append(f"{name}: 'smear' needs \"motion\": \"fast\" (slow motion gets no afterimages)")
    for p in parts.values():
        if "box" in p and len(p["box"]) != 4:
            problems.append(f"part {p['name']}: box must be [x0, y0, x1, y1]")
        if not p.get("describe"):
            problems.append(f"part {p['name']}: 'describe' is empty")
    if problems:
        raise SystemExit("loop.json:\n  " + "\n  ".join(problems))
    cfg["_parts"] = parts
    return cfg


def load_1024(path):
    """Any image -> RGBA on the work canvas. Image-model edits come back as the input upscaled (1254),
    so resizing them back lines them up with the input pixel for pixel."""
    im = Image.open(path).convert("RGBA")
    if im.size != (N, N):
        im = im.resize((N, N), Image.LANCZOS)
    return im


def key_green(im):
    """Green screen -> transparent, and green spill removed.

    Sometimes the image tool returns the edit already transparent; then only the spill is removed. Semi-
    transparent pixels (motion smears, soft edges) that came over green keep an olive cast after the
    usual G = max(R, B), so they are pulled to the mean of R and B, back to grey. Opaque pixels keep
    their green: a green tie or book cover is real content.
    """
    a = np.array(im).astype(np.float32)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    greenness = g - np.maximum(r, b)
    if (a[..., 3] < 250).mean() <= 0.2:
        a[..., 3] = np.clip((GREEN_HI - greenness) / (GREEN_HI - GREEN_LO), 0.0, 1.0) * 255
    a[..., 1] = np.where(greenness > 0, np.maximum(r, b), g)
    semi = a[..., 3] < 230
    a[..., 1] = np.where(semi, np.minimum(a[..., 1], (r + b) / 2), a[..., 1])
    return Image.fromarray(a.clip(0, 255).astype(np.uint8))


def to_green(im):
    """Transparent frame -> RGB on flat #00FF00: the input the image model gets."""
    bg = Image.new("RGBA", im.size, (0, 255, 0, 255))
    bg.alpha_composite(im.convert("RGBA"))
    return bg.convert("RGB")


def lines(im):
    a = np.array(im).astype(int)
    return (a[..., :3].mean(axis=2) < LINE_MAX) & (a[..., 3] > 128)


def local_shift(ref, cur, box, search=SHIFT_SEARCH):
    """Best offset (dx, dy) of cur's outlines against ref's inside box, and their overlap there.

    (dx, dy) is how far cur moved. Ties go to the smaller move, so a part that did not move reads (0, 0)."""
    x0, y0, x1, y1 = box
    r = ref[y0:y1, x0:x1]
    best = (0, 0, -1.0)
    for dy in range(-search, search + 1):
        for dx in range(-search, search + 1):
            c = cur[y0 + dy:y1 + dy, x0 + dx:x1 + dx]
            if c.shape != r.shape:
                continue
            u = np.logical_or(r, c).sum()
            s = np.logical_and(r, c).sum() / u if u else 0.0
            if s > best[2] or (s == best[2] and abs(dx) + abs(dy) < abs(best[0]) + abs(best[1])):
                best = (dx, dy, s)
    return best


def premul(a):
    p = a.astype(np.float32)
    p[..., :3] *= p[..., 3:4] / 255
    return p


def unpremul(p):
    out = p.copy()
    al = np.maximum(p[..., 3:4], 1e-3)
    out[..., :3] = np.where(p[..., 3:4] > 0.5, p[..., :3] * 255 / al, 0)
    return out.clip(0, 255).astype(np.uint8)


def box_mask(boxes, pad=0):
    m = np.zeros((N, N), bool)
    for x0, y0, x1, y1 in boxes:
        m[max(0, y0 - pad):y1 + pad, max(0, x0 - pad):x1 + pad] = True
    return m


def parse_select(text):
    """'B-R>5' -> function(rgba float array) -> bool mask: channel B minus channel R above 5."""
    m = re.fullmatch(r"([RGB])-([RGB])>(-?\d+)", text.replace(" ", ""))
    if not m:
        raise SystemExit(f"select {text!r}: expected a channel difference like B-R>5")
    i, j, k = "RGB".index(m.group(1)), "RGB".index(m.group(2)), int(m.group(3))
    return lambda a: a[..., i] > a[..., j] + k


def path(work, *parts):
    return os.path.join(work, *parts)


def save_json(p, data):
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    with open(p, "w") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
        f.write("\n")


def load_json(p, default=None):
    if not os.path.exists(p):
        return default
    with open(p) as f:
        return json.load(f)
