"""Make every frame use the reference frame's exact pixels wherever it is not meant to change.

Usage: python3 -I stabilize.py <workdir>

Reads matched/<frame>.png (run.py), writes stab/<frame>.png and stab/<frame>-mask.png (white = pixels kept
from this frame), stab/<ref>.png, and the overlay sprites (`erase`, `sprites`) into sprites/. Settings:
`stabilize` in loop.json and per frame `frames.<name>.stabilize` (references/loop-config.md).
Writes metrics/stabilize.json.

Each edit redraws the whole picture a little: lines wobble 1 px, colours move a level or two. The shift
check rejects real moves; this removes the rest, which at 16 fps reads as the whole character shimmering.
Per frame, the pixels kept from it are either
- "diff" (default): where it differs clearly from the reference (an arm, a turned page, a smear), or
- ellipses: only inside the given ellipses (eyes and brows of an expression frame).
With "diff", nothing new outside the reference silhouette is kept unless the frame names an `outside` zone
for it: a raised arm or a motion smear may extend past the outline, an echo of the head or body must not.
"""
import os
import sys

import numpy as np
from PIL import Image
from scipy.ndimage import binary_dilation, binary_fill_holes, binary_opening, gaussian_filter, label

sys.dont_write_bytecode = True  # no __pycache__ in the skill's folder
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import N, box_mask, load_config, parse_select, premul, save_json, unpremul  # noqa: E402
from cutout import cut  # noqa: E402

T = 40  # premultiplied difference (0-255) above which a pixel counts as really changed
MIN_AREA = 40  # changed blobs smaller than this are redraw noise
GROW = 4  # kept area grows this many px to take the anti-aliased edge along
FEATHER = 1.2  # blur of the kept area's edge
ERASE_GROW = 4  # an erased detail's mask grows this much to take its faint halo along
ERASE_ITER = 400  # diffusion steps that fill an erased detail from the colour around it

_yy, _xx = np.mgrid[0:N, 0:N].astype(np.float32)


def ellipse_mask(ellipses, feather):
    m = np.zeros((N, N), np.float32)
    for cx, cy, rx, ry in ellipses:
        d = np.sqrt(((_xx - cx) / rx) ** 2 + ((_yy - cy) / ry) ** 2)
        edge = 1 + feather / min(rx, ry)
        m = np.maximum(m, np.clip((edge - d) / (edge - 1), 0, 1))
    return m


def outside_ring(ref, cur, allowed, drop_cool):
    """Pixels outside the reference silhouette that this frame may not bring in: everything outside the
    allowed zones, and inside them (with drop_cool) cool-tinted pixels, which were echo lines."""
    outside = ref[..., 3] <= 128
    ring = outside & ~allowed
    if drop_cool:
        c = cur.astype(int)
        ring |= allowed & outside & (c[..., 2] > c[..., 0] + 5)
    return ring


def diff_mask(ref, cur, force, ring):
    """Soft mask of what really changed. Returns (mask, px the outside rule removed from it)."""
    diff = np.abs(premul(cur) - premul(ref)).max(axis=-1)
    changed = binary_opening(diff > T, iterations=1)
    lab, n = label(changed)
    if n:
        sizes = np.bincount(lab.ravel())
        changed = np.isin(lab, np.nonzero(sizes >= MIN_AREA)[0]) & changed
    changed = binary_dilation(changed, iterations=GROW)
    for x0, y0, x1, y1 in force:
        changed[y0:y1, x0:x1] = False
    if ring is None:
        return np.clip(gaussian_filter(changed.astype(np.float32), FEATHER), 0, 1), 0
    m = np.clip(gaussian_filter((changed & ~ring).astype(np.float32), FEATHER), 0, 1)
    m[ring] = 0  # again after the blur, or the soft edge brings a faint echo back
    return m, int((changed & ring & (cur[..., 3] > 40)).sum())


