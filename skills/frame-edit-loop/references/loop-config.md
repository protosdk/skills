# loop.json

One file in the work folder describes the whole loop: what the image model is told, what the checks
measure, how frames are stabilised, moved and timed. Coordinates are px on the 1024 work canvas that
`prep.py` makes (the illustration centred on a square, nothing cropped); open `in/art.png` to read them.
Boxes are `[x0, y0, x1, y1]`, ellipses `[cx, cy, rx, ry]`, rects in `scene` are normalised `[x, y, w, h]`.

Scripts read only the keys below; anything else is ignored, so a `"note"` key is a fine place for reasons.

## Top level

| Key | Used by | Meaning |
| --- | --- | --- |
| `name` | build | Prefix of the output files (`<name>-00.png`) |
| `subject` | prompts | The character as it is visible: kind, pose, view, what it holds ("a chibi animal character in a jacket, standing and holding a book against the chest, three-quarter view, head turned to the viewer's left"). No story, no name needed |
| `style` | prompts | What must look the same: "warm dark outlines, line thickness, colors and soft cel shading" |
| `pace` | prompts | One word for the loop: calm, busy, frantic |
| `motion` | prompts | `"slow"`: every prompt forbids afterimages. `"fast"`: frames may name a `smear` |
| `ms` | build | Milliseconds per output frame. 60 (16.7 fps) in both tested loops |
| `parts` | prompts, shift | What stays locked (below) |
| `frames` | run, prompts, stabilize | Every frame the image model draws, in drawing order (below) |
| `color` | run | `{"ref": "art" or a frame, "box": [...]}`: colours are matched to `ref`, fitted inside `box` on pixels that show the same thing. Use a box over parts that never change (head, horns, ears); `ref` is `"art"` unless the first keyframe changed a lot of the picture (an open book replacing a closed one), then that keyframe |
| `stabilize` | stabilize | The reference frame and loop-wide settings (below) |
| `warp` | build, check | Small motion (below) |
| `timeline` | build, check | The loop, frame by frame (below) |
| `mirror` | build | `true` flips every output frame left-right (the character faces the other way) |
| `preview` | build | Solo GIF: `{"background": [r, g, b], "crop": "auto" or [box], "pad": 24, "scale": 0.5}` or `"size": [w, h]` |
| `scene` | build | Optional scene GIF (below) |
| `review` | sheet | `{"body": [box], "closeup": [box]}` for the keyframe sheet; body defaults to the illustration's outline plus 30 px |

## parts

```json
{"name": "ear_left", "describe": "the long drooping ear on the viewer's left", "box": [170, 269, 319, 368]}
```

Every part goes into the prompt's keep list ("Keep both small horns, the long drooping ear on the viewer's
left, ... exactly where they are"), in this order, unless the frame lists it in `moves`. Parts with a `box` are also measured by the
shift check; parts without one are words only (the eyes and where the pupils look, the brows).

Draw each box tightly around one part's outlines: `run.py` refuses a box with fewer than 50 outline pixels,
and a box that takes in a neighbour that moves makes the part fail when only the neighbour moved. Check them
on `review/boxes.png` (`sheet.py <work> boxes`). Box every rigid part that must not jitter: horns, ears,
glasses, nose and mouth, a shoulder, a held prop, legs and feet, tail.

## frames

```json
"k02b": {
  "from": "k02",
  "kind": "inbetween",
  "change": "this frame is halfway through raising the hand to the glasses. Lower the raised arm on the viewer's left about halfway back down: ... Draw the nose, the mouth, the chin and the collar that the hand was covering, exactly as they look in the rest of the character.",
  "moves": ["shoulder", "mouth"],
  "keep_also": ["the hand on the viewer's right holding the book against the chest"],
  "patch": {"from": "k01", "box": [0, 0, 1024, 494], "feather": 3},
  "stabilize": {"outside": [[250, 360, 730, 830]]}
}
```

| Key | Meaning |
| --- | --- |
| `from` | `"art"` (the illustration) or an earlier frame. Edit from the frame it plays next to, so the two match. The first keyframe is edited from `"art"` and every other frame from it or from its neighbours |
| `kind` | `"key"` (default) or `"inbetween"`: one word in the prompt |
| `change` | The ONE change, concretely: which part, which way, how far, what it covers and what it uncovers ("Where the moving hand used to be, draw the book cover, the tie and the jacket that were behind it") |
| `moves` | Parts that change in this frame: left out of the keep list and not measured |
| `keep_also` | Extra keep-list phrases for this frame only (the prop exactly as it is, the other hand) |
| `smear` | `motion: "fast"` only: the one part that gets a motion smear ("the hand holding the pen") |
| `reference` | `{"image": "ref/desk-book.png", "use": "a perspective reference for the open book"}`: a second image attached as a reference only (path in the work folder) |
| `patch` | After colour matching, copy `box` from another frame, feathered (PIL rectangle: x1 and y1 included). For an area this edit had to repaint from nothing that the other frame shows correctly (a nose that was under the hand) |
| `stabilize` | `keep`, `outside`, `force_ref`, `drop_cool_outside` (below) |

