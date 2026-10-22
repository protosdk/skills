"""Check the built loop and write <workdir>/metrics.json: every check with its value, limit and verdict.

Usage: python3 -I check.py <workdir>   (after run.py, stabilize.py and build.py)
Exit code 0 when every check passes.

- shift: every drawn frame passed the shift check (metrics/frames.json, from run.py)
- colour: what is left of each frame's colour drift after matching
- outside: per output frame, pixels outside the reference frame's silhouette moved by the same pose,
  apart from the frame's `outside` zones and the overlays. An echo of the head or body shows up here.
- stretch: the largest stretch any pose puts on the character's lines
Also printed, not judged: where each change of image changes the picture (it should stay on the part
that moves), and the loop's length.
"""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageOps
from scipy.ndimage import binary_dilation

sys.dont_write_bytecode = True  # no __pycache__ in the skill's folder
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build import frame_name, plan, put  # noqa: E402
from common import box_mask, load_config, load_json, save_json  # noqa: E402
from run import COLOR_RESIDUAL_MAX  # noqa: E402
from warp import STRETCH_MAX  # noqa: E402

ZONE_PAD = 15  # outside zones are drawn on the unmoved frame; the pose can carry the part this far
CHANGE = 24  # level difference that counts as a visible change between two frames


def main(work):
    cfg = load_config(work)
    name = cfg.get("name", "loop")
    seq, poses, fields = plan(cfg)
    st = load_json(os.path.join(work, "metrics", "stabilize.json"), {})
    ref_name = st.get("ref") or cfg.get("stabilize", {}).get("ref") or next(iter(cfg["frames"]))
    ref = Image.open(os.path.join(work, "stab", f"{ref_name}.png")).convert("RGBA")
    mirror = cfg.get("mirror", False)
    checks = []

    frames_m = load_json(os.path.join(work, "metrics", "frames.json"), {})
    shifted = [n for n, r in frames_m.items() if not r["pass"]]
    redone = {n: r["tries"] for n, r in frames_m.items() if r.get("tries", 0) > 1}
    checks.append({"check": "shift: locked parts of every drawn frame at (0, 0)",
                   "value": f"{len(frames_m) - len(shifted)}/{len(frames_m)}", "limit": "all",
                   "pass": bool(frames_m) and not shifted, "detail": {"redrawn": redone, "shifted": shifted}})
    res = {n: r["color"]["residual"] for n, r in frames_m.items() if r.get("color")}
    worst = max(res.values()) if res else 0.0
    checks.append({"check": "colour: tint left on flat fill after matching (levels)", "value": worst, "limit": COLOR_RESIDUAL_MAX,
                   "pass": worst <= COLOR_RESIDUAL_MAX, "detail": res})

    sprites, refs, outside, out_detail = {}, {}, 0, {}
    frames = []
    for i, (e, pose) in enumerate(zip(seq, poses)):
        f = Image.open(os.path.join(work, "out", "frames", frame_name(name, i, len(seq)))).convert("RGBA")
        frames.append(np.array(f).astype(int))
        zones = cfg["frames"].get(e["image"], {}).get("stabilize", {}).get("outside", [])
        if zones == "keep":
            continue
        key = json.dumps(pose, sort_keys=True)
        if key not in refs:
            r = fields.warp(ref, pose)
            refs[key] = np.array(ImageOps.mirror(r) if mirror else r)[..., 3] > 16
        allowed = binary_dilation(refs[key], iterations=2)
        z = box_mask(zones, ZONE_PAD)
        if e.get("overlays"):
            layer = Image.new("RGBA", ref.size, (0, 0, 0, 0))
            for ov in e["overlays"]:
                if ov["sprite"] not in sprites:
                    sprites[ov["sprite"]] = Image.open(os.path.join(work, "sprites", f"{ov['sprite']}.png")).convert("RGBA")
                layer = put(layer, sprites[ov["sprite"]], ov["at"], ov.get("scale", 1.0), ov.get("opacity", 1.0), ov.get("angle", 0.0))
            z |= binary_dilation(np.array(fields.warp(layer, pose))[..., 3] > 0, iterations=3)
        if mirror:
            z = z[:, ::-1]
        extra = (frames[-1][..., 3] > 16) & ~allowed & ~z
        n = int(extra.sum())
        if n:
            ys, xs = np.nonzero(extra)
            out_detail[i] = {"px": n, "image": e["image"], "box": [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]}
        outside = max(outside, n)
    checks.append({"check": "outside: new pixels past the silhouette, outside the frame's zones and overlays (px)", "value": outside,
                   "limit": 0, "pass": outside == 0, "detail": out_detail})

    tl = load_json(os.path.join(work, "out", "timeline.json"))
    worst = max(tl["timeline"], key=lambda r: r["stretch"])
    checks.append({"check": "stretch: largest warp stretch on the character", "value": worst["stretch"], "limit": STRETCH_MAX,
                   "pass": worst["stretch"] <= STRETCH_MAX, "detail": {"frame": worst["frame"], "at": worst["stretch_at"]}})

    changes = []
    for i in range(len(seq)):
        a, b = frames[i - 1], frames[i]
        d = np.abs(a - b).max(-1) > CHANGE
        if seq[i - 1]["image"] != seq[i]["image"] and d.any():
            ys, xs = np.nonzero(d)
            changes.append(f"{(i - 1) % len(seq):02d}->{i:02d} {seq[i - 1]['image']}->{seq[i]['image']}: {int(d.sum())} px "
                           f"in x {xs.min()}-{xs.max()}, y {ys.min()}-{ys.max()}")
    loop = {"frames": len(seq), "ms": cfg.get("ms", 60), "loopMs": cfg.get("ms", 60) * len(seq), "fps": round(1000 / cfg.get("ms", 60), 2)}
    save_json(os.path.join(work, "metrics.json"), {"checks": checks, "image_changes": changes, "loop": loop})
    for c in checks:
        print(f"{'PASS' if c['pass'] else 'FAIL'}  {c['check']}: {c['value']} (limit {c['limit']})")
    for i, d in sorted(out_detail.items())[:8]:
        print(f"      frame {i} ({d['image']}): {d['px']} px at {d['box']}")
    print("image changes (look at these frames one by one):")
    for c in changes:
        print("  " + c)
    print(f"loop: {loop['frames']} frames x {loop['ms']} ms = {loop['loopMs']} ms ({loop['fps']} fps)")
    sys.exit(0 if all(c["pass"] for c in checks) else 1)


if __name__ == "__main__":
    main(*sys.argv[1:])
