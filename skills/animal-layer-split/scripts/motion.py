"""Joints in motion: root layers that keep a turning part attached, and a check of how the joints look when parts turn.

Usage: python3 -I motion.py <workdir> <rig.json>    (writes motion-board.png and prints the gap report)

A part in front of its parent (an ear over the head) ends where it was cut. Turn it and one side of its base
lifts off the parent, opening a wedge of background: it looks detached. A part behind its parent (a tail
behind the body) does not have this problem, because the peel painted its hidden root.

So every part in front of its parent gets a root layer, <part>_root.png, stacked just behind the parent and
moved with the part (same bone). It is a flat patch of the parent's fur colour under the joint, only where
the parent is solid, so it never shows at rest; when the part turns, it fills the wedge as plain fur.
Tried and dropped: a strip copied into the part's own layer (it sits in front, so whatever swings past the
outline shows as a smear), and a root extended from the part's own edge pixels (it smears the dark outline).
Skinning the part's base to the parent bone, so the base does not move at all, is better still where the
engine has it; joint_<part>.png marks where.
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.dont_write_bytecode = True  # no __pycache__ in the skill's folder
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import grow, load_rig, root_parts, soft, stack_back_to_front  # noqa: E402

ANGLES = (-15, 15)  # degrees each jointed part is turned for the gap report and the board
REACH = 60  # px at 512 around the pivot that count as the joint


def root_layer(part, parent, joint, width):
    """Flat parent-fur patch under the joint, `width` px deep, feathered, only where the parent is solid."""
    own, par = np.array(part).astype(np.float32), np.array(parent).astype(np.float32)
    solid = own[..., 3] > 250
    # "solid" is > 250, like everywhere else: some exports never reach 255 (one fox maxed at 254, and a 255 test made no root)
    zone = grow(solid, width) & ~solid & (par[..., 3] > 250) & grow(joint, width)
    fur = zone & (par[..., :3].max(axis=2) >= 130)  # leave outline pixels out of the colour
    out = np.zeros(own.shape, np.float32)
    out[..., :3] = np.median(par[fur][:, :3], axis=0) if fur.any() else 128
    out[..., 3] = 255 * soft(zone, 1.5) * zone
    return Image.fromarray(np.rint(out.clip(0, 255)).astype(np.uint8))


def load_stack(work, rig):
    return {name: Image.open(os.path.join(work, "layers", f"{name}.png")).convert("RGBA")
            for name in stack_back_to_front(rig)}


def pivot(rig, part, images):
    """The part's pixels over its parent, averaged: an ear's base, a tail's hidden root. rig.json `pivot` overrides."""
    given = rig["parts"][part].get("pivot")
    if given:
        return float(given[0]), float(given[1])
    m = np.array(images[part])[..., 3] > 128
    over = m & (np.array(images[rig["parent"][part]])[..., 3] > 128)
    ys, xs = np.nonzero(over if over.sum() > 30 else m)
    return float(xs.mean()), float(ys.mean())


def posed(rig, images, part, angle, centre, with_root=True):
    """The whole stack with `part` (and its root) turned by `angle` degrees around `centre`."""
    out = Image.new("RGBA", next(iter(images.values())).size, (0, 0, 0, 0))
    for name in stack_back_to_front(rig):
        if name == f"{part}_root" and not with_root:
            continue
        im = images[name]
        if name in (part, f"{part}_root"):
            im = im.rotate(angle, resample=Image.BICUBIC, center=centre)
        out.alpha_composite(im)
    return out


def gaps(work, rig):
    """Per jointed part: background pixels opening between it and its parent when turned (worst of ANGLES)."""
    images = load_stack(work, rig)
    size = next(iter(images.values())).size[0]
    reach = REACH * size / 512
    yy, xx = np.mgrid[:size, :size]
    out = {}
    for part, parent in rig["parent"].items():
        c = pivot(rig, part, images)
        near = (xx - c[0]) ** 2 + (yy - c[1]) ** 2 < reach ** 2
        par = np.array(images[parent])[..., 3] > 128
        row = {"pivot": [round(c[0]), round(c[1])], "has_root": f"{part}_root" in images}
        for with_root in ((True, False) if row["has_root"] else (True,)):
            worst = 0
            for a in ANGLES:
                comp = posed(rig, images, part, a, c, with_root)
                moved = np.array(images[part].rotate(a, resample=Image.BICUBIC, center=c))[..., 3] > 128
                gap = (np.array(comp)[..., 3] <= 128) & near & grow(moved, 3) & grow(par, 3)
                worst = max(worst, int(gap.sum()))
            row["gap_px" if with_root else "gap_px_without_root"] = worst
        out[part] = row
    return out


def board(work, rig):
    """Every jointed part at ANGLES[0], 0 and ANGLES[1] around its pivot, cropped at the joint, on a green-grey
    background so gaps show. The eye check for joints: a wedge of background or a smear means look again."""
    images = load_stack(work, rig)
    size = next(iter(images.values())).size[0]
    half = round(REACH * size / 512)
    rows = []
    for part in rig["parent"]:
        c = pivot(rig, part, images)
        row = []
        for a in (ANGLES[0], 0, ANGLES[1]):
            comp = posed(rig, images, part, a, c)
            bg = Image.new("RGBA", comp.size, (90, 160, 90, 255))
            bg.alpha_composite(comp)
            tile = bg.crop((int(c[0] - half), int(c[1] - half), int(c[0] + half), int(c[1] + half)))
            tile = tile.resize((4 * half, 4 * half), Image.LANCZOS).convert("RGB")
            ImageDraw.Draw(tile).text((6, 6), f"{part} {a:+d}", fill=(255, 255, 255))
            row.append(tile)
        rows.append(row)
    if not rows:
        return
    w, h = rows[0][0].size
    sheet = Image.new("RGB", (w * 3, h * len(rows)), "white")
    for r, row in enumerate(rows):
        for i, tile in enumerate(row):
            sheet.paste(tile, (i * w, r * h))
    sheet.save(os.path.join(work, "motion-board.png"))


def make_roots(work, rig, layers, joints):
    """Write <part>_root.png for each part in front of its parent. `layers`: part -> RGBA uint8 array."""
    size = next(iter(layers.values())).shape[0]
    written = {}
    for part in root_parts(rig):
        width = round(rig["parts"][part].get("root", 16) * size / 512)
        im = root_layer(Image.fromarray(layers[part]), Image.fromarray(layers[rig["parent"][part]]), joints[part], width)
        im.save(os.path.join(work, "layers", f"{part}_root.png"))
        written[part] = int((np.array(im)[..., 3] > 0).sum())
    return written


if __name__ == "__main__":
    work, rig_path = sys.argv[1], sys.argv[2]
    rig = load_rig(rig_path)
    board(work, rig)
    for part, row in gaps(work, rig).items():
        print(part, row)
