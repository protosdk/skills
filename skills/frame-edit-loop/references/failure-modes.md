# Failure modes

Every row happened while making the two tested loops. Find the symptom before changing a prompt; most
fixes are not prompt changes.

## Image edits

| Symptom | Cause | Fix |
| --- | --- | --- |
| codex treats the prompt as an image file name and fails | `codex exec -i` takes several values and swallowed the prompt | `codex_edit.py` passes the prompt on stdin and ends the `-i` list with the next flag. Do not call codex by hand |
| Two frames saved the identical picture | Two codex runs in parallel; each copied "the newest image" | One edit at a time. `codex_edit.py` locks and checks the file against the run's own session folder |
| A locked part 1 px off (an ear, the glasses), again on the retry | The model redraws the whole picture and thin lines next to the change wobble | Redraw; it passed on the 2nd to 4th try in practice. Do not accept "only 1 px": at 16 fps it jitters |
| The edit ignored the prompt and moved something else (an arm raised to the chin on an eyes-only frame) | The model sometimes acts out the action instead of the one change | Caught by the shift check (shoulder +9, +5); redraw. Name the part that must stay ("both hands holding the book against the chest") in the keep list |
| A prop drawn in the wrong perspective: the two halves of an open book seen from different angles, the cover a thick box | The model drew the prop from the text, not from the scene's camera | Redraw only the prop, with an image of a similar object in the scene's perspective attached as `reference`, and say what is wrong and what right looks like ("both pages in one nearly flat plane, the spine one straight line") |
| A part that was covered and is uncovered again comes back different (a nose smaller and pinker after the hand over it moved away) | The edit was made from the frame where it was hidden, so the model had to invent it | `patch` the area from the frame that shows it (the first keyframe), feathered, before the frame is used for further edits |
| A turning page redrawn as a fresh page, its edge dropped 10 px | The prompt did not say the page under it stays as it is | Name it in `keep_also` with its outline, colour and ink lines; reject and redraw |
| Smear copies came back grey-green | The model removed the green itself; the semi-transparent copies kept green spill | `key_green` pulls semi-transparent pixels to grey whether the output came back green or transparent |
| Edits 2-7 levels bluer or warmer than the reference, each differently | Every edit drifts | Expected: `run.py` matches colours; the colour check catches what matching cannot fix |
| `build.py` writes no export: a frame has pixels scattered over the whole canvas | Keying left alpha 1-2 specks where the green came back slightly off; the first keyframe is copied into every frame | `run.py` drops separate blobs whose strongest pixel is below alpha 32 (1444 px on one live keyframe) |
| The body stored at alpha 240-254 turned the whole character slightly green on the model's input | The illustration's export leaves the body just under opaque | `prep.py` treats alpha 240 and up as opaque |

## The loop

| Symptom | Cause | Fix |
| --- | --- | --- |
| The head and shoulders blink with an outline ring on every other frame; painful to watch | Smear frames also had an echo outline of the head and body; the head moves 2-3 px, so the echo matched no motion | Smears only on the part that really moves fast (`smear`); the template forbids echoes. `stabilize.py` drops new pixels outside the silhouette except in `outside` zones; the outside check confirms |
| The whole character shimmers at 16 fps although nothing moves | Each edit redraws everything: lines wobble 1 px, colours a level or two | `stabilize.py`: pixels that did not really change come from the reference frame |
| Key poses held for 300-900 ms look like a slideshow | Too few drawn frames | Drawn in-betweens between poses that differ a lot, 60 ms frames |
| Optical-flow interpolation (ffmpeg minterpolate) blurred the lines and ghosted large moves | Interpolation does not understand line art | Never interpolate: draw in-betweens, warp small moves |
| A nod by a redrawn head came back shifted | A redraw of the head always moves it a little | Nod by warp: a `band` field with its pivot under the chin |
| Stretch 0.16 under the chin at the bottom of the nod | The nod was too large for its fade band (470-570) | Widen the band onto flat fill (470-590) and make the move gentler (7 px, 1.5°): 0.106 |
| Turning an ear tugged the crown of the head | The ear field's soft edge ran across the head outline | Move the polygon so only the ear root lies on the head, pivot at the root |
| The seated hips rock on the seat with the body sway (tail and knees 3-5 px) | Sway turns the whole body around one point | Judged acceptable by the project owner in the busy loop. If not, give the sway field a shape that excludes the lower body |
| Ink scribbles on a page flicker a little | Each edit redraws the scribbles slightly differently, under the stabilise threshold | Known, small, accepted. Keep scribbles few and coarse in the first keyframe |
| A sweat drop drawn into the reference frame stays put while the head moves, or doubles | It was part of the drawing | `stabilize.erase` lifts it into a sprite and fills the spot; `force_ref` keeps every frame's own drawn drop out; the timeline overlays it |
| Facing the other way with a mirrored loop moves a one-sided detail to the other side (a lapel pin) | Mirroring is exact | Check one-sided details; if one shows, fix that detail in the first keyframe |
| The GIF bands soft shadows, or still areas shimmer | Pillow's quantizer without dithering; error-diffusion dithering moves with any change | `gif.py`: one palette for the animation, Bayer dithering, Pillow writes the timing. Ship PNGs, not the GIF |
| The exported frames are smaller than the illustration (768x1024 for a 1086x1448 drawing) | The work canvas is 1024; the model's output is the 1024 input upscaled, so there is no more detail | Say so in the report. In the tested cases the difference did not show at the size the game displays the character |

## Work

| Symptom | Cause | Fix |
| --- | --- | --- |
| An uncommitted work folder vanished with its checkout | A temporary checkout was recycled | Keep the work folder somewhere lasting, or commit it; codex's originals stay in `~/.codex/generated_images/<session>/`, and `logs/raw-<frame>-<try>.json` records which file each try is |
| Frames built after a fix still show the old keyframe | Later frames were edited from the old one | After changing a frame, redraw every frame whose `from` chain leads to it |
