---
name: frame-edit-loop
description: Turn one finished 2D character illustration (立繪; chibi, cel-shaded, dark outlines, one character alone on a transparent background) into a short frame-by-frame loop and a preview GIF at about 16 fps, in the same pose. Keyframes and in-betweens are codex image edits of the illustration, one change at a time; every locked part is measured for shift and the edit redrawn until nothing moved. Small motion (sway, a nod, ears that lag, a shaking prop) is a smooth warp, effects like sweat are overlays, frames are stabilised so nothing shimmers, and the GIF keeps exact timing. Built and tested on one chibi sheep character in clothes holding a book, in three loops (busy writing with smears; calm reading; a blink). Use when someone wants an idle or action loop from a character illustration, or asks for 關鍵幀, 補幀, 中間幀, 殘影, 逐幀動畫 or a 預覽 gif. Not for walk cycles, turns or other big pose changes, rigs or cut-out animation (see animal-layer-split), photos, 3D, painterly or pixel art, or several characters.
---

# Frame Edit Loop

Make a looping animation out of one character illustration without ever drawing the character again:
every frame is a small edit of the illustration or of a frame next to it, and everything that must stay
still is measured until it does. The image model draws the changes; scripts key, align, stabilise,
move, time and check.

You plan the frames. From the action the user wants, you decide which poses are drawn keyframes, which
are drawn in-betweens, what is a warp and what is an overlay, and the timeline. The user approves the
keyframes before anything is built on them.

This is not a general animation tool. It is tuned to one art direction and was tested on one character in
three loops, listed below. Outside that, it is untested.

## When to use it

All of these hold:

- One finished illustration of **one character**: chibi, cel-shaded, dark outlines (mean RGB below 70),
  a few flat colours, alone on a transparent background. Clothes and a held prop are fine: that is what
  was tested.
- The loop keeps **the pose** and moves parts of it: a hand writing or pushing up glasses, eyes looking,
  squinting or closing, a page turning, the head nodding a few px, the body swaying a degree.
- The result is frame-by-frame: PNG frames plus timing for an engine, and a GIF to preview.

## Not for

Refuse and explain instead of trying:

- Walking, turning around, standing up, a head turned far, anything where most of the drawing changes:
  every frame would be a new drawing, and nothing would stay still to measure against. Not tried.
- Rigs, cut-out or bone animation: use animal-layer-split (animals without props or clothes).
- Photos, 3D renders, painterly, textured or watercolour art, pixel art (resizing to the model's 1254 px
  and back destroys the pixel grid).
- Several characters, or a character drawn inside a scene. Scene layers are only for previews.
- Outlines lighter than the shift check sees (mean RGB 70 or above): `run.py` stops when a locked part's
  box has no outline pixels.
- A character that contains saturated #00FF00 green (the keying colour); `prep.py` refuses it.

## Tested on

