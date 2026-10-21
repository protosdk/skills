# Planning the parts

The parts plan is the one thing that changes per character, and it decides the result more than any
script. You decide it, including how many parts: do not ask the user how to split. Make it from a close
look at the image, show it as a table with a reason for each part, then write it into `rig.json`
([rig-config.md](rig-config.md)) and start. Wait for the user only if they asked to review the plan first.

## Decide how many parts

- **Start from the motion.** If the user said what the character will do (breathe while asleep, walk, wave
  its tail), give a layer to every part that moves on its own in that motion. If they did not say, plan for
  a gentle idle: lying animals breathe, flick an ear and move the tail; standing animals also shift their
  legs, so each leg gets its own layer.
- **A part earns a layer only if it moves relative to its parent.** Eyes, markings, blush stay inside their
  parent. Blinks and expressions are sprite swaps, not peel steps.
- **Worn items that move with one part stay in that part's layer** (a collar or a bandana with the body or
  the neck, a hat that never comes off with the head). Name them in that part's `describe` ("the body (...
  the red bandana around the neck with its knot ...)"), and in the `reveal` of the step that uncovers them,
  so their hidden edge is completed ("the top edge of the red bandana and its knot completed"). Keep every
  part-map colour far from the item's colour: no red part with a red bandana. Tested once: a bandana in a
  sitting animal's body layer, every check passed. An item that swings on its own (a cape, a dangling bag,
  a bell on a string) is out of scope.
- **Pairs:** separate layers when they move out of step (walking legs, ears that flick one at a time); one
  layer when they always move together (two front paws resting side by side in a sleeping pose).
- **Too small to split:** a part under about 1% of the character's area (a tiny tail tip, a tooth) maps
  unreliably and rarely earns its two edits. Keep it in its parent.
- **Fewer is safer.** Each part adds a part-map colour, usually a peel step (two codex edits) and another
  chance for drift. Choose the smallest plan that covers the motion, never more than 9 parts (the most
  tested; the palette's 11 colours are a hard ceiling). If the motion needs more, say so and split the
  character into two rigs (head and body) instead.
- **Starting points from the tested cases:** a curled-up four-legged animal, 6 parts: two ears, head, front
  paws as one layer, tail, body. A standing four-legged animal, 9 parts: two ears, head, four legs, body,
  tail. For body plans that are in scope but untested (two-legged, winged, front legs used as hands), use the
  same rules and tell the user the plan is untested.

In the plan table, give each part one line of reason ("left and right ear: flick separately"; "paws
merged: they rest together"), so the user can see what you merged and why without being asked.

## Order: follow the drawing at each part's root

Peel front to back, exactly as the drawing stacks. Look at every overlap, and look hardest at where each
part's root goes:

- **The root disappears under the parent** (a leg whose top is hidden under the belly, an arm going into a
  sleeve): the part is *behind* its parent. Peel the parent first, so the model paints the hidden root.
  Peeled the other way round, the root ends in a straight cut that slides over the parent when the part
  rotates.
- **Except ears and horns.** They stick out of the head with a long visible part and a short hidden base.
  Peel them first, even when the head's outline is drawn across their base, and give them a `blend`
  seam. With the head peeled first, the model had to invent the hidden ear roots, drew long stalks down to
  the neck and moved the visible ears (3 of 3 tries); ears first passed on the first try.
- **Body first leaves the legs alone on the canvas.** Peeling the body before its legs paints the hidden
  roots, but then only loose legs remain, and edits on a nearly empty canvas get redrawn rather than
  edited. In a side view, removing the near legs then moved the far legs every time; side views are out of
  scope for that reason. Front and three-quarter views with the body peeled first are untested: the
  tested standing character had its legs peeled while the body was still there, and its leg roots came
  out as straight cuts. Tell the user which trade-off the plan makes.
- **The part's lower end is drawn over the parent** (an ear whose base lies across the top of the head, a
  horn drawn on the forehead): the part is *in front* of its parent. Putting it behind sends that strip to
  the parent's layer, and the part breaks in two when it rotates.
- **Overlaps between siblings count too:** a near leg drawn over a far leg is peeled before it.
- **Parent means attached to, not overlapping.** A chin resting on a paw does not make the paw the head's
  parent; the head hangs from the body.
- **Remove symmetric parts together** when they do not touch each other (both ears, both near legs): one
  edit instead of two, and the part map still tells them apart by colour. Say "BOTH ..., so that none is
  left" in `remove_text`; the model sometimes removes only one, and `peel step: least changed removed
  part` then fails at about 0.
- **The last step should not leave one lone, elongated part** on the canvas. The image API's output
  filter has blocked a lone tail as a false positive. A round part, or two or more parts, is fine.

## Labels must stay true at every step

A part's `describe` is used in the part map of every step where the part is still there. Write it so it is
still true after the parts in front of it are gone. "The darker leg just behind the near front leg" stops
making sense once the near legs are removed, and the model then invents a leg to fit the words. Add the
fallback in the same label: "(if the near legs are already gone, simply the darker leg on the viewer's
left)". `partmap step: painted outside the silhouette` catches an invented part; it is better not to
invite one.

Say which colours belong to a part when they look like another part: "the whole tail, including its cream
tip; the whole tail is one part". Without that a pale tip tends to be mapped as body, and
`partmap step: smallest area kept` fails, naming the part that took it.

## Colours

Give the catch-all part ("everything else that belongs to the character (...)") a saturated colour. Do not
use white for it when the character has white, cream or pale areas: the model tends to leave those areas
white in the map, which hands them to the catch-all part. White is fine when nothing on the character is
pale. (The sample critter, a code-drawn test character, breaks this rule: its catch-all is its cream wings, so a cream area left white
lands where it belongs, but its pale belly patch could still have gone to the wings. It did not, that time.) Keep every part colour far from the character's own colours and from the green background.

## Show the plan

Before any edit, show the user a table like this (the main test character of the private test suite, a
chibi puppy seen from the side and drawn by code; its run fails at step 4, see "Tested on" in SKILL.md):

| Step | Removes | Reveals | Colour | Why its own layer |
| --- | --- | --- | --- | --- |
| 1 | ear | top and back of the head | blue | flops when the head moves |
| 2 | head | front of the body (everything else locked) | red | turns and nods; eye and muzzle stay in it |
| 3 | body | tops of all four legs, the part of the tail behind the body | magenta | breathes; the root of everything |
| 4 | near front leg, near back leg (both) | the far legs where the near legs covered them | yellow, cyan | each leg steps on its own |
| 5 | far front leg, far back leg (both) | nothing (green); the tail stays | purple, azure | each leg steps on its own |
| base | tail (everything else) | | pink | wags |

Eight parts for a standing idle. The far ear is not drawn, so there is no layer for it.

Why this order: the floppy ear's root lies over the top of the head, so the ear is in front of the head and
comes off first. The head overlaps the body. All four leg tops disappear under the belly, so the legs lie
behind the body, and the body comes off before any leg. The near legs overlap the far legs. The fluffy tail
sits behind the body; it is round, so leaving it alone in the last step is safe. Cream belly, paws and tail,
so the catch-all is pink, not white. Step 2's reveal also names what must stay put: on an earlier test
character the body's outline moved 2 px whenever the head was removed, until the reveal said so.

Parents: ear on head; head, legs and tail on body; body is the root. Seams: every part here is outlined
where it meets its parent, so all stay `keep` (the default); a part rooted in fur with no line would be `blend`.
