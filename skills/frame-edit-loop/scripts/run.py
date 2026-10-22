"""Draw every frame in loop.json, one image edit at a time, and redo any edit where a locked part moved.

Usage: python3 -I run.py <workdir> [--retries N] [--model M] [--offline] [--only a,b]

For each frame, in the order loop.json lists them:
  1. edit in/<from>.png with prompts/<frame>.txt -> raw/<frame>.png (codex_edit.py)
  2. shift check against in/<from>.png (shift.py); a frame with shift goes to rejected/<frame>-tryN.png
     and is redrawn, up to --retries times (default 5), then the run stops
  3. keyed/<frame>.png   resized back to 1024, green keyed, spill and faint specks removed
  4. matched/<frame>.png colours matched to the colour reference (`color` in loop.json), then `patch`
  5. in/<frame>.png      matched frame on green: the input for frames edited from this one
Resumable: a frame whose raw image exists is not redrawn, only re-checked and re-processed, so steps 3-5
always reflect the current loop.json. --offline never calls the image model (a missing raw image stops
the run). --only redraws nothing but the named frames (their raw images must have been moved aside).
Writes metrics/frames.json.
"""
import argparse
import os
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy.ndimage import binary_dilation, label, maximum

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True  # no __pycache__ in the skill's folder
sys.path.insert(0, HERE)
import prompts  # noqa: E402
from common import ART, MIN_LINE_PX, key_green, lines, load_1024, load_config, save_json, to_green  # noqa: E402
from shift import describe, measure  # noqa: E402

SAME = 30  # a pixel counts as "the same thing" in two frames when no channel differs by more than this
SPECK_ALPHA = 32  # a separate blob whose strongest pixel is fainter than this is keying noise
FLAT_EDGE = 12  # luminance step between neighbours above which a pixel is a line or an edge, not flat fill
COLOR_RESIDUAL_MAX = 2.0  # tint left on unchanged flat fill after matching, in levels (see references/checks.md)


def color_stats(a, same, box):
    x0, y0, x1, y1 = box
    r = a[y0:y1, x0:x1]
    px = r[(r[..., 3] > 200) & same[y0:y1, x0:x1]][:, :3]
    return px.mean(axis=0), px.std(axis=0)


def match_color(ref, a, box):
    """Pull a frame's colours onto the reference: per channel mean and spread, fitted only on pixels both
    frames have and that show the same thing there (new content, smears, sweat do not count).
    Returns (matched array, mean before, target mean, tint left after)."""
    same = (np.abs(a - ref).max(axis=-1) < SAME) & (ref[..., 3] > 200)
    target_mean, target_std = color_stats(ref, same, box)
    mean, std = color_stats(a, same, box)
    out = a.copy()
    out[..., :3] = (out[..., :3] - mean) / std * target_std + target_mean
    out = out.clip(0, 255).astype(np.uint8)
    return out, mean, target_mean, tint(ref, out.astype(np.float32))


def tint(ref, a):
    """How far a frame's colours still sit off the reference: per channel, the mean signed difference over
    flat fill that shows the same thing in both (lines re-render softer, which is not a tint); the worst
    channel. This is what makes a loop flash warmer or colder when the frames alternate."""
    lum = ref[..., :3] @ np.array([0.299, 0.587, 0.114], np.float32)
    edge = np.maximum(np.abs(np.diff(lum, axis=1, append=lum[:, -1:])), np.abs(np.diff(lum, axis=0, append=lum[-1:, :])))
    flat = ~binary_dilation(edge > FLAT_EDGE, iterations=2)
    same = (np.abs(a - ref).max(axis=-1) < SAME) & (ref[..., 3] > 200) & (a[..., 3] > 200) & flat
    return float(np.abs((a[..., :3] - ref[..., :3])[same].mean(axis=0)).max())


def drop_specks(im):
    """Remove faint separate blobs the keying leaves where the green came back slightly off (alpha 1-2,
    scattered over the background). Real separate pieces (a smear copy, a drop in the air) are stronger."""
    a = np.array(im)
    lab, n = label(a[..., 3] > 0)
    if n > 1:
        peak = maximum(a[..., 3], lab, index=np.arange(1, n + 1))
        faint = np.isin(lab, np.nonzero(peak < SPECK_ALPHA)[0] + 1)
        a[faint] = 0
    return Image.fromarray(a), (int(faint.sum()) if n > 1 else 0)


def patch(frame, src, box, feather):
    """Copy a region from another frame over this one, feathered (box drawn by PIL: x1, y1 included)."""
    mask = Image.new("L", frame.size, 0)
    ImageDraw.Draw(mask).rectangle(tuple(box), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(feather))
    return Image.composite(src, frame, mask)


