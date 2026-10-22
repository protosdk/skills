# Planning the loop

Decide, before the first edit, what the character does in one loop and how each part of that motion is
made. Show the plan as a table and the timeline in words, then start the keyframes.

## What the character does

The user names the action (writing busily, reading notes on a board, blinking). Pick concrete beats a
viewer can read at the size the character is shown: a stroke of the pen, a page turned, a glance down,
a nod. Do not decide what the action means in the user's game or story; if a beat needs that (should
it smile when it has read the note?), ask.

## Three ways to make a motion

| Motion | Made by | Why | Examples from the tested loops |
| --- | --- | --- | --- |
| A part changes shape or crosses something: more than about 3 px, or anything a warp would have to invent | **A drawn frame** (image edit) | Only the model can draw a hand in a new place, a turning page, closed eyes | A pen hand sliding 40 px along the page; a page turning in three stages; a hand rising to push up the glasses; eyes narrowing, looking down, closing |
| A whole area shifts or turns a few px, keeping its shape | **A warp** (`warp` in loop.json) | A redrawn head always comes back 1 px off; a warp of the frame that is already right cannot drift | Body sway of 1.2°; a nod of 7 px and 1.5°; ears lagging the head by a beat; a book shaken by the pen, 2.5 px |
| A small effect that moves on its own | **An overlay sprite** (`erase`, `sprites`, timeline `overlays`) | Its path and timing stay editable without new edits | A sweat drop that forms, slides and is flung off |

Plan the large moves as drawn keyframes, then add drawn in-betweens where a move would otherwise jump,
then warps and overlays on top. Every drawn frame is edited from the illustration or from an accepted
frame, never drawn new.

## Keyframes, then in-betweens

1. **First keyframe**, edited from the illustration: the loop's resting pose (eyes on the board; the book
   opened and the pen on the page). Everything later is measured against it.
2. **Other keyframes**, each edited from the first keyframe (or from the one it plays next to): one change
   each.
3. **Show the keyframes and wait for the user's OK** before drawing in-betweens or building a GIF. In the
   first loop the user stopped the work here: the two halves of the held book were drawn from different
   angles, and every frame already edited from that keyframe had to be redrawn.
4. **In-betweens**: a key pose held for 300-900 ms and then swapped looks like a slideshow next to a
   hand-drawn 15 fps loop. Add drawn halfway frames between poses that differ a lot (half-closed eyes
   between open and closed; the hand halfway up), edited from the neighbour they play next to.

## Timing

- 60 ms per frame (16.7 fps) in both tested loops; 15-17 fps reads as hand-drawn animation.
- Holds are repeated frames: a glance held 12 frames is 0.72 s.
- Both loops were 2-4 s (37 and 62 frames). The loop must close: the last frame leads into the first.
- Small motion that runs through the loop (sway, breathing) is a wave with a whole number of `cycles`, so
  it closes too.

## Fast motion and afterimages

Set `"motion": "fast"` only for a frantic action where a part jumps 25-45 px between frames (a pen hand
scribbling). Then the in-between that carries the jump may be a smear frame: `smear` names that one part,
and the prompt asks for paler copies of it along its path, nothing else.

Never put an afterimage on a part that moves only a few px. In the first fast loop the model was asked for
an echo outline around the head and shoulders as well; the head moved 2-3 px with the sway, so the outline
8 px out matched no motion, and since smear frames came every other frame it blinked about 8 times a
second, which the project owner found painful to watch. The template now forbids it and `stabilize.py` drops
anything new outside the silhouette except in the frame's `outside` zones.

For a calm action (`"motion": "slow"`) no frame gets an afterimage, ghost copy or motion blur.

## Facing the other way, and the scene

- If the character has to face the other way in the scene, plan the frames on the illustration as it is
  and set `"mirror": true`; do not ask the model to redraw it mirrored. Check what mirroring moves to the
  other side (a pin on one lapel, a parting): the reading loop's lapel pin ended up on the other side from
  the seated pose, hidden by a desk.
- A `scene` preview places the frames between the scene's layers. Ask the user what is in front of the
  character: in the reading loop the desk and chair were in front of it, which the first staging got wrong.

## The plan table

| Frame | From | Kind | Change | Moves | Made by |
| --- | --- | --- | --- | --- | --- |
| k01 | art | key | pupils to the board | eyes | drawn |
| k02 | k01 | key | hand up to the glasses bridge | arm, shoulder, book, mouth | drawn |
| k02b | k02 | in-between | hand halfway up | arm, shoulder, mouth | drawn, nose patched from k01 |
| - | - | - | nod 7 px, 1.5° on k05 | head | warp |

Then the timeline in words with frame counts and ms, for example "look 8, glasses 10, look 4, squint 13,
lower row 13, nod 8, look 6: 62 frames x 60 ms = 3.72 s".
