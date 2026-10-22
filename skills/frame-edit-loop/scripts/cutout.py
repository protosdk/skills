"""Cut a small effect drawn in one frame (a sweat drop in the air) into a sprite that build.py can overlay.

Usage: python3 -I cutout.py <workdir> <image> <x0,y0,x1,y1> <name> <select> [--min-alpha A]
(stabilize.py does the same for every entry in `stabilize.sprites`; run this by hand to try a selection.)

<image> is a frame on the work canvas (usually matched/<frame>.png), <select> a channel difference that is
true on the effect and false on what is around it, for example B-R>20 for a blue drop next to warm grey.
The largest connected piece inside the box is kept, grown 3 px with a soft edge; everything else in the
box is dropped. Writes <workdir>/sprites/<name>.png, the size of the box.
To lift a detail off the character itself (a drop on the cheek), use `stabilize.erase` instead: it also
fills the spot it leaves behind.
"""
import os
import sys

import numpy as np
from PIL import Image
from scipy.ndimage import binary_dilation, gaussian_filter, label

sys.dont_write_bytecode = True  # no __pycache__ in the skill's folder
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import parse_select  # noqa: E402

GROW, SOFT = 3, 0.8


def cut(a, box, select, min_alpha=0):
    """a: RGBA float array of a frame. Returns the sprite (box-sized RGBA uint8) and the selected px count."""
    x0, y0, x1, y1 = box
    part = a[y0:y1, x0:x1].copy()
    sel = parse_select(select)(part) & (part[..., 3] > min_alpha)
    lab, n = label(sel)
    if not n:
        raise SystemExit(f"nothing in {box} matches {select}")
    sel = lab == np.bincount(lab.ravel())[1:].argmax() + 1
    keep = gaussian_filter(binary_dilation(sel, iterations=GROW).astype(np.float32), SOFT)
    part[..., 3] *= np.clip(keep, 0, 1)
    return part.clip(0, 255).astype(np.uint8), int(sel.sum())


def main(work, image, box, name, select, *rest):
    min_alpha = int(rest[rest.index("--min-alpha") + 1]) if "--min-alpha" in rest else 0
    box = [int(v) for v in box.split(",")]
    a = np.array(Image.open(image if os.path.isabs(image) else os.path.join(work, image)).convert("RGBA")).astype(np.float32)
    sprite, n = cut(a, box, select, min_alpha)
    os.makedirs(os.path.join(work, "sprites"), exist_ok=True)
    Image.fromarray(sprite).save(os.path.join(work, "sprites", f"{name}.png"))
    print(f"sprites/{name}.png: {box[2] - box[0]}x{box[3] - box[1]}, {n} px selected from {image}")


if __name__ == "__main__":
    main(*sys.argv[1:])
