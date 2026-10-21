"""Cut the original into rig layers from the peel steps and part maps, then put them back together to compare.

Usage: python3 -I build_layers.py <workdir> <rig.json>

Needs, at the work size:
- norm/step0..N.png: step 0 is the original; step k has the parts of peel[0..k-1] removed and what they hid painted in.
- seg-raw/step0..N-1.png: part maps, one flat colour per part still present in that step.

A part's full shape comes from the part map of the step where it is frontmost (the head's full shape
comes from the map drawn after the ears were removed, so the top of the head hidden by the ears is included).
Where the original shows the part, the layer takes the original's pixels; where something covered it, the
layer takes the pixels the image model painted in that step. So the layers stacked back up give the original.

Writes layers/<part>.png, layers/<part>_root.png (a hidden root behind the parent, see motion.py),
layers/joint_<part>.png (where a part meets its parent, a starting point for bone weights),
layers/composite.png, layers/stats.json, layers-board.png (each layer alone, the stack, the part map) and
steps-board.png (every peel step over the part map painted on it) and motion-board.png (each jointed part
turned both ways).
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.dont_write_bytecode = True  # no __pycache__ in the skill's folder
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import grow, load_rig, lum, read_seg, save_json, shrink, soft, stack_back_to_front  # noqa: E402
import motion  # noqa: E402

CUT_FEATHER = 4  # joint feather radius (px at 512)
FADE_INSET = 10  # only fade where the parent layer lies at least this deep underneath (px at 512)
EDGE_RING = 6  # outline pixels the part maps miss get handed to the nearest part, up to this many rings
LINE_LUM = 100  # darker than this in the original counts as drawn line...
LINE_MAX = 130  # ...if no channel is brighter than this: a saturated red (lum 76) is a colour, not a line
FRINGE_MAX = 180  # the 1 px anti-aliased fringe takes line-to-fill blends, not the neighbouring fill itself
LINE_REACH = 3  # how far (px at 512) a part's own outline may lie past its part-map region
SILHOUETTE_LINE = 5  # px at 512 inside the character's edge that belong to its outer outline


def claim_outlines(masks, order, original, scale):
    """Give each part its own outline where it overlaps a part behind it.

    Part maps put the boundary between two parts anywhere across the line between them, so a strip of the front
    part's outline often lands in the rear part, stays there when the front part moves (a chin line left on the
    body), and is missing from the front part. In a drawing the line between two overlapping parts belongs to the
    one in front, so each part, front first, grows through dark pixels connected to its edge, then one more pixel
    for the anti-aliased fringe. Pixels claimed by parts further in front are never taken, and neither is the
    character's own outer outline: growing along it would leave dark spurs sticking out of the front part.
    A line is dark in every channel: with luminance alone, a head grew into the red bandana under its chin and
    carried a red sliver."""
    inside = shrink(original[..., 3] > 128, round(SILHOUETTE_LINE * scale))
    brightest = original[..., :3].max(axis=2)
    line = (lum(original) < LINE_LUM) & (brightest < LINE_MAX) & inside
    ahead = np.zeros_like(line)
    for part in order[:-1]:
        m = masks[part]
        added = np.zeros_like(line)
        for _ in range(round(LINE_REACH * scale)):
            g = grow(m, 1) & line & ~m & ~ahead
            if not g.any():
                break
            m, added = m | g, added | g
        masks[part] = m | (grow(added, 1) & inside & ~ahead & (brightest < FRINGE_MAX))
        ahead |= masks[part]


def visible_by_order(masks, order, char):
    """Original pixels go to the frontmost part that claims them."""
    visible, covered = {}, np.zeros_like(char)
    for part in order:
        visible[part] = masks[part] & char & ~covered
        covered |= masks[part]
    return visible


def seam(mask, parent_visible, scale):
    """Where this part meets its parent in the original (0-1): the edge band that touches the parent's visible pixels."""
    return mask & ~shrink(mask, round(6 * scale)) & grow(parent_visible, round(3 * scale))


def blend_seam(layer, mask, joint, parent_mask, scale):
    """Feather the seam so a rotated part blends into the parent instead of showing a hard cut. For parts that grow
    out of their parent without a drawn line (an ear rooted in fur). Only fades where the parent lies underneath,
    or the background shows through (an ear root that sticks out past the head)."""
    ramp = soft(shrink(mask, round(2 * scale)), CUT_FEATHER * scale)
    fade = grow(joint, round(2 * scale)) & mask & shrink(parent_mask, round(FADE_INSET * scale))
    out = layer.copy()
    out[..., 3] = np.where(fade, np.minimum(out[..., 3], 255 * ramp), out[..., 3])
    return out


def make_layer(original, painted, mask, visible):
    """Visible pixels from the original, hidden ones from the peel step that uncovered them; transparent outside the part."""
    v = soft(visible, 1.0)[..., None]
    out = original * v + painted * (1 - v)
    out[..., 3] = (original[..., 3] * v[..., 0] + painted[..., 3] * (1 - v[..., 0])) * soft(mask, 0.7)
    return out


