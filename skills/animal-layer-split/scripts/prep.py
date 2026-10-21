"""Step 0: put the character on a square canvas for the image model and for the layers.

Usage: python3 -I prep.py <character.png> <workdir> [work size, default 512]

The input is a transparent PNG or a flat #00FF00 green screen. Writes
  <workdir>/norm/step0.png  the character at the work size, transparent (what the layers are cut from)
  <workdir>/in/step0.png    the same crop at 1024 on green (what the first edit gets)
  <workdir>/prep.json       crop box and scale, to map layer pixels back onto the source image
"""
import os
import sys

import numpy as np
from PIL import Image

sys.dont_write_bytecode = True  # no __pycache__ in the skill's folder
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import CODEX_INPUT, on_green, save_json, to_rgba  # noqa: E402

MARGIN = 0.08  # empty border on each side, as a share of the character's longer side


def main(src, work, size=512):
    size = int(size)
    a = to_rgba(src)
    ys, xs = np.nonzero(a[..., 3] > 0)
    if not len(ys):
        raise SystemExit(f"{src}: no character found (transparent PNG or flat #00FF00 background expected)")
    x0, y0, x1, y1 = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
    side = round(max(x1 - x0, y1 - y0) * (1 + 2 * MARGIN))
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    box = (cx - side // 2, cy - side // 2, cx - side // 2 + side, cy - side // 2 + side)
    square = Image.fromarray(a).crop(box)  # areas outside the source come back transparent
    os.makedirs(os.path.join(work, "norm"), exist_ok=True)
    os.makedirs(os.path.join(work, "in"), exist_ok=True)
    square.resize((size, size), Image.LANCZOS).save(os.path.join(work, "norm", "step0.png"))
    on_green(np.array(square.resize((CODEX_INPUT, CODEX_INPUT), Image.LANCZOS))).save(os.path.join(work, "in", "step0.png"))
    save_json(os.path.join(work, "prep.json"), {
        "source": os.path.abspath(src), "source_size": [a.shape[1], a.shape[0]],
        "crop_box": list(box), "work_size": size, "scale": size / side,
    })
    print(f"crop {box} -> {size}x{size} (scale {size / side:.4f}); codex input {CODEX_INPUT}x{CODEX_INPUT}")


if __name__ == "__main__":
    main(*sys.argv[1:])
