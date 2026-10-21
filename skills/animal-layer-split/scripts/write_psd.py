"""Write layer PNGs as a layered PSD (Unity PSD Importer, Spine's PSD import, Krita, Photoshop...).

Usage:
  python3 -I write_psd.py <out.psd> <bottom.png> ... <top.png>
  python3 -I write_psd.py --check <out.psd> <bottom.png> ... <top.png>

Written straight from Adobe's published file format: 8-bit RGB, one RGBA layer per PNG, uncompressed, no
dependencies. The layer name is the file name without the extension. --check reads the file back and
confirms every layer's position and pixels match its PNG.
"""
import os
import struct
import sys

import numpy as np
from PIL import Image


def pascal(name):
    b = name.encode("ascii")[:255]
    s = bytes([len(b)]) + b
    return s + b"\0" * ((4 - len(s) % 4) % 4)


def write_psd(path, layer_paths):
    imgs = [np.array(Image.open(p).convert("RGBA")) for p in layer_paths]
    h, w = imgs[0].shape[:2]
    records, data = b"", b""
    for p, a in zip(layer_paths, imgs):
        ys, xs = np.nonzero(a[..., 3])
        top, left, bottom, right = (int(ys.min()), int(xs.min()), int(ys.max()) + 1, int(xs.max()) + 1) if len(ys) else (0, 0, 0, 0)
        crop = a[top:bottom, left:right]
        chans = [(-1, crop[..., 3]), (0, crop[..., 0]), (1, crop[..., 1]), (2, crop[..., 2])]
        rec = struct.pack(">iiiiH", top, left, bottom, right, len(chans))
        for cid, c in chans:
            rec += struct.pack(">hI", cid, 2 + c.size)
        extra = struct.pack(">I", 0) + struct.pack(">I", 0) + pascal(os.path.splitext(os.path.basename(p))[0])
        rec += b"8BIM" + b"norm" + struct.pack(">BBBB", 255, 0, 0, 0) + struct.pack(">I", len(extra)) + extra
        records += rec
        for _, c in chans:
            data += struct.pack(">H", 0) + c.astype(np.uint8).tobytes()
    info = struct.pack(">h", len(imgs)) + records + data
    if len(info) % 2:
        info += b"\0"
    layer_info = struct.pack(">I", len(info)) + info
    lmi = layer_info + struct.pack(">I", 0)  # no global layer mask
    merged = Image.new("RGBA", (w, h), (255, 255, 255, 255))
    for a in imgs:
        merged.alpha_composite(Image.fromarray(a))
    m = np.array(merged.convert("RGB"))
    with open(path, "wb") as f:
        f.write(b"8BPS" + struct.pack(">H", 1) + b"\0" * 6 + struct.pack(">HIIHH", 3, h, w, 8, 3))
        f.write(struct.pack(">I", 0))  # color mode data
        f.write(struct.pack(">I", 0))  # image resources
        f.write(struct.pack(">I", len(lmi)) + lmi)
        f.write(struct.pack(">H", 0) + b"".join(m[..., c].tobytes() for c in range(3)))


def read_layers(path):
    """Read back a PSD written by write_psd (only the subset it writes): [(name, (top, left), RGBA array)]."""
    with open(path, "rb") as f:
        buf = f.read()
    assert buf[:4] == b"8BPS"
    off = 26
    for _ in range(2):
        off += 4 + struct.unpack(">I", buf[off:off + 4])[0]
    off += 4 + 4  # layer-and-mask length, layer-info length
    count = struct.unpack(">h", buf[off:off + 2])[0]
    off += 2
    recs = []
    for _ in range(count):
        top, left, bottom, right, n = struct.unpack(">iiiiH", buf[off:off + 18])
        off += 18
        chans = [struct.unpack(">hI", buf[off + 6 * i:off + 6 * i + 6]) for i in range(n)]
        off += 6 * n + 12  # channel info, blend signature + mode, opacity/clipping/flags/filler
        extra_len = struct.unpack(">I", buf[off:off + 4])[0]
        off += 4
        extra = buf[off:off + extra_len]
        off += extra_len
        name_len = extra[8]
        recs.append((extra[9:9 + name_len].decode(), top, left, bottom, right, chans))
    out = []
    for name, top, left, bottom, right, chans in recs:
        hh, ww = bottom - top, right - left
        planes = {}
        for cid, ln in chans:
            assert struct.unpack(">H", buf[off:off + 2])[0] == 0
            planes[cid] = np.frombuffer(buf[off + 2:off + ln], np.uint8).reshape(hh, ww)
            off += ln
        out.append((name, (top, left), np.dstack([planes[0], planes[1], planes[2], planes[-1]])))
    return out


def check(psd, pngs):
    ok = True
    for (name, (top, left), a), p in zip(read_layers(psd), pngs):
        ref = np.array(Image.open(p).convert("RGBA"))
        same = np.array_equal(ref[top:top + a.shape[0], left:left + a.shape[1]], a) and ref[..., 3].sum() == a[..., 3].astype(int).sum()
        ok &= same
        print(f"{name}: at ({left}, {top}), {a.shape[1]}x{a.shape[0]}, {'matches' if same else 'DIFFERS FROM'} {os.path.basename(p)}")
    return ok


if __name__ == "__main__":
    if sys.argv[1] == "--check":
        sys.exit(0 if check(sys.argv[2], sys.argv[3:]) else 1)
    write_psd(sys.argv[1], sys.argv[2:])
    print("saved", sys.argv[1], os.path.getsize(sys.argv[1]), "bytes")
