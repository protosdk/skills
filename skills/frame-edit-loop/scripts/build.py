"""Assemble the loop from the stabilised frames: timeline, small motion, overlays, preview GIFs, export.

Usage: python3 -I build.py <workdir>

Every output frame = a stabilised frame (stab/) + overlay sprites (sprites/) + the smooth warp of its pose,
mirrored if `mirror` is set. The pose of a frame is the sum of `warp.waves` at that frame, the offsets in
`warp.images` for the image it shows, and the entry's own `warp`, clamped by each field's `clamp`.
Writes to <workdir>/out/:
  frames/<name>-NN.png  every frame, 1024 square, transparent
  timeline.json         per frame: image, ms, pose, overlays, stretch
  solo.gif              the character alone on a flat background (256-colour preview)
  scene.gif             the character between scene layers, if `scene` is set
  motion-board.png      every frame on one sheet, numbered
  export/               frames cropped back to the illustration's canvas, and <name>.json with the timing
"""
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

sys.dont_write_bytecode = True  # no __pycache__ in the skill's folder
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gif  # noqa: E402
from common import load_config, load_json, save_json  # noqa: E402
from warp import Fields  # noqa: E402


def frame_name(name, i, n):
    return f"{name}-{i:0{max(2, len(str(n - 1)))}d}.png"


def plan(cfg):
    """The expanded timeline, each frame's pose, and the warp fields."""
    seq = expand(cfg["timeline"])
    fields = Fields(cfg)
    return seq, poses(cfg, seq, fields), fields


def expand(entries):
    out = []
    for e in entries:
        if "repeat" in e:
            out += expand(e["entries"]) * e["repeat"]
        else:
            out += [e] * e.get("hold", 1)
    return out


def poses(cfg, seq, fields):
    w = cfg.get("warp", {})
    n = len(seq)
    clamp = {f["name"]: f["clamp"] for f in w.get("fields", []) if "clamp" in f}
    out = []
    for i, e in enumerate(seq):
        pose = {}
        for name in fields.names:
            v = [0.0, 0.0, 0.0]
            for wave in w.get("waves", []):
                if wave["field"] == name:
                    s = math.sin(2 * math.pi * wave.get("cycles", 1) * (i - wave.get("lag", 0)) / n)
                    v = [v[k] + wave["amp"][k] * s for k in range(3)]
            for extra in (w.get("images", {}).get(e["image"], {}).get(name), e.get("warp", {}).get(name)):
                if extra:
                    v = [v[k] + extra[k] for k in range(3)]
            if name in clamp:
                v[0] = max(-clamp[name], min(clamp[name], v[0]))
            if any(v):
                pose[name] = v
        out.append(pose)
    return out


def put(frame, sprite, center, scale=1.0, opacity=1.0, angle=0.0):
    """Overlay a sprite centred on `center` (work canvas px), scaled, faded and turned."""
    s = sprite
    if angle:
        s = s.rotate(angle, resample=Image.BICUBIC, expand=True)
    if scale != 1.0:
        s = s.resize((max(1, round(s.width * scale)), max(1, round(s.height * scale))), Image.LANCZOS)
    if opacity < 1.0:
        a = np.array(s)
        a[..., 3] = (a[..., 3] * opacity).astype(np.uint8)
        s = Image.fromarray(a)
    layer = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    layer.alpha_composite(s, (round(center[0] - s.width / 2), round(center[1] - s.height / 2)))
    out = frame.copy()
    out.alpha_composite(layer)
    return out


def place(canvas, img, rect, crop=None):
    """Stretch img (or its crop) into rect, normalised [x, y, w, h] of the canvas; off-canvas parts are cut."""
    W, H = canvas.size
    x, y, w, h = rect
    part = (img.crop(tuple(crop)) if crop else img).resize((round(w * W), round(h * H)), Image.LANCZOS)
    px, py = round(x * W), round(y * H)
    part = part.crop((max(0, -px), max(0, -py), part.width, part.height))
    canvas.alpha_composite(part, (max(0, px), max(0, py)))


