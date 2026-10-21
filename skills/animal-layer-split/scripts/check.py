"""Measure every step and decide pass/fail. Eyeballing a contact sheet does not catch a 4 px drift; this does.

Usage: python3 -I check.py <workdir> <rig.json> [psd]

Writes <workdir>/metrics.json and prints one line per check, plus warnings that do not stop anything.
Exit code 1 if any check fails. Limits are in LIMITS below and explained in references/checks.md
(lengths are px at a 512 work size). run.py applies the same peel and part-map checks right after each edit.
"""
import os
import sys

import numpy as np
from PIL import Image, ImageFilter

sys.dont_write_bytecode = True  # no __pycache__ in the skill's folder
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (GREEN, REVEAL_MARGIN, components, edges, grow, iou, load_json, load_rig, read_seg, removed_mask,  # noqa: E402
                    save_json, stack_back_to_front)
import motion  # noqa: E402
from peel import measure  # noqa: E402

LIMITS = {
    "peel_global_shift_px": 1,  # whole-image offset the edit came back with (after resizing 1254 -> work size)
    "peel_drift_px": 1.0,  # local movement of anything that was not removed or revealed
    "peel_color_residual_main": 3.0,  # main colour's mean difference left after the colour offset (levels of 255)
    "peel_color_residual_worst": 8.0,  # same for every colour covering >= 3% of the kept flat pixels
    "peel_added_outside": 0.02,  # new character outside the previous silhouette, share of that silhouette
    "peel_removed_changed": 0.35,  # share of each removed part's area that must change (accepted steps: 0.57-0.99)
    "peel_kept_repainted": 0.01,  # share of the area that should stay put that changed anyway (accepted: 0-0.002)
    "partmap_silhouette_iou": 0.96,  # part map outline vs the image it was painted on
    "partmap_outside": 0.005,  # map colour outside that image's silhouette, share of the silhouette (accepted maps: 0)
    "partmap_part_share": 0.002,  # every part still present covers at least this share of the character
    "partmap_kept_area": 0.9,  # a part may not shrink below this share of its area in the previous map
    "stack_mean_diff": 3.0,  # layers stacked back up vs the original, mean RGB difference (levels)
    "stack_diff_over_30_pct": 3.0,  # share of pixels that differ by more than 30 levels
    "stack_outline_mismatch_pct": 1.0,  # share of the character whose alpha differs by more than 60
}
CHANGE_LEVEL = 40  # a pixel counts as changed when the blurred images differ by more than this in any channel


def gate(label, value, key, higher_is_better=False):
    limit = LIMITS[key]
    ok = value >= limit if higher_is_better else value <= limit
    return {"check": label, "value": value, "limit": (">= " if higher_is_better else "<= ") + str(limit), "pass": bool(ok)}


