"""Shared helpers: config, green-screen keying, masks, alignment.

Every script in this folder imports from here, so they all key, resize and align the same way.
"""
import json
import os
import re
from collections import deque

import numpy as np
from PIL import Image, ImageFilter

CODEX_INPUT = 1024  # side of the green-screen image handed to the image model
GREEN = (0, 255, 0)
GREEN_LO, GREEN_HI = 30.0, 130.0  # greenness (G - max(R, B)) in this band becomes a soft edge

# Part-map colours the prompts may use. Names go into the prompt next to the hex code.
PALETTE = {
    "#FF0000": "red", "#0000FF": "blue", "#00FFFF": "cyan", "#FFFF00": "yellow",
    "#FF00FF": "magenta", "#FFFFFF": "white", "#FF8000": "orange", "#8000FF": "purple",
    "#808080": "grey", "#0080FF": "azure", "#FF80C0": "pink",
}
MIN_PALETTE_DISTANCE = 120  # RGB distance between any two part colours, and from the green background
SEG_MAX_DIST = 90  # part-map pixels further than this from every palette colour are "unknown" (lines, blur)
REVEAL_MARGIN = 12  # px (at 512) around a removed part where an edit is expected to paint new content


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def load_rig(path):
    """Read rig.json and derive the peel bookkeeping. See references/rig-config.md for the format."""
    with open(path) as f:
        rig = json.load(f)
    rig.setdefault("size", 512)
    parts, peel, base = rig["parts"], rig["peel"], rig["base"]
    order = [p for step in peel for p in step["remove"]] + [base]  # front to back
    missing = set(parts) - set(order)
    if missing or len(order) != len(set(order)) or set(order) != set(parts):
        raise SystemExit(f"rig.json: every part must appear exactly once in peel[].remove or base (problem: {sorted(missing) or order})")
    for name in parts:
        if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
            raise SystemExit(f"rig.json: part name {name!r} must be lower_snake_case ASCII (it becomes a PSD layer name)")
    rig["order"] = order
    # Part removed at peel step k+1 is frontmost in step k: its full shape comes from part map k.
    rig["front_step"] = {p: k for k, step in enumerate(peel) for p in step["remove"]}
    rig["step_parts"] = {k: order[sum(len(s["remove"]) for s in peel[:k]):] for k in range(len(peel))}
    rig["colors"] = {p: hex_rgb(parts[p]["color"]) for p in parts}
    rig["parent"] = {p: parts[p]["parent"] for p in parts if parts[p].get("parent")}
    for p, parent in rig["parent"].items():
        if parent not in parts:
            raise SystemExit(f"rig.json: {p}.parent {parent!r} is not a part")
    for p in parts:
        if parts[p].get("seam", "keep") not in ("blend", "keep"):
            raise SystemExit(f"rig.json: {p}.seam must be \"blend\" or \"keep\"")
        if not (isinstance(parts[p].get("root", 16), int) and parts[p].get("root", 16) >= 0):
            raise SystemExit(f"rig.json: {p}.root must be a whole number of px (0 for no root)")
        if "pivot" in parts[p] and not (isinstance(parts[p]["pivot"], list) and len(parts[p]["pivot"]) == 2):
            raise SystemExit(f"rig.json: {p}.pivot must be [x, y] in work-size px")
    return rig


def root_parts(rig):
    """Parts that get a root layer: in front of their parent, and `root` not set to 0."""
    order = rig["order"]
    return [p for p, parent in rig["parent"].items()
            if order.index(p) < order.index(parent) and rig["parts"][p].get("root", 16) > 0]


def stack_back_to_front(rig):
    """Layer names from the back: each part's root goes just behind its parent. This is the PSD order too."""
    roots = root_parts(rig)
    out = []
    for p in reversed(rig["order"]):
        out += [f"{child}_root" for child in roots if rig["parent"][child] == p]
        out.append(p)
    return out


