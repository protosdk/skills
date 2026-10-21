# Failure modes

Every row happened in a real split. Find the symptom before changing a prompt; most fixes are not prompt changes.

## Image edits

| Symptom | Cause | Fix |
| --- | --- | --- |
| Codex says "the composition changed, not usable as the next step" | The edit came back at 1254x1254 instead of 1024. It is the input upscaled, not reframed | Nothing. Resize back (the scripts do) and measure; trust `global shift`, not the message |
| Two steps saved the identical picture | Two codex runs in parallel; each copied "the newest image" | One edit at a time. `codex_edit.py` locks and checks the file against the run's own `~/.codex/generated_images/<session>/` |
| Edit is darker or lighter by 3-7 levels, a little more each step | Every edit drifts | Expected. `peel.py norm` shifts the mean back onto the previous step |
| One colour off after matching (pink turned purple) | Colour spread was scaled, not just shifted, so the dominant colour picked the factor | Shift means only (`peel.py` does). If `worst colour residual` still fails, redo that edit |
| `colour residual` fails on most tries of one character, always the same colours (one hue family shifted 8-13 levels, pale areas 2-3) | The model re-tints that hue family whenever it repaints a large area; one mean offset cannot correct two different shifts | Known limit, not fixed in v1. Retrying sometimes passes (the teal sample critter did; an earlier teal four-legged test character did not, at 7 of 12). Seen most with teal; a warm brown character had it on one step (2 of 3 tries). Do not loosen the limit to get through: the hidden painted areas will not match the visible ones. Per-colour matching is the candidate fix |
| Edit is not square, or `global shift` > 1 | The model recomposed the picture | Rejected and redone automatically. If it keeps happening, the reveal asks for something that does not fit the frame |
| Removing the head first turned the ears into long stalks reaching down to the neck, and moved the visible ears 1.4-4 px (3 of 3) | The ears' bases were drawn under the head outline, so the plan put them behind the head and peeled the head first; the model then had to invent hidden ear roots and drew stalks | Peel ears and horns first, even when the head outline crosses their base, and set their `seam` to `blend`; it passed first try. "Peel the parent first" is for roots that are short and buried, like leg tops under a belly |
| A part that should stay moved 2-6 px (`drift`) | The model redrew more than it was asked to. Seen most on thin parts next to the change (ears beside a head being edited) | Redo the edit. If it repeats, remove the moving part in an earlier step, or name it in `reveal` as unchanged |
| A stump, smear or outline left where a part was | `reveal` too vague about what continues there | Describe the continuing outline and fill ("the top of the head continues as one smooth round outline") and what is beyond it |
| The edit is a different drawing of the character: shifted, reposed, 29% outside the old silhouette | Codex called the image tool without the attached image as the edit reference and drew from the prompt alone | The work folder's AGENTS.md (written by `codex_edit.py`) tells codex to pass the reference; keep it. `new character outside the previous silhouette` and `global shift` reject the edit |
| Removing the near legs of a side-view four-legged animal moves the far legs (4 px, every try) and re-tints them | After the body is peeled, the legs stand alone on an empty canvas, and the model redraws what is left instead of editing it. Naming the far legs as unchanged in `reveal` did not help (6 of 6) | Known to fail, not fixed: side views are out of scope. Peeling legs while the body is still there avoids it but gives straight-cut leg roots. A front or three-quarter view does not put near and far legs in one step |
| A late step draws removed parts back: paws reappear, or a whole new head and face on a headless body (2 of 3 tries on one fox) | Every peel prompt opened with the full description of the character, and little of it was left in the image, so the model "corrected" the picture | The peel template now lists the parts removed in earlier steps and says they stay removed (0 of 3 after). `kept area repainted` catches a redraw inside the outline; a part drawn back inside the area being repainted is still only caught by eye |
| A white part removed from a white body fails `least changed removed part` | Colour barely changes when the part matches what is behind it | Fixed: the check also counts the part's own vanished lines |
| Root layers come out tiny, so turning ears still open wedges | The export's alpha stops at 254 and roots were only placed where the parent is 255 | Fixed: "solid" is alpha > 250 everywhere |
| One of two parts in a group is still there (one leg left) | The model removed only one | `least changed removed part` fails near 0 and the step is redone. Say "BOTH ..., so that none is left" in `remove_text` |
| The background came back transparent instead of green | The image tool sometimes returns RGBA | Fine: `to_rgba` uses the alpha as is |
| The model removed the background, cropped or resized itself | It was allowed to post-process | Keep the template sentence "Do not post-process the image yourself" |
| No image saved; the log says `moderation_blocked` / `safety_violations=[...]` | The image model's output filter flagged the edit. Seen as a false positive on an innocent character when a peel step left one isolated, elongated, rounded part (a lone tail) | Retrying did not help (2 of 2 attempts blocked). Change what the step leaves alone: peel in a different order, keep a larger base, or split the rig so no step ends with a lone tube-like shape |
| Colours shift more each step (offsets of 10, then 18) | The colour offset was fitted on revealed pixels too: a light part replaced by a darker one reads as drift | Fit only outside the removed parts. `run.py` paints each part map before the next peel step so `peel.py norm` can mask them |
| `codex did not start a session` | Not logged in, unknown model, or codex refused the folder | Run `codex exec --skip-git-repo-check -m <model> "say hi"` by hand and fix that first; the scripts do not retry this |

