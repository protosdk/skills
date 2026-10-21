---
name: animal-layer-split
description: Split one 2D chibi animal character illustration (thick dark outlines, flat cel shading, a few flat colours, one character alone on a plain or transparent background, up to 9 moving parts, one pose) into rig-ready layers with the hidden areas painted in, plus a layered PSD, for cut-out or bone animation in Unity 2D Animation, Spine or Godot. Built and tested for four-legged animals in front or three-quarter view; side views fail. Uses codex image edits to peel parts off front to back, and scripts that align, colour-match and measure every step. Use when someone wants to rig or animate such an animal character drawn as one image, asks to 拆圖層, 分層, 切成頭/耳朵/手/腳/尾巴, or wants a 分層 PSD of it. Not for photos, 3D renders, painterly or pixel art, humans or humanoid characters, characters holding props, or scenes with several characters.
---

# Animal Layer Split

Turn one animal character image into layers a 2D rig can move: every part complete underneath (the top of
the head that the ear covered, the leg tops hidden under the belly), each with its own outline, stacked in
the original's order, with blended seams where a part grows out of its parent. The image model does the
painting; scripts do everything that has to be exact.

You do the layering. From the image alone you decide which parts become layers and how many, their
front-to-back order, what each hangs from and how its seam is treated. The user only gives the image, and
optionally the motion they want; they never have to say how to split it.

This is not a general 2D tool. It is tuned to one art direction and a small cast of animal characters, and
it says below exactly what it was tested on. Outside that, it is untested.

## When to use it

All of these hold:

- One finished illustration of **one cute or chibi animal character**: thick dark outlines, flat cel
  shading, a few flat colours, alone on a plain or transparent background.
- **Four-legged animals seen from the front or three-quarter view** are the main tested case. A standing bird
  with a folded wing has been split once. Other two-legged and winged animals are in scope but not tested
  yet (see below); say so to the user before starting.
- Up to 9 moving parts, one pose per split. Each pose that needs its own drawing (sleeping, standing) is
  split separately.
- The goal is cut-out or bone animation: parts rotate and move, the drawing is not redrawn per frame.

## Not for

Refuse and explain instead of trying. These either fail in known ways or have never been tried:

- Photos and 3D renders.
- Painterly, textured, gradient-heavy or watercolour art: part maps come back blurred and colour matching
  has nothing flat to hold on to.
- Pixel art: resizing to and from the image model's 1254 px destroys the pixel grid.
- Humans and humanoid characters: arms crossing the body, front and back hair, layered clothing are
  occlusions this method has never been tested on.
- Characters holding props, or attachments that move on their own (a cape, a dangling bag, a bell on a
  string). Worn items that move with one part (a collar, a bandana) are fine: they stay in that part's
  layer, see [references/parts-plan.md](references/parts-plan.md).
- Several characters, or a character in a scene.
- Heavily foreshortened views (a paw thrust at the viewer, a top-down view).
- Four-legged animals in side view, with near legs in front of far legs: known to fail. Once the body is
  peeled, the legs stand alone on the canvas, and the edit that removes the near pair redraws the far pair
  (9 of 9 tries on two test characters; see Tested on).
- A character that contains saturated #00FF00 green (it is the keying colour).
- Frame-by-frame animation, where each frame is a new drawing.

## Tested on

| Character | Parts | Evidence |
| --- | --- | --- |
| Curled-up four-legged animal, private project | 6 | Accepted split re-measured with these scripts: every check passes |
| Standing four-legged animal with four separate legs, private project | 9 | Split with a sibling pipeline, the case with the most failures. Its four recorded failures (an invented leg, a pale tail tip mapped as body, one of two legs left behind, a character redrawn from the text) are all caught by these checks; its accepted steps pass the new checks; this skill's drift and colour checks reject its last step. Not run end to end with `run.py` |
| Sitting four-legged animal wearing a bandana, private project | 5 | End to end with `run.py`: every check passes, the bandana kept in the body layer. Needed ears first (see parts-plan) and found the outline bug that gave the head a red sliver of the bandana, now fixed |
| Curled-up white arctic fox, private project | 6 | End to end with `run.py`: every check passes. Ears, head, paws, tail, body; white tail and body kept apart by the part maps. Found and fixed: late steps drew removed parts back (paws, a whole head), now named in the prompt; a white-on-white removal read as "not removed"; roots missing on an export whose alpha stops at 254 |
| Standing owl with one folded wing, private project | 3 | End to end with `run.py`: every check passes. Wing, head (ear tufts kept in it) and body (feet and leg ring kept in it); the head is cut from the body through continuous feathers with a `blend` seam. 2 of 3 head removals rejected for uneven colour. Finer feather texture than the other characters did not upset the drift check |
| Chibi puppy, side view, drawn by code for the private test suite (its main test character) | 8 | Fails. Peel steps 1-3 and part maps 0-3 pass; the step that removes the near legs failed 6 of 6 tries: the far legs moved 4 px and their colours shifted 4.6-24 levels, even with a reveal that names them as unchanged. An earlier side-view test character in teal failed the same step 3 of 3 |
| Winged critter, drawn by code for the private test suite | 7 | End to end, every check passes. A simple regression and sanity case, not evidence that mascots are supported |