def check_palette(rig):
    problems = []
    cols = rig["colors"]
    for p, c in cols.items():
        if rig["parts"][p]["color"].upper() not in PALETTE:
            problems.append(f"{p}: {rig['parts'][p]['color']} is not in the palette {list(PALETTE)}")
        if np.linalg.norm(np.subtract(c, GREEN)) < MIN_PALETTE_DISTANCE:
            problems.append(f"{p}: colour too close to the green background")
    names = list(cols)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if np.linalg.norm(np.subtract(cols[a], cols[b])) < MIN_PALETTE_DISTANCE:
                problems.append(f"{a} and {b}: colours too close to tell apart")
    return problems


def key_green(rgb):
    """Green screen -> RGBA with soft edges and the green spill removed from edge pixels."""
    rgb = rgb.astype(np.float32)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    greenness = g - np.maximum(r, b)
    alpha = np.clip((GREEN_HI - greenness) / (GREEN_HI - GREEN_LO), 0.0, 1.0)
    rgb[..., 1] = np.where(greenness > 0, np.maximum(r, b), g)
    return np.dstack([rgb, alpha * 255]).clip(0, 255).astype(np.uint8)


def components(mask, min_size=1):
    """4-connected components, largest first, as lists of (y, x)."""
    h, w = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    comps = []
    for y0, x0 in zip(*np.nonzero(mask)):
        if seen[y0, x0]:
            continue
        comp, q = [], deque([(y0, x0)])
        seen[y0, x0] = True
        while q:
            y, x = q.popleft()
            comp.append((y, x))
            for ny, nx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    q.append((ny, nx))
        if len(comp) >= min_size:
            comps.append(comp)
    return sorted(comps, key=len, reverse=True)


def keep_main(mask, min_share=0.01):
    """Drop specks: keep components at least min_share of the largest one (characters may have separate pieces)."""
    comps = components(mask)
    keep = np.zeros_like(mask, dtype=bool)
    if comps:
        for comp in comps:
            if len(comp) < min_share * len(comps[0]):
                break
            ys, xs = zip(*comp)
            keep[list(ys), list(xs)] = True
    return keep


def to_rgba(path):
    """Codex output (green screen, or sometimes already transparent) -> clean RGBA."""
    im = Image.open(path)
    a = np.array(im.convert("RGBA"))
    if a[..., 3].min() == 255:
        a = key_green(np.array(im.convert("RGB")))
    a[~keep_main(a[..., 3] > 128) & (a[..., 3] >= 128), 3] = 0
    return a


def on_green(rgba):
    g = Image.new("RGBA", (rgba.shape[1], rgba.shape[0]), GREEN + (255,))
    g.alpha_composite(Image.fromarray(rgba))
    return g.convert("RGB")


def shift(arr, dx, dy):
    out = np.zeros_like(arr)
    h, w = arr.shape[:2]
    ys, yd = (slice(0, h - dy), slice(dy, h)) if dy >= 0 else (slice(-dy, h), slice(0, h + dy))
    xs, xd = (slice(0, w - dx), slice(dx, w)) if dx >= 0 else (slice(-dx, w), slice(0, w + dx))
    out[yd, xd] = arr[ys, xs]
    return out


def iou(a, b):
    u = np.logical_or(a, b).sum()
    return float(np.logical_and(a, b).sum() / u) if u else 1.0


def grow(mask, r):
    return np.array(Image.fromarray(mask.astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(2 * r + 1))) > 127


def shrink(mask, r):
    return np.array(Image.fromarray(mask.astype(np.uint8) * 255).filter(ImageFilter.MinFilter(2 * r + 1))) > 127


def soft(mask, r):
    return np.array(Image.fromarray(mask.astype(np.uint8) * 255).filter(ImageFilter.GaussianBlur(r))).astype(np.float32) / 255


def lum(a):
    return a[..., :3].astype(np.float32) @ np.array([0.299, 0.587, 0.114], np.float32)


def edges(a, threshold=40):
    """Line/edge pixels, used to measure drift. Works with or without dark outlines."""
    l = lum(a)
    gx = np.abs(np.diff(l, axis=1, append=l[:, -1:]))
    gy = np.abs(np.diff(l, axis=0, append=l[-1:, :]))
    return (np.maximum(gx, gy) > threshold) & (a[..., 3] > 200)


