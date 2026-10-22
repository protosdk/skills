# Checks

`run.py` checks every drawn frame as it comes back; `check.py` checks the built loop and writes
`metrics.json`. Lengths are px on the 1024 work canvas, colours levels of 255.

The limits come from two accepted loops of one character from a private project (a seated busy-writing
loop with motion smears, 7 drawn frames; a standing reading loop, 12 drawn frames), replayed through these
scripts from the recorded image edits, and from deliberately broken copies of them. That is little data:
when a loop passes and still looks wrong, the eye wins, and the case belongs in
[failure-modes.md](failure-modes.md).

## Shift: locked parts at (0, 0)

For each part with a `box` that the frame does not list in `moves`, `shift.py` takes the outline pixels
(mean RGB below 70, alpha above 128) of the edit and of the image it was edited from, both resized to
1024, and finds the offset within ±10 px that overlaps them best (intersection over union; a tie goes to
the smaller move). Every part must come out at exactly (0, 0). A frame edited from the illustration may be
off by 1 px: the illustration does not play in the loop, and that frame becomes the reference for all the
others. A failing edit is moved to `rejected/` and redrawn, up to 6 tries.

Why exactly 0: at 16 fps a part that is 1 px off in alternate frames visibly jitters, and the frames are
compared against the image they play next to. The project owner asked for "redraw until there is no
shift" on the reading loop.

Measured: all 19 accepted frames pass. Overlap at the best offset was 0.73-0.97 (lowest on the glasses,
whose thin lines re-render softer). On the recorded reading loop the check rejected 5 edits: 1 px on the
glasses or an ear (4 times, one frame needing 4 tries), and one edit that ignored the prompt and raised
the arm (shoulder +9, +5). In the live blink run it rejected 3 of 6 edits, all for 1 px. Broken input: the left ear of an accepted edit moved 1 px and 2 px: both fail,
the unmoved copy passes.

A box needs at least 50 outline pixels in the illustration, or `run.py` stops before the first edit: a box
on flat fill measures nothing. Lowest in the tested boxes: 568 (nose and mouth). Outlines lighter than
mean RGB 70 are not seen at all; such art is untested.

## Colour: tint left after matching ≤ 2.0 levels

Each edit comes back a few levels off (warmer, bluer, darker), differently each time; frames that
alternate then flash. `run.py` matches each frame's per-channel mean and spread to the colour reference,
fitted inside `color.box` on pixels both frames have that show the same thing (no channel more than 30
apart). What is left is measured over the whole frame, on flat fill only (2 px away from any luminance
step above 12) that shows the same thing: per channel the mean signed difference, worst channel.

Measured: before matching 1.4-7.1 (reading 1.4-6.4, busy 1.8-7.1); after matching 0.03-1.62 (reading)
and 0.51-1.49 (busy); live blink 0.5-2.9 before, 0.76-1.34 after. Matching can raise a tint that was
already small (0.5 to 1.17 on one live frame): it fits the spread too, which a uniform offset would not. Broken input: one accepted edit with only the body below the head re-tinted +8 red,
which matching on the head cannot see: 2.43, fails; the other frames stay at 1.62 or less. The margin
between 1.62 and 2.43 is thin; tighten the limit when a passing loop flashes.

## Outside: nothing new past the silhouette

For every output frame, the reference frame is moved by the same pose (and mirrored if `mirror`), and the
frame's pixels with alpha above 16 more than 2 px outside that silhouette are counted, apart from the
frame's `outside` zones (grown 15 px, since the pose carries the part along) and the overlay sprites.
Limit 0.

`stabilize.py` already drops such pixels from frames kept by difference, so this is the final check that
nothing came back through a warp, an ellipse mask or an overlay. Measured: 0 on both accepted loops; while
stabilising, the busy loop's two smear edits had 4341 and 5656 px of echo outline dropped. Broken input:
an echo outline of the head 8 px up and right painted into a stabilised smear frame: 1751 px, fails.

## Stretch ≤ 0.12

For each pose, the warp's Jacobian on every character pixel (the frame before overlays): its singular
values' largest distance from 1. 0.1 means a line is stretched or squashed by 10 % there.

Measured: 0.108 (busy, where the left ear's top edge meets the crown) and 0.106 (reading, under the chin
at the bottom of the nod). The limit 0.12 was set by the agent during the first loop, not from a failure
someone saw; in both loops the agent widened a fade band or moved a mask edge to get under it (0.163 at
the chin with a larger nod and a narrower band, 0.16 at the ear root). Broken input: the reading loop's nod with its band
narrowed from 470-590 to 470-570: 0.135, fails.

## Export inside the canvas

`build.py` exports each frame cut to the illustration's own canvas (on the work canvas), so the
illustration's placement in the engine applies unchanged. If any frame has pixels outside that canvas (a
raised arm past the illustration's edge) it writes no export and says which frame.

## Not checked by numbers

Look at these yourself; no script judges them:

- Whether a keyframe is the same character in the same style (face, proportions, props in perspective).
- Whether a prop keeps its shape across frames: the shift check measures only boxed parts, and a part in
  `moves` is not measured at all.
- Whether the motion reads: the GIF at speed, and single frames at full size around every image change
  (`check.py` lists them).
- Seams of the stabilise masks and patches: open the frame, not just the board.