## Not tested

- Birds and two-legged animals beyond the one owl: spread wings, both wings visible, separate legs that
  move, a head that turns far (only a gentle tilt is covered by one blended seam).
- Animals whose front legs work as hands.
- Humanoids of any kind.
- Side views where the far limbs are mostly hidden (side views with visible far legs fail, see Not for).
- Characters whose main colour is teal or cyan: on an earlier four-legged test character in teal, the
  image model shifted the teal much more than the pale colours on most edits and the colour check
  stopped the run (see [references/failure-modes.md](references/failure-modes.md)).
- Importing the PSD into Unity, Spine or Godot.

Needs: the `codex` CLI signed in (its built-in image tool does the edits), Python 3 with Pillow and numpy.
Run the scripts with `python3 -I`; check first with `python3 -c "import PIL, numpy"`.

## How it works

1. **Peel**, front to back. Each step asks the image model to remove one part (or a few that do not overlap)
   from the previous step's image and paint what was behind it. Edits come back as the input upscaled to
   1254x1254, so resizing them to the work size lines them up with the step before, pixel for pixel.
2. **Part maps.** Before each peel step, the model repaints the current image as flat colour regions, one
   colour per part still present. The map says which pixels the next removal may change; everything else
   is used to match colours and to measure drift, so a revealed area never counts as colour drift.
3. **Cut.** A part's full shape is its region in the part map of the step where it is frontmost. Pixels the
   original shows come from the original; hidden pixels come from the peel step that uncovered them. Stacked
   back up, the layers reproduce the original.

## Steps

