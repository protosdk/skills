"""Step 0: put the illustration on the 1024 work canvas.

Usage: python3 -I prep.py <illustration.png> <workdir> [--alpha-as-is]

The illustration (transparent PNG) is centred on a square as wide as its longer side and scaled to 1024,
with nothing cropped, so every frame maps straight back onto the original canvas. Writes
  <workdir>/in/art.png     the illustration on flat #00FF00 (what the first edit gets)
  <workdir>/keyed/art.png  the same, keyed back to transparent (colour reference, review sheets)
  <workdir>/prep.json      where the original canvas sits on the work canvas (export crops to it)

Alpha 240-254 counts as opaque: exports often store the body just under 255, and on green that tints the
whole character. --alpha-as-is skips this (to replay runs prepared without it).
"""
import os
import sys

import numpy as np
from PIL import Image

sys.dont_write_bytecode = True  # no __pycache__ in the skill's folder
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import N, key_green, save_json  # noqa: E402

OPAQUE_FROM = 240


def main(src, work, *flags):
    im = Image.open(src).convert("RGBA")
    a = np.array(im)
    if "--alpha-as-is" not in flags:
        a[..., 3] = np.where(a[..., 3] >= OPAQUE_FROM, 255, a[..., 3])
    green = (a[..., 1].astype(int) - np.maximum(a[..., 0], a[..., 2])) > 100
    if (green & (a[..., 3] > 200)).mean() > 0.001:
        raise SystemExit(f"{src}: the character contains saturated green, the keying colour; it cannot be keyed")
    side = max(im.size)
    ox, oy = (side - im.width) // 2, (side - im.height) // 2
    canvas = Image.new("RGBA", (side, side), (0, 255, 0, 255))
    canvas.alpha_composite(Image.fromarray(a), (ox, oy))
    rgb = canvas.resize((N, N), Image.LANCZOS).convert("RGB")
    os.makedirs(os.path.join(work, "in"), exist_ok=True)
    os.makedirs(os.path.join(work, "keyed"), exist_ok=True)
    rgb.save(os.path.join(work, "in", "art.png"))
    key_green(rgb.convert("RGBA")).save(os.path.join(work, "keyed", "art.png"))
    s = N / side
    box = [round(ox * s), round(oy * s), round((ox + im.width) * s), round((oy + im.height) * s)]
    save_json(os.path.join(work, "prep.json"), {
        "source": os.path.abspath(src), "source_size": list(im.size), "square": side, "offset": [ox, oy],
        "scale": s, "art_box": box,
    })
    print(f"{src} {im.size} -> centred on {side}x{side} -> {N}x{N}; original canvas at {box}")


if __name__ == "__main__":
    main(*sys.argv[1:])