def edge_reach(size):
    return max(3, size // 128)  # silhouettes may differ by this much from resizing and soft edges


def blurred(a):
    """On the green background, blurred a little, so a removed part reads as changed but line re-rendering does not."""
    im = Image.new("RGBA", (a.shape[1], a.shape[0]), GREEN + (255,))
    im.alpha_composite(Image.fromarray(np.rint(a.clip(0, 255)).astype(np.uint8)))
    return np.array(im.convert("RGB").filter(ImageFilter.GaussianBlur(2))).astype(np.float32)


def peel_checks(rig, k, prev, cur, prev_masks):
    """What the edit for peel step k did, beyond alignment and colour: did it draw anything new outside the
    character, and did every part it should remove actually change? prev_masks is part map k-1."""
    size = prev.shape[0]
    pm, cm = prev[..., 3] > 128, cur[..., 3] > 128
    added = float((cm & ~grow(pm, edge_reach(size))).sum() / max(1, pm.sum()))
    out = [gate(f"peel step{k}: new character outside the previous silhouette", round(added, 4), "peel_added_outside")]
    diff = np.abs(blurred(prev) - blurred(cur)).max(axis=2) > CHANGE_LEVEL
    # A removed part counts as gone where its colours changed or where its own lines vanished. Lines alone matter
    # for a part the same colour as what is behind it: a white tail removed from a white body changed 0.27-0.32
    # of its area, but 0.76-0.81 of its lines vanished. A leg left in place: 0.00 either way.
    cur_edges = grow(edges(cur), 1)
    changed = {}
    for p in rig["peel"][k - 1]["remove"]:
        m = prev_masks[p]
        if m.any():
            lines = edges(prev) & m
            gone = float((lines & ~cur_edges).sum() / lines.sum()) if lines.any() else 0.0
            changed[p] = round(max(float(diff[m].mean()), gone), 2)
    if changed:
        p = min(changed, key=changed.get)
        out.append(gate(f"peel step{k}: least changed removed part ({p})", changed[p], "peel_removed_changed", True))
    # A redraw that stays inside the old silhouette (a new head drawn on a headless body) passes the checks above;
    # drift skips the tiles it repainted. So: how much of what should stay put changed at all?
    removed = np.zeros_like(pm)
    for p in rig["peel"][k - 1]["remove"]:
        removed |= prev_masks[p]
    keep = pm & cm & ~grow(removed, round(REVEAL_MARGIN * size / 512))
    repainted = round(float(diff[keep].mean()), 4) if keep.any() else 0.0
    out.append(gate(f"peel step{k}: kept area repainted", repainted, "peel_kept_repainted"))
    return out, {"added_outside": round(added, 4), "removed_changed": changed, "kept_repainted": repainted}


def partmap_checks(rig, k, masks, inside, step_alpha, prev_masks):
    """Part map k against the image it was painted on (step_alpha) and against part map k-1 (prev_masks).

    A failure counts only where this map shapes a layer: map 0 for every part, map k for the parts that are
    frontmost in step k (their full shape comes from it). Elsewhere the same finding is a warning."""
    size = step_alpha.shape[0]
    present = rig["step_parts"][k]
    used = set(present) if k == 0 else {p for p, s in rig["front_step"].items() if s == k}
    char = max(1, step_alpha.sum())
    painted = np.zeros_like(step_alpha)
    for m in masks.values():
        painted |= m
    outside = float((painted & ~grow(step_alpha, edge_reach(size))).sum() / char)
    out = [gate(f"partmap step{k}: silhouette IoU", round(iou(inside, step_alpha), 4), "partmap_silhouette_iou", True),
           gate(f"partmap step{k}: painted outside the silhouette", round(outside, 4), "partmap_outside")]
    warnings, numbers = [], {"outside": round(outside, 4), "share": {}, "kept_area": {}}

    share = {p: round(float(masks[p].sum() / char), 4) for p in present}
    numbers["share"] = share
    gated = [p for p in present if p in used]
    if gated:
        p = min(gated, key=share.get)
        out.append(gate(f"partmap step{k}: smallest part share ({p})", share[p], "partmap_part_share", True))
    warnings += [f"partmap step{k}: {p} covers only {share[p]:.2%} of the character (not used for its layer)"
                 for p in present if p not in used and share[p] < LIMITS["partmap_part_share"]]

    if prev_masks is not None:
        worst = None
        for p in present:
            if p not in prev_masks or not prev_masks[p].any():
                continue
            ratio = round(float(masks[p].sum() / prev_masks[p].sum()), 2)
            numbers["kept_area"][p] = ratio
            lost = prev_masks[p] & ~masks[p] & step_alpha
            gainers = [q for q in present if q != p and (masks[q] & lost).sum() > 0.25 * max(1, lost.sum())]
            if p in used or used & set(gainers):
                if worst is None or ratio < worst[1]:
                    worst = (p, ratio, gainers)
            elif ratio < LIMITS["partmap_kept_area"]:
                warnings.append(f"partmap step{k}: {p} kept only {ratio:.0%} of its area in step{k - 1}'s map, lost to "
                                f"{', '.join(gainers) or 'nothing'} (neither is used for a layer from this map)")
        if worst:
            p, ratio, gainers = worst
            out.append(gate(f"partmap step{k}: smallest area kept from step{k - 1} ({p}"
                            + (f", lost to {', '.join(gainers)}" if ratio < LIMITS["partmap_kept_area"] and gainers else "") + ")",
                            ratio, "partmap_kept_area", True))
    return out, warnings, numbers


def main(work, rig_path, psd=None):
    rig = load_rig(rig_path)
    order, n = rig["order"], len(rig["peel"])
    load = lambda p: np.array(Image.open(os.path.join(work, p)).convert("RGBA")).astype(np.float32)  # noqa: E731
    steps = [load(f"norm/step{i}.png") for i in range(n + 1)]
    size = steps[0].shape[0]
    checks, warnings, info = [], [], {}

    segs = {}
    for k in range(n):
        segs[k], inside = read_seg(os.path.join(work, "seg-raw", f"step{k}.png"), rig["step_parts"][k], rig["colors"], size)
        out, warn, numbers = partmap_checks(rig, k, segs[k], inside, steps[k][..., 3] > 128, segs.get(k - 1))
        checks += out
        warnings += warn
        info[f"partmap_step{k}"] = numbers

    for k in range(1, n + 1):
        prev, cur = steps[k - 1], steps[k]
        m = load_json(os.path.join(work, "metrics", f"peel-step{k}.json"), {})
        if m:
            checks.append(gate(f"peel step{k}: global shift px", max(abs(v) for v in m["global_shift_px"]), "peel_global_shift_px"))
            if m["raw_size"][0] != m["raw_size"][1]:
                checks.append({"check": f"peel step{k}: square output", "value": m["raw_size"], "limit": "square", "pass": False})
        # Recomputed from the images, with the removed parts (from the previous part map) masked out.
        r = measure(prev, cur, removed_mask(os.path.join(work, "seg-raw", f"step{k - 1}.png"), rig, k - 1, size))
        checks.append(gate(f"peel step{k}: drift px ({r['drift_tiles_measured']} tiles)", r["drift_px"], "peel_drift_px"))
        checks.append(gate(f"peel step{k}: main colour residual", r["color_residual_main"], "peel_color_residual_main"))
        checks.append(gate(f"peel step{k}: worst colour residual", r["color_residual_worst"], "peel_color_residual_worst"))
        out, numbers = peel_checks(rig, k, prev, cur, segs[k - 1])
        checks += out
        info[f"peel_step{k}"] = {**m, **r, **numbers}

    comp_path = os.path.join(work, "layers", "composite.png")
    if os.path.exists(comp_path):
        orig, comp = steps[0], load("layers/composite.png")
        both = (orig[..., 3] > 250) & (comp[..., 3] > 250)
        diff = np.abs(orig[..., :3] - comp[..., :3]).max(axis=2)
        char = orig[..., 3] > 128
        checks.append(gate("stack vs original: mean diff", round(float(diff[both].mean()), 2), "stack_mean_diff"))
        checks.append(gate("stack vs original: % px diff > 30", round(float(100 * (diff[both] > 30).mean()), 2), "stack_diff_over_30_pct"))
        checks.append(gate("stack vs original: % outline mismatch",
                           round(float(100 * (np.abs(orig[..., 3] - comp[..., 3]) > 60).sum() / char.sum()), 2), "stack_outline_mismatch_pct"))
        layers = {}
        for p in order:
            a = np.array(Image.open(os.path.join(work, "layers", f"{p}.png")))[..., 3] > 128
            comps = components(a)
            layers[p] = {"pixels": int(a.sum()), "pieces": len(comps), "largest_piece_share": round(len(comps[0]) / a.sum(), 4) if comps else 0}
        info["layers"] = layers
        info["layer_stats"] = load_json(os.path.join(work, "layers", "stats.json"), {})
        # Reported, not gated yet: background opening at each joint when the part turns (see motion.py)
        info["joint_gaps"] = motion.gaps(work, rig)
    else:
        checks.append({"check": "layers built", "value": False, "limit": "layers/composite.png", "pass": False})

    if psd:
        from write_psd import read_layers
        names = [name for name, _, _ in read_layers(psd)]
        checks.append({"check": "psd: layer order bottom to top", "value": names, "limit": stack_back_to_front(rig),
                       "pass": names == stack_back_to_front(rig)})

    ok = all(c["pass"] for c in checks)
    save_json(os.path.join(work, "metrics.json"), {"pass": ok, "checks": checks, "warnings": warnings, "info": info, "limits": LIMITS})
    for c in checks:
        print(f"{'PASS' if c['pass'] else 'FAIL'}  {c['check']}: {c['value']} (limit {c['limit']})")
    for w in warnings:
        print(f"WARN  {w}")
    for part, g in info.get("joint_gaps", {}).items():
        print(f"INFO  joint {part}: {g['gap_px']} px of background when turned {motion.ANGLES} deg"
              + (f" ({g['gap_px_without_root']} without its root)" if "gap_px_without_root" in g else "") + "; see motion-board.png")
    print("ALL CHECKS PASS" if ok else "SOME CHECKS FAIL: see references/failure-modes.md")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main(*sys.argv[1:]) else 1)