def erase(ref, box, select):
    """Remove a small detail drawn into the reference (a sweat drop on the cheek): fill it from the colour
    around it and return (cleaned image, the detail as a sprite cut to the box)."""
    x0, y0, x1, y1 = box
    a = ref.astype(np.float32)
    part = a[y0:y1, x0:x1]
    detail = binary_fill_holes(select(part) & (part[..., 3] > 0))
    lab, n = label(detail)
    if n > 1:
        detail = lab == np.bincount(lab.ravel())[1:].argmax() + 1
    if not detail.any():
        raise SystemExit(f"erase {box}: nothing in the box matches the selection")
    detail = binary_dilation(detail, iterations=ERASE_GROW)
    filled = part.copy()
    filled[detail] = part[~detail].mean(axis=0)
    for _ in range(ERASE_ITER):
        avg = (np.roll(filled, 1, 0) + np.roll(filled, -1, 0) + np.roll(filled, 1, 1) + np.roll(filled, -1, 1)) / 4
        filled[detail] = avg[detail]
    out = a.copy()
    out[y0:y1, x0:x1] = filled
    diff = np.abs(part[..., :3] - filled[..., :3]).max(axis=-1)
    sprite = part.copy()
    sprite[..., 3] = np.clip(diff / 60, 0, 1) * 255 * detail
    return out.clip(0, 255).astype(np.uint8), sprite.clip(0, 255).astype(np.uint8)


def main(work):
    cfg = load_config(work)
    st = cfg.get("stabilize", {})
    ref_name = st.get("ref") or next(iter(cfg["frames"]))
    out_dir = os.path.join(work, "stab")
    os.makedirs(out_dir, exist_ok=True)
    ref = np.array(Image.open(os.path.join(work, "matched", f"{ref_name}.png")).convert("RGBA"))
    base = ref
    for e in st.get("erase", []):
        base, sprite = erase(base, e["box"], parse_select(e["select"]))
        os.makedirs(os.path.join(work, "sprites"), exist_ok=True)
        Image.fromarray(sprite).save(os.path.join(work, "sprites", f"{e['name']}.png"))
        print(f"erased {e['name']} from {ref_name} at {e['box']} -> sprites/{e['name']}.png")
    Image.fromarray(base).save(os.path.join(out_dir, f"{ref_name}.png"))
    for sp in st.get("sprites", []):
        a = np.array(Image.open(os.path.join(work, "matched", f"{sp['frame']}.png")).convert("RGBA")).astype(np.float32)
        sprite, n = cut(a, sp["box"], sp["select"], sp.get("min_alpha", 0))
        os.makedirs(os.path.join(work, "sprites"), exist_ok=True)
        Image.fromarray(sprite).save(os.path.join(work, "sprites", f"{sp['name']}.png"))
        print(f"cut {sp['name']} from {sp['frame']} at {sp['box']} ({n} px) -> sprites/{sp['name']}.png")
    pb = premul(base)
    report = {"ref": ref_name, "frames": {}}
    for name, fr in cfg["frames"].items():
        if name == ref_name:
            continue
        s = fr.get("stabilize", {})
        cur = np.array(Image.open(os.path.join(work, "matched", f"{name}.png")).convert("RGBA"))
        keep = s.get("keep", "diff")
        outside = s.get("outside", [])
        dropped = 0
        if keep == "diff":
            ring = None if outside == "keep" else outside_ring(ref, cur, box_mask(outside), s.get("drop_cool_outside", False))
            m, dropped = diff_mask(ref, cur, st.get("force_ref", []) + s.get("force_ref", []), ring)
        else:  # the ellipses are the agent's explicit choice of what changes; they are kept as drawn
            m = ellipse_mask(keep["ellipses"], keep.get("feather", 10))
        out = unpremul(pb * (1 - m[..., None]) + premul(cur) * m[..., None])
        # Outside the mask take the reference's own pixels: the premultiplied round trip would make
        # nearly transparent edge pixels change colour from frame to frame.
        out = np.where((m == 0)[..., None], base, out)
        Image.fromarray(out).save(os.path.join(out_dir, f"{name}.png"))
        Image.fromarray((m * 255).astype(np.uint8)).save(os.path.join(out_dir, f"{name}-mask.png"))
        report["frames"][name] = {"mode": "diff" if keep == "diff" else "ellipses", "kept_share": round(float(m.mean()), 4),
                                  "outside_dropped_px": dropped}
        print(f"{name}: kept {m.mean() * 100:.1f}% of this frame ({report['frames'][name]['mode']})"
              + (f", dropped {dropped} px outside the silhouette" if dropped else ""))
    save_json(os.path.join(work, "metrics", "stabilize.json"), report)


if __name__ == "__main__":
    main(*sys.argv[1:])