def tile_drift(prev, cur, keep, tile=64, search=4, min_edges=80, min_gain=0.05):
    """How far the parts that should stay put moved: best local shift of the edge map, per tile.

    Tiles whose best match is poor (the content was removed or repainted, not moved) are skipped:
    a part that drifted still matches well, just at a non-zero offset. A shift only counts if it matches
    clearly better than no shift (min_gain), because the model re-renders lines slightly softer and
    32 px tiles then wobble by a pixel even where nothing moved.
    Returns (max drift in px, worst tile [x, y, dx, dy] where (dx, dy) is how far cur moved, tiles measured)."""
    pe, ce = edges(prev) & keep, edges(cur)
    h, w = keep.shape
    worst, measured = (0.0, None), 0
    for y0 in range(search, h - tile - search, tile):
        for x0 in range(search, w - tile - search, tile):
            r = pe[y0:y0 + tile, x0:x0 + tile]
            if r.sum() < min_edges:
                continue
            k = keep[y0:y0 + tile, x0:x0 + tile]
            zero = iou(r, ce[y0:y0 + tile, x0:x0 + tile] & k)
            best = (zero, 0, 0)
            for dy in range(-search, search + 1):
                for dx in range(-search, search + 1):
                    s = iou(r, ce[y0 + dy:y0 + dy + tile, x0 + dx:x0 + dx + tile] & k)
                    if s > best[0] or (s == best[0] and abs(dx) + abs(dy) < abs(best[1]) + abs(best[2])):
                        best = (s, dx, dy)
            if best[0] < 0.5:
                continue
            measured += 1
            if best[0] - zero < min_gain:
                continue
            d = float(max(abs(best[1]), abs(best[2])))  # px in either direction: a diagonal 1 px move is 1, not 1.41
            if d > worst[0]:
                worst = (d, [x0, y0, best[1], best[2]])
    return worst[0], worst[1], measured


def read_seg(path, parts, colors, size):
    """Part map -> one mask per part. Nearest palette colour per pixel; unknown pixels take their neighbours' majority."""
    im = Image.open(path)
    a = np.array(im.convert("RGBA"))
    if a[..., 3].min() == 255:
        a = key_green(np.array(im.convert("RGB")))
    a = np.array(Image.fromarray(a).resize((size, size), Image.BOX)).astype(np.float32)
    cols = np.array([colors[p] for p in parts], np.float32)
    dist = np.linalg.norm(a[..., None, :3] - cols[None, None], axis=3)
    label = dist.argmin(axis=2)
    label[(dist.min(axis=2) > SEG_MAX_DIST) | (a[..., 3] < 128)] = -1
    inside = a[..., 3] > 128
    for _ in range(8):
        unknown = inside & (label < 0)
        if not unknown.any():
            break
        votes = np.zeros(label.shape + (len(parts),), np.int32)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                sh = np.roll(label, (dy, dx), axis=(0, 1))
                for k in range(len(parts)):
                    votes[..., k] += sh == k
        best = votes.argmax(axis=2)
        fill = unknown & (votes.max(axis=2) > 0)
        label[fill] = best[fill]
    min_speck = int(80 * (size / 512) ** 2)
    out = {}
    for k, p in enumerate(parts):
        keep = np.zeros(label.shape, bool)
        for comp in components(label == k, min_speck):
            ys, xs = zip(*comp)
            keep[list(ys), list(xs)] = True
        out[p] = keep
    return out, inside


def removed_mask(seg_path, rig, k, size):
    """Where peel step k+1 is allowed to change things: the parts it removes, from part map k, plus a margin."""
    masks, _ = read_seg(seg_path, rig["step_parts"][k], rig["colors"], size)
    removed = np.zeros((size, size), bool)
    for p in rig["peel"][k]["remove"]:
        removed |= masks[p]
    return grow(removed, round(REVEAL_MARGIN * size / 512))


def save_json(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path) as f:
        return json.load(f)