## Part maps and cutting

| Symptom | Cause | Fix |
| --- | --- | --- |
| Head layer has holes, tail edge is jagged | Layers were cut from the difference between two peel steps; where the removed part looks like what is behind it, the difference is near zero | Cut from part maps (what `build_layers.py` does) |
| Each part is complete but will not stack back (line overlap 0.2-0.5 after aligning) | The model was asked to "keep only part X"; it redraws the part, changing size and position | Peel instead. Isolation prompts are not a fallback |
| Silhouette IoU < 0.96 | The model redrew the shape | Redo the map. The template's "keep EXACTLY the same silhouette" and "do not move, resize or redraw" are what keep it at 0.96-0.98 |
| A thin ring of the original outline floats on the base layer when a part moves | Part maps stop 1-3 px inside the outline and the ring went to the base | `build_layers.py` grows each part into the ring first (`EDGE_RING`) |
| The map shows a part that is not in the image (a phantom leg in a gap) | The label no longer fits what is left in that step ("the leg between the front legs" after the front legs are gone), so the model invented something to match | `painted outside the silhouette` fails. Rewrite the label with a fallback that stays true ([parts-plan.md](parts-plan.md#labels-must-stay-true-at-every-step)) |
| A pale area of a part is mapped as another part (a cream tail tip as body) | The model reads colour, not structure | `smallest area kept` fails and names the part that took it. Say in the label that the pale area belongs to the part; do not use white as the catch-all colour |
| Two parts in one colour; check "smallest part share" fails | Colours too similar, or the descriptions overlap | Use palette colours far apart; make each `describe` claim distinct visible details |
| An eye or strap lands on the wrong layer | Not listed in that part's `describe` | List it in brackets in the owning part's description |

## Joints

| Symptom | Cause | Fix |
| --- | --- | --- |
| A thin white line or broken fur appears at a joint when a part moves | Hard cut edge where the part grows out of its parent | Set that part's `seam` to `"blend"`: it fades into its parent over 4 px where they meet in the original |
| A part's outline looks washed out or grey on its layer | `"blend"` on a part whose original draws a line over its parent | Set `seam` to `"keep"` (the default) |
| A line stays behind on the parent layer when a part moves (a chin line left on the body) | Part maps put the boundary anywhere across the line between two parts, so a strip of the front part's outline went to the part behind | Each part claims the dark pixels connected to its edge, front first (`claim_outlines`). It stays off the character's outer outline, or it would grow dark spurs along it |
| A part's layer carries a sliver of a neighbouring saturated colour along its outline (a red bandana under the chin moves with the head) | Outline claiming took anything with luminance under 100 as line, and saturated red is 76 | Fixed: a line must also be dark in every channel (`LINE_MAX`), and the 1 px fringe takes only line-to-fill blends (`FRINGE_MAX`) |
| A 2-3 px dark tick on a part's edge | Where a rear part's interior line meets the front part's outline (a T-junction), the claim follows that line for up to 3 px | Known, small. Not fixed in v1 |
| Background shows through at a joint | The seam faded where nothing lies underneath (an ear root that sticks out past the head) | Fade only where the parent lies at least 10 px deep underneath (`FADE_INSET`) |
| An ear breaks in two when it rotates | The ear was ordered behind the head though the drawing puts its base over the head, so the base went to the head layer | Order parts as the drawing overlaps them |
| Seam detection marks almost every edge as a cut | Detected seams by "is there an outline nearby"; a furry character has lines everywhere | Detect seams as "touches the parent in the part maps" (`seam` in `build_layers.py`), and let the rig say which seams blend |

| A part looks detached when it turns: a wedge of background opens at its base (an ear flicking off the head) | The part is in front of its parent and ends where it was cut; nothing lies behind the parent's outline to fill the gap | Each such part gets `<part>_root.png`, hidden behind the parent and moved with the part; better still, skin the base to the parent bone ([engine-import.md](engine-import.md#joints-that-turn)) |
| A flat patch of fur without an outline shows past the parent's outline when a part turns far | The root layer swung beyond the parent's silhouette | Smaller `root` for that part, smaller angles, or skin the base instead |
| Turning a part leaves a smear of the parent's colour or outline over the background | A connecting strip was copied into the part's own layer, which sits in front | Roots go in their own layer behind the parent, filled with flat fur colour (tried and dropped: copying the parent into the part, extending the part's own edge pixels) |

## Out of scope here (later skills)

- Joints that hinge instead of bend, parts moving at unrelated rhythms: rig and motion, not layering.
- GIF previews with banding or flicker: palette per animation plus ordered (Bayer) dithering, with frame
  timing written by Pillow; error-diffusion dithering makes still areas flicker when something moves.
