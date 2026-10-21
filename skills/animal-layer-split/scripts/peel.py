"""Conversions between peel steps (the image model removes one part per step, front to back).

Usage:
  python3 -I peel.py prep <codex output or work-size image> <next codex input, 1024 green screen>
  python3 -I peel.py norm <codex output> <previous step> <output> [metrics.json] [changed-mask.png]

An image edit comes back as the input upscaled to 1254x1254, so resizing it to the work size lines it up
with the previous step. norm confirms that with a +-3 px search, then shifts the colours back onto the
previous step: every edit drifts 3-7 levels darker or lighter, and uncorrected the layers get darker step by step.

The colour offset and the drift are measured only where nothing should change. changed-mask.png (white =
the removed parts and a margin, from the previous step's part map; run.py writes it) keeps the revealed
area out: a light head replaced by a darker body is new content, and counting it as drift shifts the
whole image and compounds step after step. Without the mask, only brightness separates the two.
Only the mean is shifted. Scaling the spread too lets the dominant colour decide the factor and pushes
small colours (pink ear insides, eye highlights) visibly off.
"""
import os
import sys

import numpy as np
from PIL import Image

sys.dont_write_bytecode = True  # no __pycache__ in the skill's folder
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import CODEX_INPUT, edges, grow, iou, lum, on_green, save_json, shift, tile_drift, to_rgba  # noqa: E402

SEARCH = 3
SAME_LUM = 25  # pixels whose brightness differs more than this are content changes, not colour drift


def prep(src, out):
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    on_green(to_rgba(src)).resize((CODEX_INPUT, CODEX_INPUT), Image.LANCZOS).save(out)


def color_residual(prev, cur, same):
    """Colour difference left after the offset, per colour: (main colour, worst colour) in levels of 255.

    The offset is one shift for the whole image, so a colour the edit drifted differently shows up here.
    Only flat fill counts (lines come back softer, which is not a colour drift); colours are 32-level bins
    covering >= 3% of those pixels; "main" is the largest bin, which most seams between layers run through."""
    flat = same & ~grow(edges(prev) | edges(cur), 2)
    keys = (prev[flat][:, :3].astype(np.int32) >> 5) @ np.array([64, 8, 1])
    diff = cur[flat][:, :3] - prev[flat][:, :3]
    bins = [(int((keys == k).sum()), float(np.abs(diff[keys == k].mean(axis=0)).max())) for k in np.unique(keys)]
    bins = [b for b in bins if b[0] >= 0.03 * len(keys)]
    if not bins:
        return 0.0, 0.0
    return max(bins)[1], max(r for _, r in bins)


def stable(prev, cur, changed):
    """Pixels both steps have and the edit was not supposed to touch."""
    keep = (prev[..., 3] > 250) & (cur[..., 3] > 250)
    return keep & ~changed if changed is not None else keep


def measure(prev, cur, changed):
    """Drift and colour residual of an aligned, colour-matched step. Shared with check.py."""
    keep = stable(prev, cur, changed)
    scale = prev.shape[0] / 512
    drift, where, tiles = tile_drift(prev, cur, keep, tile=round(64 * scale), min_edges=round(80 * scale ** 2))
    main_res, worst_res = color_residual(prev, cur, keep & (np.abs(lum(prev) - lum(cur)) < SAME_LUM))
    return {"color_residual_main": round(main_res, 2), "color_residual_worst": round(worst_res, 2),
            "drift_px": round(drift, 2), "drift_tile": where, "drift_tiles_measured": tiles}


def norm(src, prev_path, out, metrics_path=None, changed_path=None):
    raw = Image.open(src)
    prev = np.array(Image.open(prev_path).convert("RGBA")).astype(np.float32)
    size = prev.shape[1], prev.shape[0]
    changed = np.array(Image.open(changed_path).convert("L")) > 127 if changed_path else None
    cur = np.array(Image.fromarray(to_rgba(src)).resize(size, Image.LANCZOS)).astype(np.float32)
    pm, cm = prev[..., 3] > 128, cur[..., 3] > 128
    best = max(((dx, dy) for dy in range(-SEARCH, SEARCH + 1) for dx in range(-SEARCH, SEARCH + 1)),
               key=lambda d: (iou(pm, shift(cm, *d)), -abs(d[0]) - abs(d[1])))
    cur = shift(cur, *best)
    same = stable(prev, cur, changed) & (np.abs(lum(prev) - lum(cur)) < SAME_LUM)
    offset = prev[same][:, :3].mean(axis=0) - cur[same][:, :3].mean(axis=0)
    cur[..., :3] += offset
    saved = np.rint(cur.clip(0, 255)).astype(np.uint8)  # round, do not truncate: truncating darkens every step by half a level
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    Image.fromarray(saved).save(out)
    cur = saved.astype(np.float32)  # measure what was saved, so the numbers match check.py
    m = {"raw_size": list(raw.size), "global_shift_px": list(best), "color_offset": [round(float(v), 2) for v in offset],
         "masked": changed is not None, **measure(prev, cur, changed)}
    if metrics_path:
        save_json(metrics_path, m)
    print(f"{os.path.basename(out)}: raw {raw.size[0]}x{raw.size[1]}, shift {best}, colour offset {m['color_offset']}, "
          f"residual main {m['color_residual_main']} worst {m['color_residual_worst']}, "
          f"drift {m['drift_px']} px over {m['drift_tiles_measured']} tiles", flush=True)
    return m


if __name__ == "__main__":
    {"prep": prep, "norm": norm}[sys.argv[1]](*sys.argv[2:])