def on_bg(im, color):
    t = Image.new("RGBA", im.size, tuple(color) + (255,))
    t.alpha_composite(im)
    return t


def solo_frames(frames, p):
    crop = p.get("crop", "auto")
    if crop == "auto":
        boxes = [f.getchannel("A").point(lambda a: 255 if a > 128 else 0).getbbox() for f in frames]
        pad = p.get("pad", 24)
        crop = (min(b[0] for b in boxes) - pad, min(b[1] for b in boxes) - pad,
                max(b[2] for b in boxes) + pad, max(b[3] for b in boxes) + pad)
    crop = tuple(crop)
    w, h = crop[2] - crop[0], crop[3] - crop[1]
    size = tuple(p["size"]) if "size" in p else (round(w * p.get("scale", 0.5)), round(h * p.get("scale", 0.5)))
    bg = p.get("background", [245, 236, 218])
    return [on_bg(f.crop(crop), bg).resize(size, Image.LANCZOS) for f in frames], crop


def scene_frames(work, frames, sc, art_box):
    def load(p):
        return Image.open(p if os.path.isabs(p) else os.path.join(work, p)).convert("RGBA")

    base = load(sc["background"])
    layers = sc["layers"]
    me = next(i for i, layer in enumerate(layers) if layer.get("character"))
    for layer in layers[:me]:
        place(base, load(layer["image"]), layer["rect"], layer.get("crop"))
    front = [(load(layer["image"]), layer) for layer in layers[me + 1:]]
    out = []
    for f in frames:
        im = base.copy()
        place(im, f, layers[me]["rect"], art_box)
        for img, layer in front:
            place(im, img, layer["rect"], layer.get("crop"))
        if sc.get("crop"):
            im = im.crop(tuple(sc["crop"]))
        if sc.get("scale", 1) != 1:
            im = im.resize((round(im.width * sc["scale"]), round(im.height * sc["scale"])), Image.LANCZOS)
        out.append(im)
    return out


