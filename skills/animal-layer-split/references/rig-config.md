# rig.json

One file describes the character's parts, the peel order and the words that go into the prompts. The
scripts derive everything else from it (which part map gives each part its shape, which colours each map
uses, which seams get blended).

```json
{
  "subject": "a round cartoon creature with two small curved horns and two small wings, sitting, drawn with flat colors, simple cel shading and thick dark outlines",
  "style": "thick dark outline, flat teal color and simple cel shading",
  "size": 512,
  "parts": {
    "horn_left": {"color": "#0000FF", "parent": "head", "describe": "the curved cream horn on the viewer's left"},
    "horn_right": {"color": "#00FFFF", "parent": "head", "describe": "the curved cream horn on the viewer's right"},
    "head": {"color": "#FF0000", "parent": "body", "describe": "the round head (the face with the eyes, the pale muzzle with the nose and the mouth, the pink cheeks and the top of the head)"},
    "arm_left": {"color": "#FFFF00", "parent": "body", "describe": "the arm on the viewer's left (the rounded teal arm with the cream hand)"},
    "arm_right": {"color": "#FF8000", "parent": "body", "describe": "the arm on the viewer's right (the rounded teal arm with the cream hand)"},
    "body": {"color": "#FF00FF", "describe": "the round body (the teal belly with the big pale belly patch)"},
    "wings": {"color": "#FFFFFF", "parent": "body", "describe": "everything else that belongs to the creature (the two small cream wings behind the body)"}
  },
  "peel": [
    {"remove": ["horn_left", "horn_right"], "reveal": "the top of the head continues as one smooth round outline, filled with the same teal color; above it is the flat green background"},
    {"remove": ["head"], "reveal": "the top of the round body continues as one smooth round outline, filled with the same teal color and shading as the rest of the body; above it is the flat green background"},
    {"remove": ["arm_left", "arm_right"], "reveal": "the sides of the round body, completed with the same smooth round outline, teal color and shading; behind each arm, the cream wing with its thin veins continues where the arm covered it"},
    {"remove": ["body"], "reveal": "the inner parts of the two cream wings that the body covered: each wing continues inward to a rounded root, with the same outline, cream color and thin veins; between the two wings is the flat green background"}
  ],
  "base": "wings"
}
```

This is the plan of the sample critter, a code-drawn test character from the privately maintained test
suite. A four-legged plan, with labels that stay true after the parts in front are gone, is shown and
explained in [parts-plan.md](parts-plan.md#show-the-plan).

## Fields

| Field | Meaning |
| --- | --- |
| `subject` | What the picture is, in a phrase that finishes "Using the uploaded image of ...". Include the drawing style. |
| `style` | The drawing style to continue in painted areas: "Use the same ... as the rest of the character". |
| `size` | Work size in px (square). 512 is tested; layers come out at this size. 1024 is the ceiling: edits come back at 1254. |
| `parts.<name>` | One layer. Names are lower_snake_case ASCII: they become PSD layer names and file names. |
| `parts.<name>.color` | The part's colour in the part maps, from the palette below. |
| `parts.<name>.parent` | The part it hangs from in the rig. Leave it out for the root. |
| `parts.<name>.seam` | `"keep"` (default) or `"blend"`: what happens at the seam with its parent when the part lies in front of it. See below. |
| `parts.<name>.root` | Depth in px (at 512) of the hidden root layer a part in front of its parent gets, default 16; `0` for none. See [engine-import.md](engine-import.md#joints-that-turn) |
| `parts.<name>.pivot` | Optional `[x, y]` in work-size px: where the part turns, for the motion board and the gap report. Default: the middle of the part's pixels that lie over its parent |
| `parts.<name>.describe` | The part as it looks, used in both the peel and the part-map prompts. |
| `peel[]` | Front to back. `remove` lists the parts this step takes off; `reveal` says what to paint where they were. Optional `remove_text` replaces the joined `describe`s. |
| `base` | The rearmost part, what is left after the last peel. Its `describe` should start with "everything else that belongs to ...". |

Every part appears exactly once, in one `peel[].remove` or as `base`. `load_rig` stops with a message otherwise.

## Palette

Part-map colours must be far apart and far from the green background. Use these (the prompt names them):
`#FF0000` red, `#0000FF` blue, `#00FFFF` cyan, `#FFFF00` yellow, `#FF00FF` magenta, `#FF8000` orange,
`#8000FF` purple, `#0080FF` azure, `#FF80C0` pink, `#808080` grey, `#FFFFFF` white (not for a character
with pale areas, see [parts-plan.md](parts-plan.md#colours)). `prompts.py` refuses colours outside it or
closer than 120 RGB units to each other. Eleven colours means at most eleven parts; split a bigger character
into two rigs (a body rig and a head rig) rather than inventing colours.

## Writing the words

- **Viewer's left / right**, never the character's. "The ear on the viewer's left (with the pink heart)": a
  position plus one visible detail tells two similar parts apart.
- **Describe what is visible**, with the details that belong to the part listed in brackets. Things on a part
  (eyes, a scarf knot, a belt) go in that part's description, or the part map gives them to the wrong layer.
- **Say what the removal reveals**, concretely: which outline continues and how ("one smooth round outline"),
  what fills it ("the same teal color and shading"), what is beyond it ("above it is the flat green
  background"). A vague reveal gets a hole, a stump, or a new object.
- **Keep labels true after the parts in front are gone**, and say which colours belong to a part when they
  look like another part. Order, grouping and colour choice: [parts-plan.md](parts-plan.md).
- **Group only parts that do not touch.** Two ears in one step is fine; an arm and the hand it holds is not.
  For a group, say "BOTH ..., so that none is left" in `remove_text`.

## Seams: keep or blend

Look at where each part meets its parent in the original.

- **A drawn line between them** (a cartoon arm outlined over the body, a horn outlined on the head): `"keep"`.
  The part keeps its own outline. Blending would fade that outline and the stack would no longer look like
  the original.
- **No line; the part grows out of its parent** (an ear rooted in fur, a tail growing out of the back):
  `"blend"`. The part fades into its parent over 4 px there, so a rotated part does not show a hard cut.

One character can need both. `"keep"` is the default because it never changes how the character looks at
rest; a wrong `"blend"` passes every check while softening lines you can see.
