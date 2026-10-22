"""Write a looping GIF preview without banding or flicker.

Library for build.py. ffmpeg picks one palette for the whole animation (palettegen, stats_mode=full) and maps
every frame with ordered Bayer dithering; Pillow then writes the indexed frames with exact per-frame
durations. Why each part:
- Pillow's own quantizer without dithering bands soft gradients (shadows turned grey-green), and its
  palette lookup is approximate.
- Error-diffusion dithering moves the dither pattern wherever anything changes, so still areas shimmer;
  Bayer dithering is the same on every frame where the picture is the same.
- ffmpeg mistimes non-uniform frame delays, so it does not write the GIF itself.
The GIF has 256 colours: it is a preview. Ship the PNG frames.
"""
import os
import shutil
import subprocess
import tempfile

import numpy as np
from PIL import Image


def ffmpeg(*args):
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg not found: install it (for example `brew install ffmpeg`) to write GIF previews")
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"ffmpeg failed: {r.stderr.strip()}")


def write(images, durations, path):
    """images: PIL images (composited on a background already); durations: ms per frame."""
    with tempfile.TemporaryDirectory() as tmp:
        for i, im in enumerate(images):
            im.convert("RGB").save(os.path.join(tmp, f"in{i:05d}.png"))
        src = ["-framerate", "10", "-i", os.path.join(tmp, "in%05d.png")]
        palette = os.path.join(tmp, "palette.png")
        ffmpeg(*src, "-vf", "palettegen=stats_mode=full:reserve_transparent=0", palette)
        ffmpeg(*src, "-i", palette, "-lavfi", "[0:v][1:v]paletteuse=dither=bayer:bayer_scale=4", os.path.join(tmp, "out%05d.png"))
        colors = np.array(Image.open(palette).convert("RGB")).reshape(-1, 3)
        lut = {tuple(c): i for i, c in reversed(list(enumerate(colors.tolist())))}
        frames = []
        for i in range(len(images)):
            rgb = np.array(Image.open(os.path.join(tmp, f"out{i + 1:05d}.png")).convert("RGB")).reshape(-1, 3)
            uniq, inv = np.unique(rgb, axis=0, return_inverse=True)
            idx = np.array([lut[tuple(c)] for c in uniq.tolist()], dtype=np.uint8)[inv.ravel()]
            f = Image.fromarray(idx.reshape(images[i].height, images[i].width), mode="P")
            f.putpalette(colors.astype(np.uint8).ravel().tolist())
            frames.append(f)
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=list(durations), loop=0, disposal=1, optimize=False)