1. **Plan the parts** with [references/parts-plan.md](references/parts-plan.md). You decide how many parts and
   which: give a layer to each part that moves on its own in the intended motion (a gentle idle if none was
   named), merge parts that always move together, keep tiny parts in their parent, never more than 9. Do
   not ask the user how to split. Show the plan as a table (step, what it removes, what it reveals, colour,
   and a one-line reason per part) before the first image edit, then start; wait only if the user asked to
   review it. Peel front to back as the drawing stacks at each part's
   root: a root hidden under its parent (leg tops under the belly) puts the part behind the parent; a part
   drawn over its parent (an ear's base across the head) stays in front. Group parts that do not touch
   (both ears) into one step. The rearmost part is the base and is never peeled. Give each part a `parent`
   (what it hangs from) and a `seam`: `keep` if the original draws a line where it overlaps its parent,
   `blend` if it grows out of the parent with no line. Avoid a last step that leaves one lone, elongated
   part (a tail by itself): the image API's output filter blocked that as a false positive.
2. **Write `rig.json`** in a work folder: [references/rig-config.md](references/rig-config.md). Describe each
   part by what is visible ("the curved horn on the viewer's left"), and for each step say concretely what
   the removal reveals: which outline continues, what colour fills it, what is behind.
3. **Run it.** `<skill>` is the folder this file is in:

   ```bash
   python3 -I <skill>/scripts/run.py character.png work/ work/rig.json
   ```

   It runs one image edit at a time, checks each one, retries a failing step twice (moving the rejected image
   to `work/rejected/`), and stops on a step that keeps failing. It is resumable: rerun the same command after
   a fix and it skips steps whose outputs exist. Each edit takes about 1-2 minutes; with retries, allow
   15-30 minutes for a 4-step split.
   Run it in the background and do not start anything else that calls codex.
4. **Look** at `work/steps-board.png` (each peel step over its part map), `work/layers-board.png` (each
   layer alone, the stack, the part map) and `work/motion-board.png` (each jointed part turned 15 degrees
   both ways: a wedge of background or a patch of fur past the outline means the joint needs attention). Numbers cannot tell you whether a removed part left a stump or the
   painted body looks like the character; your eyes can. Open the images, do not skip this.
5. **Read** `work/metrics.json`. Every check must pass: [references/checks.md](references/checks.md). When
   one fails, find its row in [references/failure-modes.md](references/failure-modes.md) before touching a
   prompt.
6. **Deliver** `work/layers/<part>.png`, `work/layers/<part>_root.png` (hidden roots that keep a turning part
   attached; bind each to its part's bone), `work/rig.psd`, `work/layers/joint_<part>.png` (where each part
   meets its parent: the band to skin to the parent bone) and the metrics. For engines see [references/engine-import.md](references/engine-import.md).

Running inside Codex with your own image tool? Either call `scripts/run.py` as above, or do each edit
yourself: give the image tool the IMAGE PROMPT part of `work/prompts/<step>.txt` with the named input, copy
the generated file unmodified to the named output, then rerun `run.py`, which picks up from there.

## Numeric checks

| Check | Limit | Catches |
| --- | --- | --- |
| Peel: whole-image shift after resizing back | ≤ 1 px | the edit recomposed or reframed the picture |
| Peel: local drift of everything not removed | ≤ 1 px in each direction | a part that should stay put was redrawn and moved |
| Peel: kept area repainted | ≤ 1 % | the model redrew inside the old outline (a new head on a headless body) |
| Peel: main colour left after the colour offset | ≤ 3 levels | colours that drifted unevenly (seams will show) |
| Peel: worst colour left after the colour offset | ≤ 8 levels | one colour shifted alone (pink turning purple) |
| Peel: new character outside the previous silhouette | ≤ 2 % | the model drew a new picture instead of editing |
| Peel: least changed removed part (colours changed or its lines gone) | ≥ 0.35 | a part that should be gone was left in place (one of two legs) |
| Part map: silhouette IoU vs the image it was painted on | ≥ 0.96 | the map was redrawn instead of painted over |
| Part map: colour painted outside the silhouette | ≤ 0.5 % | the map invented a part (a phantom leg) |
| Part map: smallest part share | ≥ 0.2 % | two parts merged into one colour, or a part dropped |
| Part map: smallest area kept from the previous map | ≥ 0.9 | a part handed some of its area to another (a pale tip given to the body) |
| Stack vs original: mean RGB difference | ≤ 3 levels | layers cut from the wrong source |
| Stack vs original: pixels differing by more than 30 | ≤ 3 % | holes, wrong layer order |
| Stack vs original: outline mismatch | ≤ 1 % | pieces lost or added at the edges |
| PSD: layers read back in order | exact | broken file |

## Rules

- **The model must edit, not redraw.** `codex_edit.py` puts an AGENTS.md in the work folder telling codex to
  pass the attached image to the image tool as the edit reference; once it skipped that and drew a new
  character from the prompt text. Keep that file.
- **One image edit at a time on a machine.** Parallel runs race: codex saves "the newest image" and two steps
  end up with the same picture. `codex_edit.py` holds a lock and verifies the file against the run's own
  session folder; do not bypass it.
- **Peel; never isolate.** Asking the model to "keep only the head" gets a complete head that is redrawn,
  resized and moved; it will not stack back onto the original.
- **Cut from part maps, never from before/after differences.** Where a removed part looks like what is behind
  it (orange forehead over orange body), the difference is near zero and the layer gets holes and jagged edges.
- **Never let the model post-process.** No background removal, resizing or cropping in codex; the templates
  say so and the scripts do it.
- **Measure, do not trust the model's report.** Codex says "the composition changed" when only the size did,
  and says nothing when an ear moved 5 px.
- **Shift colour means only.** Scaling the spread lets the dominant colour pick the factor and pushes small
  colours off.
- **Keep the prompt templates fixed** (`scripts/templates/`). Every sentence there fixes a failure. Change the
  character words in `rig.json`; change a template only with a before/after measurement.
- **Rejected images are evidence.** Move them aside, never delete them.

## Report

Tell the user: the layer list (front to back, pixels, how many the model painted), every check with its value
and limit, what you looked at on the boards, and what was not tested (for example "not imported into Unity").
A check that was not run is "not run", never "passed".