def board(frames, labels, crop, path, cols=8, tile=200):
    th = round(tile * (crop[3] - crop[1]) / (crop[2] - crop[0]))
    rows = math.ceil(len(frames) / cols)
    sheet = Image.new("RGB", (cols * tile, rows * (th + 16)), (255, 255, 255))
    d = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.load_default(size=14)
    except TypeError:  # Pillow before 10.1
        font = ImageFont.load_default()
    for i, (f, label) in enumerate(zip(frames, labels)):
        x, y = (i % cols) * tile, (i // cols) * (th + 16)
        sheet.paste(on_bg(f.crop(crop), (240, 232, 216)).resize((tile, th), Image.LANCZOS).convert("RGB"), (x, y + 16))
        d.text((x + 4, y + 2), label, fill=(60, 45, 30), font=font)
    sheet.save(path)


def export(cfg, out_dir, frames, rows, art_box, name, ms):
    x0, y0, x1, y1 = art_box
    os.makedirs(os.path.join(out_dir, "export"), exist_ok=True)
    listed = []
    for i, f in enumerate(frames):
        a = np.array(f)[..., 3] > 0
        a[y0:y1, x0:x1] = False
        if a.any():
            ys, xs = np.nonzero(a)
            return f"frame {i} has {int(a.sum())} px outside the illustration's canvas (x {xs.min()}-{xs.max()}, y {ys.min()}-{ys.max()})"
    for i, f in enumerate(frames):
        fname = frame_name(name, i, len(frames))
        f.crop(tuple(art_box)).save(os.path.join(out_dir, "export", fname), optimize=True)
        listed.append({"file": fname, "ms": ms, "image": rows[i]["image"]})
    save_json(os.path.join(out_dir, "export", f"{name}.json"), {
        "name": name, "loop": True, "frameMs": ms, "fps": round(1000 / ms, 2), "loopMs": ms * len(frames),
        "size": [x1 - x0, y1 - y0], "mirrored": bool(cfg.get("mirror")), "frames": listed,
        "note": "Each frame is the illustration's own canvas at the work scale, so the illustration's placement applies unchanged.",
    })
    return None


def main(work):
    cfg = load_config(work)
    prep = load_json(os.path.join(work, "prep.json"))
    name = cfg.get("name", "loop")
    ms = cfg.get("ms", 60)
    out_dir = os.path.join(work, "out")
    os.makedirs(os.path.join(out_dir, "frames"), exist_ok=True)
    seq, ps, fields = plan(cfg)
    cache, sprites = {}, {}
    frames, rows = [], []
    for i, (e, pose) in enumerate(zip(seq, ps)):
        if e["image"] not in cache:
            cache[e["image"]] = Image.open(os.path.join(work, "stab", f"{e['image']}.png")).convert("RGBA")
        im = cache[e["image"]]
        # Stretch is measured on the character, not on overlays: a drop in the air may sit where a field fades out.
        stretch, at = fields.stretch(pose, np.array(im)[..., 3]) if pose else (0.0, None)
        for ov in e.get("overlays", []):
            if ov["sprite"] not in sprites:
                sprites[ov["sprite"]] = Image.open(os.path.join(work, "sprites", f"{ov['sprite']}.png")).convert("RGBA")
            im = put(im, sprites[ov["sprite"]], ov["at"], ov.get("scale", 1.0), ov.get("opacity", 1.0), ov.get("angle", 0.0))
        im = fields.warp(im, pose)
        if cfg.get("mirror"):
            im = ImageOps.mirror(im)
        im.save(os.path.join(out_dir, "frames", frame_name(name, i, len(seq))))
        frames.append(im)
        rows.append({"frame": i, "image": e["image"], "ms": ms, "pose": {k: [round(x, 4) for x in v] for k, v in pose.items()},
                     "overlays": e.get("overlays", []), "stretch": round(stretch, 4), "stretch_at": at})
    save_json(os.path.join(out_dir, "timeline.json"), {"name": name, "ms": ms, "fps": round(1000 / ms, 2), "frames": len(frames),
                                                       "loopMs": ms * len(frames), "mirror": bool(cfg.get("mirror")), "timeline": rows})
    pv = cfg.get("preview", {})
    solo, crop = solo_frames(frames, pv)
    gif.write(solo, [ms] * len(solo), os.path.join(out_dir, "solo.gif"))
    if cfg.get("scene"):
        art_box = prep["art_box"]
        if cfg.get("mirror"):
            art_box = [1024 - art_box[2], art_box[1], 1024 - art_box[0], art_box[3]]
        gif.write(scene_frames(work, frames, cfg["scene"], art_box), [ms] * len(frames), os.path.join(out_dir, "scene.gif"))
    board(frames, [f"{r['frame']:02d} {r['image']}" for r in rows], crop, os.path.join(out_dir, "motion-board.png"))
    box = prep["art_box"]
    if cfg.get("mirror"):
        box = [1024 - box[2], box[1], 1024 - box[0], box[3]]
    problem = export(cfg, out_dir, frames, rows, box, name, ms)
    worst = max(rows, key=lambda r: r["stretch"])
    print(f"{len(frames)} frames x {ms} ms = {ms * len(frames)} ms ({1000 / ms:.1f} fps); "
          f"largest stretch {worst['stretch']:.3f} at frame {worst['frame']} {worst['stretch_at']}")
    size = f"{box[2] - box[0]}x{box[3] - box[1]}"
    print("export: " + (f"NOT WRITTEN, {problem}" if problem else f"{len(frames)} frames of {size} in out/export/"))


if __name__ == "__main__":
    main(*sys.argv[1:])