def process(cfg, work, name, color_ref):
    """raw -> keyed -> matched (+ patch) -> in/<name>.png. Returns (colour numbers, faint speck px removed)."""
    fr = cfg["frames"][name]
    keyed, specks = drop_specks(key_green(load_1024(os.path.join(work, "raw", f"{name}.png"))))
    keyed.save(os.path.join(work, "keyed", f"{name}.png"))
    color = cfg.get("color", {})
    info = {}
    if name == color.get("ref", ART):
        matched = keyed
    else:
        box = color.get("box", [0, 0, 1024, 1024])
        arr, before, target, residual = match_color(color_ref, np.array(keyed).astype(np.float32), box)
        matched = Image.fromarray(arr)
        info = {"mean_before": [round(float(v), 1) for v in before], "mean_target": [round(float(v), 1) for v in target],
                "tint_before": round(tint(color_ref, np.array(keyed).astype(np.float32)), 2),
                "residual": round(residual, 2), "pass": residual <= COLOR_RESIDUAL_MAX}
    if fr.get("patch"):
        p = fr["patch"]
        src = Image.open(os.path.join(work, "matched", f"{p['from']}.png")).convert("RGBA")
        matched = patch(matched, src, p["box"], p.get("feather", 3))
    matched.save(os.path.join(work, "matched", f"{name}.png"))
    to_green(matched).save(os.path.join(work, "in", f"{name}.png"))
    return info, specks


def edit(work, name, fr, model):
    args = [work, os.path.join("prompts", f"{name}.txt"), os.path.join("in", f"{fr['from']}.png"), os.path.join("raw", f"{name}.png")]
    args += [model] if model else []
    args += ["--ref", fr["reference"]["image"]] if fr.get("reference") else []
    return subprocess.run([sys.executable, "-I", os.path.join(HERE, "codex_edit.py"), *args]).returncode


def reject(work, name, why):
    os.makedirs(os.path.join(work, "rejected"), exist_ok=True)
    n = len([f for f in os.listdir(os.path.join(work, "rejected")) if f.startswith(f"{name}-try")])
    dst = os.path.join(work, "rejected", f"{name}-try{n + 1}.png")
    shutil.move(os.path.join(work, "raw", f"{name}.png"), dst)
    print(f"REJECTED {name} ({why}); kept as {os.path.relpath(dst, work)}", flush=True)


def check_boxes(cfg, work):
    art = lines(Image.open(os.path.join(work, "keyed", "art.png")).convert("RGBA"))
    bad = []
    for p in cfg["parts"]:
        if "box" in p:
            x0, y0, x1, y1 = p["box"]
            n = int(art[y0:y1, x0:x1].sum())
            if n < MIN_LINE_PX:
                bad.append(f"{p['name']}: {n} outline px in its box (needs {MIN_LINE_PX}); move the box onto the part's outlines")
    if bad:
        raise SystemExit("locked parts that cannot be measured:\n  " + "\n  ".join(bad))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work")
    ap.add_argument("--retries", type=int, default=5)
    ap.add_argument("--model")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--only")
    a = ap.parse_args()
    work = a.work
    cfg = load_config(work)
    for d in ("raw", "keyed", "matched", "in", "metrics"):
        os.makedirs(os.path.join(work, d), exist_ok=True)
    if not os.path.exists(os.path.join(work, "in", f"{ART}.png")):
        raise SystemExit("run prep.py first")
    check_boxes(cfg, work)
    prompts.main(work)
    shutil.copyfile(os.path.join(work, "keyed", f"{ART}.png"), os.path.join(work, "matched", f"{ART}.png"))
    color_name = cfg.get("color", {}).get("ref", ART)
    only = set(a.only.split(",")) if a.only else None
    report = {}
    color_ref = None
    for name, fr in cfg["frames"].items():
        if color_ref is None and (color_name == ART or color_name in report):
            color_ref = np.array(Image.open(os.path.join(work, "matched", f"{color_name}.png")).convert("RGBA")).astype(np.float32)
        if color_ref is None and name != color_name:
            raise SystemExit(f"color.ref {color_name!r} must be drawn before {name}")
        raw = os.path.join(work, "raw", f"{name}.png")
        tries = 0
        while True:
            if not os.path.exists(raw):
                if a.offline or (only is not None and name not in only):
                    raise SystemExit(f"raw/{name}.png missing" + (" (--offline)" if a.offline else ""))
                if tries > a.retries:
                    raise SystemExit(f"{name}: still shifted after {tries} tries; see failure-modes.md before changing the prompt")
                tries += 1
                rc = edit(work, name, fr, a.model)
                if rc == 2:
                    raise SystemExit("codex did not start; fix the setup (login, model name) before retrying")
                if rc != 0:
                    if os.path.exists(raw):
                        reject(work, name, "unusable edit")
                    continue
            r = measure(cfg, work, name)
            print(describe(r), flush=True)
            if r["pass"]:
                break
            reject(work, name, "shift: " + ", ".join(r["moved"]))
        r["tries"] = tries
        r["color"], r["specks_removed_px"] = process(cfg, work, name, color_ref)
        if r["color"]:
            c = r["color"]
            print(f"  colour: tint {c['tint_before']} -> {c['residual']} levels (limit {COLOR_RESIDUAL_MAX})", flush=True)
        report[name] = r
    save_json(os.path.join(work, "metrics", "frames.json"), report)
    bad = [n for n, r in report.items() if r["color"] and not r["color"]["pass"]]
    print(f"{len(report)} frames drawn, no shift" + (f"; colour residual over {COLOR_RESIDUAL_MAX} on {bad}" if bad else ""))


if __name__ == "__main__":
    main()
