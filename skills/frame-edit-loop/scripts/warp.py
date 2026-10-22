"""Small motion by a smooth displacement field: sway, a nod, ears that lag, a prop that shakes.

Library for build.py and check.py. A move of a few px that fades smoothly from the moving area into the
still one only stretches the lines a little: no seam opens and nothing hidden has to be painted in, so
nothing needs cutting into layers. Large moves (a hand crossing the body, a page turning) are drawn as
frames by the image model instead.

`warp.fields` in loop.json is an ordered list; each field has a weight shape (1 = moves fully) and a pivot.
A frame's pose gives each field [degrees, dx, dy]. Fields apply in list order, each in the coordinates the
previous ones produced, so a head field rides on a body sway listed before it.
Shapes: "all" (whole frame, no blending), {"band": [y_full, y_none]} (rows above y_full move fully, below
y_none not at all), {"ellipse": [cx, cy, rx, ry], "feather": f}, {"polygon": [[x, y], ...], "feather": f};
any shape may add "minus": <shape> to exclude an area (a hand that must not ride with the head).
Transition bands must fall on background or flat fill, not across a thin part: an ear crossed by a band
bends instead of moving.
"""
import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import gaussian_filter, map_coordinates

N = 1024
STRETCH_MAX = 0.12  # see references/checks.md

_yy, _xx = np.mgrid[0:N, 0:N].astype(np.float32)


def soft_ellipse(cx, cy, rx, ry, feather):
    d = np.sqrt(((_xx - cx) / rx) ** 2 + ((_yy - cy) / ry) ** 2)
    edge = 1.0 + feather / min(rx, ry)
    return np.clip((edge - d) / (edge - 1.0), 0, 1) ** 1.5


def soft_poly(points, feather):
    m = Image.new("L", (N, N), 0)
    ImageDraw.Draw(m).polygon([tuple(p) for p in points], fill=255)
    return np.clip(gaussian_filter(np.array(m, np.float32) / 255, feather / 2.5), 0, 1)


def band(y0, y1):
    t = np.clip((y1 - _yy) / (y1 - y0), 0, 1)
    return t * t * (3 - 2 * t)


def shape(spec):
    if spec == "all":
        return None
    if "band" in spec:
        w = band(*spec["band"])
    elif "ellipse" in spec:
        w = soft_ellipse(*spec["ellipse"], spec.get("feather", 30))
    elif "polygon" in spec:
        w = soft_poly(spec["polygon"], spec.get("feather", 30))
    else:
        raise SystemExit(f"warp shape {spec}: expected all, band, ellipse or polygon")
    if "minus" in spec:
        w = w * (1 - shape(spec["minus"]))
    return w


class Fields:
    def __init__(self, cfg):
        self.fields = []
        for f in cfg.get("warp", {}).get("fields", []):
            self.fields.append((f["name"], shape(f.get("shape", "all")), tuple(f.get("pivot", (0.0, 0.0)))))
        self.names = [f[0] for f in self.fields]

    def source_coords(self, pose):
        """Inverse map: for every output pixel, where to sample the input. pose: {field: [deg, dx, dy]}."""
        x, y = _xx.copy(), _yy.copy()
        for name, w, (cx, cy) in self.fields:
            if not any(pose.get(name, ())):
                continue
            deg, dx, dy = pose[name]
            rx, ry = rot(x, y, cx, cy, -deg)
            if w is None:
                x, y = rx - dx, ry - dy
            else:
                k = map_coordinates(w, [y, x], order=1, mode="constant", cval=0.0)
                x, y = x + k * (rx - x) - k * dx, y + k * (ry - y) - k * dy
        return x, y

    def warp(self, img, pose):
        """img: RGBA PIL image. Sampled with premultiplied alpha, so edges get no dark fringe. Pixels that do
        not move keep their exact values: resampling would make nearly transparent edges flicker."""
        if not any(any(v) for v in pose.values()):
            return img.copy()
        src = np.array(img.convert("RGBA"))
        a = src.astype(np.float32) / 255
        pre = a.copy()
        pre[..., :3] *= a[..., 3:4]
        x, y = self.source_coords(pose)
        out = np.stack([map_coordinates(pre[..., c], [y, x], order=3, mode="constant", cval=0.0) for c in range(4)], -1)
        out = np.clip(out, 0, 1)
        al = out[..., 3:4]
        out[..., :3] = np.where(al > 1e-4, out[..., :3] / np.maximum(al, 1e-4), 0)
        out = (np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8)
        still = (x == _xx) & (y == _yy)
        out = np.where(still[..., None], src, out)
        return Image.fromarray(out)

    def stretch(self, pose, alpha):
        """Largest stretch or squash of the field on the character (singular values of the Jacobian off 1),
        and where. alpha: the input's alpha (0-255); the background stretching does not show."""
        x, y = self.source_coords(pose)
        j = np.stack([np.stack([np.gradient(x, axis=1), np.gradient(x, axis=0)], -1),
                      np.stack([np.gradient(y, axis=1), np.gradient(y, axis=0)], -1)], -2)
        s = np.linalg.svd(j.reshape(-1, 2, 2), compute_uv=False).reshape(N, N, 2)
        dev = np.abs(s - 1).max(axis=-1)
        dev = np.where(map_coordinates(alpha.astype(np.float32), [y, x], order=1) > 128, dev, 0)
        i = int(dev.argmax())
        return float(dev.max()), (i % N, i // N)


def rot(px, py, cx, cy, deg):
    t = np.deg2rad(deg)
    dx, dy = px - cx, py - cy
    return cx + dx * np.cos(t) - dy * np.sin(t), cy + dx * np.sin(t) + dy * np.cos(t)
