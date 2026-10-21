# Checks

`scripts/check.py` measures every step and writes `metrics.json`; the limits live in its `LIMITS`.
Lengths are in px at a 512 work size and scale with `size`. Colours are levels of 255.

The limits were calibrated on two characters: a 6-part cel-shaded animal from a private project (its
accepted split, re-measured with these scripts) and the sample critter, a simple horned and winged creature
drawn by code (7 parts) whose recorded run the privately maintained test suite replays after every script
change. "The sample puppy" below is the suite's side-view four-legged character (8 parts). The four semantic checks (new character
outside the silhouette, removed part changed, map outside the silhouette, area kept) and their limits come
from a second pipeline, calibrated on accepted versus redone steps of a 9-part standing four-legged
character from the same private project; all four of its recorded failures fail here, its accepted steps pass. Both pass every limit. The drift and colour
checks were also fed deliberately broken input to confirm they fail (a region shifted 1, 2 and 3 px: measured
1, 2 and 3; one colour pushed +10: measured 7.4); the other checks were not tested that way.
Treat the limits as calibrated on little data: when a split passes but looks wrong, the eye wins and the
limit should be tightened, with the case written down.

## Peel steps (one per removal)

Every peel step is measured against the step before it, only where nothing should change: pixels both
images have, minus the parts this step removes (from the part map painted before it) and 12 px around them,
where new content is expected. `peel.py norm` writes the numbers to `metrics/peel-step<k>.json`;
`check.py` recomputes them from the images.

**Global shift ≤ 1 px.** After resizing the edit (1254) to the work size, `peel.py norm` searches ±3 px
for the offset that best overlaps the silhouettes. Edits that keep the composition come back at 0. More
than 1 means the model reframed the picture; the edit is rejected and redone. A non-square output is
rejected outright.

**Local drift ≤ 1 px.** Everything that was not removed should not move. `tile_drift` compares the edge
maps of the two steps in 64 px tiles and finds, per tile, the shift (±4 px) that best lines the edges up.
A tile only counts as moved if that shift matches clearly better than no shift (IoU gain ≥ 0.05) and the
match is good (IoU ≥ 0.5; poorer tiles were repainted, not moved). The worst tile's distance is the
value. Smaller tiles wobble by a pixel on line re-rendering alone, so 64 is deliberate.

**Colour residual: main ≤ 3, worst ≤ 8.** Each edit drifts 3-9 levels, so `peel.py norm` shifts the
edit's mean colour onto the previous step, over the stable pixels whose brightness differs by less than
25. What remains is measured per colour: flat fill only (lines come back softer, which is not a colour
drift), grouped into 32-level bins covering ≥ 3% of those pixels. "Main" is the largest bin, the colour
most seams run through; "worst" is any bin. Accepted splits measured main 0.84-1.44 and worst 2.13-5.21
(reference character), main 0.89-2.73 and worst 2.63-5.08 (sample critter). A colour scaled instead of
shifted (the failure where pink turned purple) is around 11. On the sample critter this gate rejected two
edits that re-tinted the body (main 7.58: teal lost 16 levels of red while the pale belly lost 6; and worst
8.14), and the drift gate rejected two that moved a wing 1.4 and 2.2 px. All four redos passed. On an
earlier teal four-legged test character the colour gate rejected 7 of 12 peel attempts, all with the same pattern (teal -8 to -13
red, pale and cream -2 to -3) and stopped the run: a known limit of the single offset, see
[failure-modes.md](failure-modes.md).

**New character outside the previous silhouette ≤ 2%.** Pixels of the edit outside the previous step's
silhouette (grown by max(3, size/128) px for resizing and soft edges), as a share of that silhouette. A peel
step only removes and repaints, so accepted steps add 0-0.2%. An edit where codex skipped the attached image
and drew a new character from the prompt alone added 29% (it also failed the global shift).

**Least changed removed part ≥ 0.35.** For each part this step removes, its area in the previous part map,
and the share of it where the two steps differ by more than 40 levels in any channel after a 2 px blur (so
line re-rendering does not count). The lowest part is the value. Accepted steps: 0.57-0.99 on the private
characters, 0.45-1.0 on the sample critter (0.45 is a teal arm removed from a teal body: similar colours
change less), 0.79-0.97 on the sample puppy's accepted steps, 0.77-1.0 on an earlier teal four-legged test
character. An edit that removed one of two legs left that leg at 0.00.