## stabilize

Loop-wide, under `"stabilize"`:

| Key | Meaning |
| --- | --- |
| `ref` | The frame every other frame is stabilised against; default the first frame. Usually the first keyframe |
| `force_ref` | Boxes always taken from `ref`, in every frame (where a detail is erased and overlaid instead) |
| `erase` | `[{"name": "drop", "box": [...], "select": "B-R>5"}]`: remove a small detail drawn into `ref` (a sweat drop on the cheek) by filling it from the colour around it, and save it as `sprites/<name>.png` to overlay where the timeline wants it. `select` is a channel difference true on the detail and false around it |
| `sprites` | `[{"name": "fly", "frame": "f02", "box": [...], "select": "B-R>20", "min_alpha": 60}]`: cut an effect drawn in a frame (a drop flying off) into `sprites/<name>.png` (`cutout.py` does the same by hand) |

Per frame, under `frames.<name>.stabilize`:

| Key | Meaning |
| --- | --- |
| `keep` | `"diff"` (default): keep this frame's pixels where they differ clearly from `ref`. Or `{"ellipses": [[cx, cy, rx, ry], ...], "feather": 10}`: keep only inside these (eyes and brows of an expression frame); use this when only a face changes, so the rest cannot shimmer at all |
| `outside` | Boxes where this frame may put new pixels outside `ref`'s silhouette (a raised elbow, a smear by the hand). Default none: with `"diff"`, nothing new survives outside the silhouette. `"keep"` turns the rule off for this frame (and the outside check with it) |
| `force_ref` | Boxes taken from `ref` in this frame only |
| `drop_cool_outside` | Inside the `outside` boxes, also drop new pixels that are bluer than red: echo lines the model drew next to a smear. Needed only for edits made before the template forbade echoes |

## warp

```json
"warp": {
  "fields": [
    {"name": "sway", "shape": "all", "pivot": [500, 820]},
    {"name": "head", "shape": {"band": [455, 545], "minus": {"polygon": [[640, 430], [1024, 430], [1024, 1024], [640, 1024]], "feather": 40}}, "pivot": [585, 505]},
    {"name": "ear_right", "shape": {"polygon": [[712, 215], [800, 190], [920, 270], [910, 420], [770, 410], [715, 335]], "feather": 30}, "pivot": [732, 285], "clamp": 1.5}
  ],
  "waves": [{"field": "sway", "amp": [1.2, 0, 0], "cycles": 2}, {"field": "head", "amp": [0.6, 0, 0], "cycles": 2, "lag": 2}],
  "images": {"f02": {"head": [0, 0, -0.8]}}
}
```

Each field moves the pixels under its weight shape by `[degrees, dx, dy]`: turned around `pivot`, then
shifted. Fields apply in list order, each on the result of the ones before, so put the whole-body field
first and the parts that ride on it after. Shapes: `"all"`, `{"band": [y_full, y_none]}` (rows above
`y_full` move fully, fading to none at `y_none`), `{"ellipse": [...], "feather": f}`, `{"polygon": [...],
"feather": f}`, each optionally with `"minus": <shape>`. `clamp` limits a field's degrees.

A frame's pose, per field: the sum of every wave on it, `amp * sin(2 pi * cycles * (i - lag) / frames)`
with `i` the output frame; plus `images.<image shown>.<field>`; plus the timeline entry's `warp.<field>`.
A wave with `lag` follows another a few frames late (a head that follows the body, ears a beat behind it).

Keep moves to a few px. `check.py` fails a stretch above 0.12: move the fade (`band`, `feather`) onto
background or flat fill, never across a thin part such as an ear, or make the move smaller.

## timeline

```json
"timeline": [
  {"image": "k01", "hold": 8},
  {"image": "k05", "warp": {"head": [-1.05, 0, 4.9]}},
  {"image": "f01", "overlays": [{"sprite": "drop", "at": [708, 306], "scale": 0.6, "opacity": 1.0, "angle": 0}]},
  {"repeat": 4, "entries": [{"image": "f01"}, {"image": "f02"}, {"image": "f03"}, {"image": "f05"}]}
]
```

Each entry is one output frame (`hold` repeats it). `image` is any frame from `frames` (stabilised). An
overlay sprite is pasted centred on `at` before the warp, so it moves with whatever it sits on. The loop
plays from the first entry to the last and back to the first: make the last frame lead into the first.

## scene

```json
"scene": {
  "background": "/abs/path/background.png",
  "layers": [
    {"image": "/abs/path/chair.png", "crop": [39, 28, 935, 996], "rect": [-0.03, 0.52, 0.20, 0.35]},
    {"character": true, "rect": [-0.010, 0.355, 0.183, 0.4335]},
    {"image": "/abs/path/desk.png", "rect": [-0.005, 0.534, 0.36, 0.43]}
  ],
  "crop": [0, 300, 640, 900], "scale": 1.5
}
```

Layers stack in list order: the ones before `character` behind it, the ones after it in front. The
character layer is each frame cut back to the illustration's own canvas, so use the rect the illustration
has in the scene. `crop` is in background px, applied before `scale`. The scene is for the preview only.
