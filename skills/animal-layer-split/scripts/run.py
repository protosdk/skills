"""Run the whole split, one image edit at a time, and stop at the first step that fails its checks.

Usage: python3 -I run.py <character.png> <workdir> <rig.json> [--retries N] [--model M] [--psd name.psd]

Order: part map 0, peel 1, part map 1, peel 2, ... Each part map comes before the next peel step because
it says which pixels that step is allowed to change; everything else is used to line up colours and to
measure drift.

Resumable: a step whose output exists is skipped, so after fixing a prompt in rig.json, move the bad
output aside (keep it) and run again. A peel step or part map that fails its gate is moved to
<workdir>/rejected/ and redone, up to --retries times (default 2), then the run stops.
"""
import argparse
import os
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True  # no __pycache__ in the skill's folder
sys.path.insert(0, HERE)
from check import LIMITS, partmap_checks, peel_checks  # noqa: E402
from common import load_rig, read_seg, removed_mask, stack_back_to_front  # noqa: E402
from peel import norm  # noqa: E402


def py(script, *args):
    subprocess.run([sys.executable, "-I", os.path.join(HERE, script), *args], check=True)


def edit(work, prompt, src, out, model):
    args = [work, prompt, src, out] + ([model] if model else [])
    rc = subprocess.run([sys.executable, "-I", os.path.join(HERE, "codex_edit.py"), *args]).returncode
    if rc == 2:
        raise SystemExit("codex did not start; fix the setup (login, model name) before retrying")
    return rc == 0


def reject(work, rel, why):
    os.makedirs(os.path.join(work, "rejected"), exist_ok=True)
    stem = os.path.splitext(rel)[0].replace(os.sep, "-")
    n = len([f for f in os.listdir(os.path.join(work, "rejected")) if f.startswith(stem + "-try")])
    dst = os.path.join(work, "rejected", f"{stem}-try{n + 1}.png")
    shutil.move(os.path.join(work, rel), dst)
    print(f"REJECTED {rel} ({why}); kept as {os.path.relpath(dst, work)}")


def peel_problems(m):
    problems = []
    if m["raw_size"][0] != m["raw_size"][1]:
        problems.append(f"output {m['raw_size']} is not square")
    if max(abs(v) for v in m["global_shift_px"]) > LIMITS["peel_global_shift_px"]:
        problems.append(f"whole image moved {m['global_shift_px']} px")
    if m["drift_px"] > LIMITS["peel_drift_px"]:
        problems.append(f"something that should stay put moved {m['drift_px']} px near {m['drift_tile']}")
    if m["color_residual_main"] > LIMITS["peel_color_residual_main"] or m["color_residual_worst"] > LIMITS["peel_color_residual_worst"]:
        problems.append(f"colours drifted unevenly (main {m['color_residual_main']}, worst {m['color_residual_worst']})")
    return problems


def partmap_problems(work, rig, k):
    masks, inside = read_seg(os.path.join(work, f"seg-raw/step{k}.png"), rig["step_parts"][k], rig["colors"], rig["size"])
    step_alpha = np.array(Image.open(os.path.join(work, f"norm/step{k}.png")))[..., 3] > 128
    prev = read_seg(os.path.join(work, f"seg-raw/step{k - 1}.png"), rig["step_parts"][k - 1], rig["colors"], rig["size"])[0] if k else None
    out, warnings, _ = partmap_checks(rig, k, masks, inside, step_alpha, prev)
    for w in warnings:
        print(f"WARN  {w}")
    return [f"{c['check']} {c['value']} (limit {c['limit']})" for c in out if not c["pass"]], out[0]["value"]


def attempt(work, retries, out, make, judge, what):
    """Make `out` until judge() finds no problems; returns once it passes, or stops the run."""
    for _ in range(retries + 1):
        if not os.path.exists(os.path.join(work, out)) and not make():
            if os.path.exists(os.path.join(work, out)):
                reject(work, out, "codex_edit guard")
            continue
        problems = judge()
        if not problems:
            return
        reject(work, out, "; ".join(problems))
    raise SystemExit(f"{what} failed {retries + 1} times; see references/failure-modes.md before changing the prompt")


def main():
    sys.stdout.reconfigure(line_buffering=True)  # keep our lines in order with the child scripts' output in logs
    ap = argparse.ArgumentParser()
    ap.add_argument("character")
    ap.add_argument("work")
    ap.add_argument("rig")
    ap.add_argument("--retries", type=int, default=2)
    ap.add_argument("--model")
    ap.add_argument("--psd", default="rig.psd")
    a = ap.parse_args()
    work, rig_path = os.path.abspath(a.work), os.path.abspath(a.rig)
    rig = load_rig(rig_path)
    n, size = len(rig["peel"]), rig["size"]
    w = lambda *p: os.path.join(work, *p)  # noqa: E731

    if not os.path.exists(w("norm", "step0.png")):
        py("prep.py", a.character, work, str(size))
    py("prompts.py", work, rig_path)
    os.makedirs(w("metrics"), exist_ok=True)

    for k in range(n):
        seg = f"seg-raw/step{k}.png"

        def judge_seg():
            problems, overlap = partmap_problems(work, rig, k)
            if not problems:
                print(f"{seg}: silhouette IoU {overlap:.4f}")
            return problems
        attempt(work, a.retries, seg, lambda: edit(work, f"prompts/partmap-step{k}.txt", f"in/step{k}.png", seg, a.model),
                judge_seg, f"part map {k}")

        changed = w("metrics", f"changed-step{k + 1}.png")
        Image.fromarray(removed_mask(w(seg), rig, k, size).astype(np.uint8) * 255).save(changed)
        raw, out = f"raw/step{k + 1}.png", f"norm/step{k + 1}.png"

        def judge_peel():
            m = norm(w(raw), w(f"norm/step{k}.png"), w(out), w("metrics", f"peel-step{k + 1}.json"), changed)
            load = lambda p: np.array(Image.open(p).convert("RGBA")).astype(np.float32)  # noqa: E731
            prev_masks = read_seg(w(seg), rig["step_parts"][k], rig["colors"], size)[0]
            more, _ = peel_checks(rig, k + 1, load(w(f"norm/step{k}.png")), load(w(out)), prev_masks)
            problems = peel_problems(m) + [f"{c['check']} {c['value']} (limit {c['limit']})" for c in more if not c["pass"]]
            if problems:
                os.remove(w(out))
            return problems
        if not os.path.exists(w(out)):
            attempt(work, a.retries, raw, lambda: edit(work, f"prompts/peel-step{k + 1}.txt", f"in/step{k}.png", raw, a.model),
                    judge_peel, f"peel step {k + 1}")
        if not os.path.exists(w(f"in/step{k + 1}.png")):
            py("peel.py", "prep", w(raw), w(f"in/step{k + 1}.png"))

    py("build_layers.py", work, rig_path)
    psd = w(a.psd)
    layers = [w("layers", f"{name}.png") for name in stack_back_to_front(rig)]
    py("write_psd.py", psd, *layers)
    py("write_psd.py", "--check", psd, *layers)
    ok = subprocess.run([sys.executable, "-I", os.path.join(HERE, "check.py"), work, rig_path, psd]).returncode == 0
    print(f"\nlayers: {w('layers')}\nboards: {w('layers-board.png')}, {w('steps-board.png')}\nPSD: {psd}\nmetrics: {w('metrics.json')}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
