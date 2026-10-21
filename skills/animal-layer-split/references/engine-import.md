# Using the layers in an engine

The split delivers, at the work size and in one shared canvas:

- `layers/<part>.png`: one RGBA image per part, full canvas, already in place. Stacking them back to front
  in `rig.json` order (base first) reproduces the original.
- `rig.psd`: the same layers, bottom to top, named after the parts, each cropped to its content with its
  offset kept. 8-bit RGB, uncompressed, no masks or groups.
- `layers/joint_<part>.png`: where a part meets its parent in the original (white = seam), blended or not. A
  starting point for where bone weights should blend, and for where to put the joint's pivot.
- `layers/<part>_root.png`: for every part in front of its parent, a hidden root (see below). In the PSD it
  sits just behind the parent.
- `motion-board.png`: every jointed part turned -15 and +15 degrees around its pivot, cropped at the joint.
- `prep.json`: crop box and scale from the source image to the work canvas, to map positions back.

None of the engine paths below were run as part of this skill's tests: the PSD was read back by
`write_psd.py --check`, nothing more. Report engine import as untested until someone has done it.

## Unity 2D Animation

Import `rig.psd` with the PSD Importer package (`com.unity.2d.psdimporter`) with its rig option enabled ("Use as
Rig"; older versions say "Character Rig"), then add bones and weights in the Skinning Editor
(`com.unity.2d.animation`). Layer names become sprite names.
Put each pivot at the seam in `joint_<part>.png`; let weights near the seam blend into the parent the way the
joint image fades, so joints bend instead of hinging.

## Spine, DragonBones, Godot

Use the PNGs: each is full-canvas and in place, so importing them at the same origin keeps the layout. In
Godot, one `Sprite2D` per layer under a `Skeleton2D`/`Bone2D` hierarchy that follows `parent` in `rig.json`.

## Before animating

Parts rotate around pivots that the split does not choose. Expect to adjust: a part that moves far from rest
can show hidden pieces the model painted that are never visible at rest. Check the extremes of every motion.

## Joints that turn

A part in front of its parent ends where it was cut. Turned rigidly, one side of its base lifts off the parent
and opens a wedge of background, so it looks detached: an ear flicking off the head. Two fixes, best first:

1. **Skin the base to the parent.** In Unity 2D Animation or Spine meshes, weight the part's vertices near the
   joint to the parent's bone and let the weight move to the part's own bone towards its tip. The base then
   never moves; only the rest of the part turns. `joint_<part>.png` marks the band to weight.
2. **Use the root layer** where the part turns rigidly. Bind `<part>_root` to the part's bone, keep it in its
   place behind the parent. At rest the parent hides it completely; when the part turns, it fills the wedge
   with plain fur. On the test characters it cut the background at the joint by 60-70% at 15 degrees (an
   ear: 93 to 29 px). It is a flat patch of the parent's colour without an outline, so at larger angles a
   small patch can show past the parent's outline: check `motion-board.png`, and set `root` smaller or skin
   the base if it does.

Parts behind their parent (a tail behind the body) need neither: the peel painted their hidden root.