| Loop | Character | Frames | Evidence |
| --- | --- | --- | --- |
| Busy writing: fast strokes with smears on the pen hand, a page flip, body sway, sweat | Seated chibi sheep character in clothes, holding an open book and a quill, private project | 7 drawn, 37 out at 60 ms | Accepted by the project owner after two fixes (the book's perspective, an echo outline that flickered). Replayed offline through these scripts from the recorded edits: the same 37 frames as the accepted loop, apart from faint keying specks these scripts remove (alpha 13 or less, at most 5 levels visible); every check passes |
| Reading notes on a board: look, push up glasses, squint, look down, nod; no smears; mirrored | Same character standing, holding the book | 12 drawn (6 key, 6 in-between), 62 out at 60 ms | Accepted. Replayed offline: the same 62 frames, apart from the same specks; every check passes. During the original run the shift check rejected 5 of 17 edits |
| Blink | Same standing illustration | 3 drawn, 39 out at 60 ms | Live run of these scripts end to end: 6 edits for 3 frames (the closed-eyes frame rejected 3 times for 1 px on an ear or the glasses, accepted on the 4th); every check passes; single frames show no mask seams. Not reviewed by the project owner |

## Not tested

- Any other character, an animal without clothes, a four-legged animal, a human.
- Art with medium or light outlines, soft shading or gradients.
- Loops longer than 62 frames, or slower than 16 fps.
- Importing into an engine: frames from both loops went into a Unity project, but no import is part of
  these tests.

Needs: the `codex` CLI signed in (its built-in image tool does the edits), Python 3 with Pillow, numpy and
scipy (the warp needs scipy's spline resampling), and ffmpeg for the GIF. Run every script with
`python3 -I`; if the packages are missing, `uv run --with pillow --with numpy --with scipy python -I`.

## How it works

1. **Edit, never draw.** The first keyframe is an edit of the illustration; every other frame is an edit
   of the first keyframe or of the frame it plays next to. Each prompt lists what stays locked and names
   ONE change.
2. **Shift check.** Each locked part's outlines are compared with the image the edit was made from; the
   best offset must be (0, 0), or the edit is moved to `rejected/` and redrawn.
3. **Key, colour, stabilise.** The edit is resized back (it comes back as the input upscaled to 1254),
   keyed, colour-matched, and every pixel that was not meant to change is taken from the reference frame,
   so the model's small redraws do not shimmer. Nothing new survives outside the silhouette except where a
   frame is allowed to reach (a raised arm, a smear by the hand).
4. **Move and time.** Large moves are drawn frames; moves of a few px are smooth warps of a frame that is
   already right; effects are overlay sprites. The timeline repeats and orders the frames at about 60 ms.
5. **Preview and export.** A GIF with one palette and ordered dithering, and PNG frames cut back to the
   illustration's own canvas, so its placement in the engine applies unchanged.

## Steps

1. **Plan** with [references/motion-plan.md](references/motion-plan.md): what the character does, which
   poses are drawn (keyframes, in-betweens), which moves are warps or overlays, the timeline in frames and
   ms. Show it as a table before the first edit. Ask the user only what is theirs to decide (what the
   action means, what is in front of the character in the scene), not how to make it.
2. **Prepare** the illustration (`<skill>` is the folder this file is in):

   ```bash
   python3 -I <skill>/scripts/prep.py character.png work/
   ```

3. **Write `work/loop.json`** with [references/loop-config.md](references/loop-config.md): the subject,
   the locked parts with boxes on their outlines, and **only the keyframes** in `frames`. Then draw the
   boxes and look at them:

   ```bash
   python3 -I <skill>/scripts/sheet.py work/ boxes      # work/review/boxes.png
   ```

4. **Draw the keyframes**, one edit at a time, in the background:

   ```bash
   python3 -I <skill>/scripts/run.py work/
   ```

   Each edit takes 1-3 minutes; with redraws allow 5-10 minutes per frame. Do not start anything else
   that calls codex. The run is resumable: rerun the same command after a change.
5. **Show the keyframes and wait.** `sheet.py work/` writes `work/review/keyframes.png` (the illustration
   and every frame, whole body and close-up). Look for a different character, a prop in the wrong
   perspective, a face that is off; then show the sheet to the user and wait for their OK. To redo a
   frame: move `raw/<frame>.png` into `rejected/`, change its `change` or `keep_also`, rerun `run.py`,
   and redo every frame edited from it.
6. **Add the in-betweens** (and smear frames for fast motion) to `frames` and rerun `run.py`.
7. **Build:** write `stabilize`, `warp`, `timeline`, `preview` (and `scene`) in `loop.json`, then

   ```bash
   python3 -I <skill>/scripts/stabilize.py work/
   python3 -I <skill>/scripts/build.py work/
   python3 -I <skill>/scripts/check.py work/
   ```

   Timing and motion changes need only these three steps, no new edits.
8. **Look.** Every check in `work/metrics.json` must pass ([references/checks.md](references/checks.md));
   on a failure, find its row in [references/failure-modes.md](references/failure-modes.md) first. Then
   open `out/motion-board.png`, `out/solo.gif` (and `out/scene.gif`), and **single frames at full size**
   around every image change that `check.py` lists. The flicker in the first loop was found by stepping
   through single frames, not by the GIF.
9. **Deliver** `out/export/` (PNG frames on the illustration's canvas and `<name>.json` with the timing),
   the GIFs as previews, and `loop.json` with `raw/` so the loop can be rebuilt or retimed later.

Running inside Codex with your own image tool? Give the tool the IMAGE PROMPT part of
`prompts/<frame>.txt` with `in/<from>.png` as the image to edit, save its output unmodified as
`raw/<frame>.png`, then rerun `run.py`, which checks it and goes on.

## Numeric checks

| Check | Limit | Catches |
| --- | --- | --- |
| Shift: best offset of each locked part against the image it was edited from | (0, 0); 1 px for the first keyframe against the illustration | a part the edit moved: at 16 fps 1 px jitters |
| Locked part's outline pixels in the illustration | ≥ 50 | a box on flat fill, which measures nothing |
| Colour: tint left on unchanged flat fill after matching | ≤ 2.0 levels | an uneven re-tint (the body warmer than the head): the frames flash when they alternate |
| Outside: new pixels past the reference silhouette moved by the same pose, apart from the frame's zones and overlays | 0 px | an echo outline around the head or body, leftover background |
| Stretch: warp stretch on the character | ≤ 0.12 | a warp that bends lines (a fade band across an ear) |
| Export: every frame inside the illustration's canvas | all | an arm cut off at the canvas edge |

## Rules

- **Edit, never redraw.** A frame comes from the illustration or an accepted frame, with one change. Edit
  from the frame it plays next to, so the two match.
- **Locked means (0, 0).** Redraw an edit with a 1 px shift; do not accept it because it is small.
- **Keyframes are approved before in-betweens and GIFs.** Everything later is built on them.
- **Small moves are warps.** A redrawn head always comes back a little off; warp the frame that is right.
- **Afterimages only on a part that really moves fast** (25-45 px between frames). Never an echo outline
  around a head or body that moves a few px: it blinks on every other frame. Slow motion gets none.
- **One image edit at a time on a machine.** `codex_edit.py` holds a lock; do not bypass it.
- **Never let the model post-process.** No background removal, resizing or cropping in codex; the template
  says so and the scripts do it.
- **Measure, do not trust the model's report.**
- **Keep the prompt template fixed** (`scripts/templates/edit.txt`). Change the character's words in
  `loop.json`; change the template only with a before/after measurement.
- **Rejected images are evidence.** Move them aside, never delete them.

## Report

Tell the user: each drawn frame with its tries and why rejected ones failed, every check with its value
and limit, what you looked at (which single frames), the timeline (frames x ms = loop length), the export
size, and what was not tested (for example "not imported into the engine", "not watched on a device").
A check that was not run is "not run", never "passed". The GIF is a 256-colour preview; the PNG frames
are the result.
