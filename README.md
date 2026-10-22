# Skills for 2D Game Animation

Agent skills that make AI agents better at 2D game animation work: splitting characters into rig layers,
editing frames without breaking the character, and checking the result with numbers instead of guesses.

**These are not general-purpose tools.** They are tuned to one art direction (cute, chibi animal characters
with thick dark outlines and flat cel shading) and to a small cast of animal characters, and they move
further in that direction as the characters do. Each skill lists what it was tested on, what it was not
tested on, and what it refuses. Outside those lists, expect it not to work.

Image models are good at painting and bad at precision. Ask one to remove an ear and it usually does; it
also quietly moves the other ear 4 px, darkens everything by 5 levels, and reports that the composition
changed when it did not. An agent that trusts the picture ships a rig that jitters and seams that show.

These skills put the model where it is strong and scripts everywhere else. Each one comes with:

- **Deterministic scripts** for every step that has to be exact: cutting, aligning, colour matching, file
  writing.
- **Numeric checks with limits**, so "looks fine" becomes "drift 0 px, silhouette overlap 0.97, pass".
- **Fixed prompt templates**, where every sentence fixes a failure seen in practice.
- **Documented failure modes**: the symptom, the cause, and the fix, including the fixes that look right and
  are not.

## Install

```bash
npx skills@latest add protosdk/skills
```

Works with any agent that reads `SKILL.md` (Claude Code, Codex and others). The skills call the `codex` CLI
for image edits and need Python 3 with Pillow and numpy; frame-edit-loop also needs scipy, and ffmpeg for
its GIF previews.

## Skills

- **[animal-layer-split](./skills/animal-layer-split/SKILL.md)**: split one chibi animal character drawn as a
  single image into rig-ready layers, with the hidden parts painted in, plus a layered PSD for Unity 2D
  Animation, Spine or Godot. Tested on four-legged animals; two-legged and winged animals are in scope but
  untested; humans, props, scenes and other art styles are out. The agent decides the layers itself (which
  parts, how many, in what order) from the image; it then peels parts off front to back, cuts from
  flat-colour part maps, and measures every step.
- **[frame-edit-loop](./skills/frame-edit-loop/SKILL.md)**: turn one character illustration into a short
  frame-by-frame loop in the same pose, plus a preview GIF at about 16 fps. Keyframes and in-betweens are
  image edits of the illustration, one change at a time, redrawn until no locked part has moved; small
  motion is a smooth warp, effects are overlays, and every frame is stabilised so nothing shimmers. The GIF
  uses one palette per animation, ordered dithering and exact frame timing. Tested on one chibi character in
  clothes holding a book, in three loops; walk cycles, turns and other big pose changes are out.

Planned, for the same art direction and cast:

- **2d-rig-preview**: preview a layered rig moving before it reaches the engine (hierarchy, bending joints,
  breathing rhythm) to catch seams and hinges early.
- **animation-principles**: the vocabulary and rules for idle loops and small character motion, so agents
  ask for the right thing.

## Testing

Each skill is tested against characters drawn by code, so that their true layers (hidden areas included)
are known, plus recorded runs replayed offline after every script change and an agent eval on characters
the skill never mentions. The test suite is maintained privately and is not part of this repository. The
results are in each skill: its "Tested on" table, and the measured values behind every limit in
`references/checks.md`.

## License

[MIT](./LICENSE)