def main(work, rig_path):
    rig = load_rig(rig_path)
    order, base, n = rig["order"], rig["base"], len(rig["peel"])
    load = lambda p: np.array(Image.open(os.path.join(work, p)).convert("RGBA")).astype(np.float32)  # noqa: E731
    steps = [load(f"norm/step{i}.png") for i in range(n + 1)]
    original = steps[0]
    size = original.shape[0]
    scale = size / 512
    char = original[..., 3] > 128
    segs = {k: read_seg(os.path.join(work, "seg-raw", f"step{k}.png"), rig["step_parts"][k], rig["colors"], size)[0] for k in range(n)}

    masks, src = {}, {}
    for part, k in rig["front_step"].items():
        masks[part] = segs[k][part] | segs[0][part]
        src[part] = steps[k]
    base_mask = steps[n][..., 3] > 128
    # Part maps stop 1-3 px inside the outline. Giving that ring to the base layer would leave the original outline
    # floating on the base when a part moves, so grow every part into it ring by ring; the base gets what is left.
    front = order[:-1]
    for _ in range(EDGE_RING):
        taken = base_mask.copy()
        for part in front:
            taken |= masks[part]
        left = char & ~taken
        if not left.any():
            break
        for part in front:
            g = grow(masks[part], 1) & left
            masks[part] |= g
            left &= ~g
    taken = np.zeros_like(char)
    for part in front:
        taken |= masks[part]
    masks[base] = base_mask | (char & ~taken)
    src[base] = steps[n]
    # Seams are where the part maps meet, so take them before the outlines move between parts.
    region_visible = visible_by_order(masks, order, char)
    joints = {part: seam(masks[part], region_visible[parent], scale) for part, parent in rig["parent"].items()}
    claim_outlines(masks, order, original, scale)

    os.makedirs(os.path.join(work, "layers"), exist_ok=True)
    layers, stats = {}, {}
    visible = visible_by_order(masks, order, char)
    for part in order:
        layers[part] = make_layer(original, src[part], masks[part], visible[part])
        stats[part] = {"pixels": int(masks[part].sum()), "visible": int(visible[part].sum()),
                       "painted": int((masks[part] & ~visible[part]).sum())}
    for part, parent in rig["parent"].items():
        if order.index(part) > order.index(parent):
            continue  # behind its parent: the parent covers the seam, nothing to blend
        joint = joints[part]
        if rig["parts"][part].get("seam", "keep") == "blend":
            layers[part] = blend_seam(layers[part], masks[part], joint, masks[parent], scale)
        band = soft(joint, 3 * scale)
        Image.fromarray((band * 255).astype(np.uint8)).save(os.path.join(work, "layers", f"joint_{part}.png"))
        stats[part]["joint"] = int(joint.sum())

    final = {part: np.rint(layers[part].clip(0, 255)).astype(np.uint8) for part in order}
    for part in order:
        Image.fromarray(final[part]).save(os.path.join(work, "layers", f"{part}.png"))
    for part, px in motion.make_roots(work, rig, final, joints).items():  # hidden behind the parent at rest
        stats[part]["root"] = px
    comp = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    for name in stack_back_to_front(rig):
        comp.alpha_composite(Image.open(os.path.join(work, "layers", f"{name}.png")))
    comp.save(os.path.join(work, "layers", "composite.png"))
    save_json(os.path.join(work, "layers", "stats.json"), stats)
    for part in order:
        s = stats[part]
        print(f"{part}: {s['pixels']} px, {s['visible']} visible in the original, {s['painted']} painted by the model"
              + (f", joint {s['joint']} px" if "joint" in s else "") + (f", root {s['root']} px" if "root" in s else ""))

    tiles = []
    for name in stack_back_to_front(rig):
        bg = Image.new("RGBA", (size, size), (200, 225, 245, 255))
        bg.alpha_composite(Image.open(os.path.join(work, "layers", f"{name}.png")))
        ImageDraw.Draw(bg).text((8, 8), name, fill=(0, 0, 0))
        tiles.append(bg)
    bg = Image.new("RGBA", (size, size), (200, 225, 245, 255))
    bg.alpha_composite(comp)
    ImageDraw.Draw(bg).text((8, 8), "stacked", fill=(0, 0, 0))
    tiles.append(bg)
    seg_view = np.full((size, size, 3), 230, np.uint8)
    for part in reversed(order):
        seg_view[masks[part] & char] = [int(v * 0.8) for v in rig["colors"][part]]
    tiles.append(Image.fromarray(seg_view).convert("RGBA"))
    cols = 4
    board = Image.new("RGB", (size * cols, size * ((len(tiles) + cols - 1) // cols)), "white")
    for i, t in enumerate(tiles):
        board.paste(t.convert("RGB"), ((i % cols) * size, (i // cols) * size))
    board.save(os.path.join(work, "layers-board.png"))

    # Peel steps on top, the part map painted on each one below: the quickest way to spot a stump or a merged part.
    steps_board = Image.new("RGB", (size * (n + 1), size * 2), "white")
    for k in range(n + 1):
        bg = Image.new("RGBA", (size, size), (200, 225, 245, 255))
        bg.alpha_composite(Image.fromarray(steps[k].astype(np.uint8)))
        ImageDraw.Draw(bg).text((8, 8), f"step{k}" + (f" -{'+'.join(rig['peel'][k - 1]['remove'])}" if k else ""), fill=(0, 0, 0))
        steps_board.paste(bg.convert("RGB"), (k * size, 0))
        if k < n:
            seg = Image.open(os.path.join(work, "seg-raw", f"step{k}.png")).convert("RGB").resize((size, size), Image.BOX)
            steps_board.paste(seg, (k * size, size))
    steps_board.save(os.path.join(work, "steps-board.png"))
    motion.board(work, rig)  # every jointed part turned both ways: the eye check for joints


if __name__ == "__main__":
    main(*sys.argv[1:])