**Kept area repainted ≤ 1%.** The share of the area that should stay put (both steps opaque, outside the
removed parts and 12 px around them) where the blurred images differ by more than 40. Accepted steps:
0-0.003 on four characters. An edit that drew a whole new head, face and paws onto a headless body stayed
inside the old silhouette, so the outside check passed and drift skipped the repainted tiles; this measured
0.199. Two edits that also drew outside the silhouette measured 0.014 and 0.021.

**Drift counts px in each direction.** A diagonal move of 1 px is 1, not 1.41: three accepted-looking edits of
a white fox failed on (1, 1) alone. Real drift in the recorded failures was 2-4 px.

**The removed-part check counts vanished lines too.** For a part the same colour as what is behind it (a
white tail on a white body) the colour barely changes: 0.27-0.32 of its area, below the 0.35 limit, though the
tail was gone. 0.76-0.81 of its own lines had vanished. The value is now the larger of the two; accepted
removals measure 0.77-0.99, a leg left in place 0.00 either way.

The mask matters. Fitted on every pixel of similar brightness, the offset also counts the revealed area:
a light head replaced by a darker body reads as 10 levels of drift, the whole image is shifted by it, and
the error compounds step after step (seen: +10, then +18 levels of red).

There is no "≤ 1 level after matching" check on purpose: measured on the pixels that set the offset, the
residual is zero by construction and can never fail. The main-colour residual is the closest real measure.

## Part maps (one before each peel step)

**Silhouette IoU ≥ 0.96.** The map's character area against the alpha of the image it was painted on.
Accepted maps measured 0.963-0.979 (reference character, fur edges) and 0.986-0.990 (sample critter, clean
outlines). Below that the model redrew the shape instead of painting over it.

**Painted outside the silhouette ≤ 0.5%.** Map colour outside the silhouette of the image it was painted
on (grown by max(3, size/128) px), as a share of that silhouette. Accepted maps: 0. A map that invented a
leg in an empty gap: 1.48% and 1.06%. This is the strict version of the IoU check above, which passed the
same maps at 0.950, only 0.01 under its limit.

**Smallest part share ≥ 0.2%.** Every part the map should contain covers at least this share of the
character. Less means two parts came back in one colour, or the label no longer fits what is left.

**Smallest area kept from the previous map ≥ 0.9.** As front parts come off, the parts behind can only
become more visible, so each part present in both maps keeps at least 90% of its previous area. The label
names where the lost area went. A map that gave a pale tail tip to the body kept 0.73 of the tail.

The last two only gate where the map shapes a layer: map 0 for every part, map k for the parts that are
frontmost in step k (and a part that lost area to one of those). Elsewhere a finding is printed as a
warning, because no layer is cut from it.

## The stack

`build_layers.py` stacks the layers back to front; `check.py` compares the stack with the original.

| Check | Limit | Reference character (blend seams) | Sample critter (keep seams) |
| --- | --- | --- | --- |
| Mean RGB difference where both are opaque | ≤ 3.0 | 1.20 | 0.13 |
| Pixels differing by more than 30 | ≤ 3% | 1.28% | 0.05% |
| Character pixels whose alpha differs by more than 60 | ≤ 1% | 0.67% | 0.81% |

With `"keep"` seams the stack is the original, give or take rounding. With `"blend"` seams the differences
sit on the faded edges, where a little of the painted layer underneath shows. The limits allow blending;
they do not catch a `"blend"` set where the original has a drawn line (the sample critter with every seam
blended still measured 1.82 and 2.3%, and passed). That one is for your eyes: a faded outline on the layers board.

## Joints in motion (reported, not gated)

`motion.py` turns every part with a parent by -15 and +15 degrees around its pivot, with its root layer if
it has one, and counts background pixels that open between the part and its parent within 60 px of the
pivot. `check.py` prints it per joint, with and without the root, and `motion-board.png` shows it. Measured:
a sitting animal's ears 66 and 93 px without roots, 26 and 29 with; the critter's horns 35 to 24-27, arms 15-16 to
0; heads, wings and parts behind their parent 0-38. There is no limit yet: the pivot is a guess and two
characters are not enough to set one. Look at the board.

## PSD

`write_psd.py --check` reads every layer back and compares position and pixels with its PNG; `check.py`
confirms the layer order. Not checked: how any particular engine imports the file. Say so in the report.

## Not measured, so look

- A removed part that left a stump, a shadow or a smear.
- Painted areas that do not look like the character (wrong fur direction, a new object).
- A part map that put a detail (an eye, a strap) on the wrong part.
- Thin hidden pieces the model added that are never visible at rest but show when a part moves.
