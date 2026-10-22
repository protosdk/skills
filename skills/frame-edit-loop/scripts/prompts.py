"""Write the image-edit prompt for every frame in loop.json from the fixed template.

Usage: python3 -I prompts.py <workdir>

Writes <workdir>/prompts/<frame>.txt. Only the character-specific words (subject, style, the parts to keep,
the change, the smeared part) come from loop.json; the rest is fixed in templates/edit.txt, because each
sentence there fixes a failure seen in practice (see references/failure-modes.md). Edit the template only
with a before/after measurement.
"""
import os
import sys

sys.dont_write_bytecode = True  # no __pycache__ in the skill's folder
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ART, load_config  # noqa: E402

TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "edit.txt")
SLOW = "The motion is slow, so this is a clean, sharp drawing: no afterimages, no ghost copies, no motion blur, no speed lines."
FAST = "No afterimages, no ghost copies, no motion blur, no speed lines."
# The first fast loop asked for an echo outline around the head and body as well; the head barely moved,
# so the echo matched no motion and blinked on every other frame. Smears go on the fast part only.
SMEAR = ("This is a fast motion: draw a motion smear on {part} only, two faint, semi-transparent, paler copies of it "
         "along the path it just moved, each paler than the last. No afterimage outline around the head or the body, "
         "no speed lines.")


def join(items):
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def prompt(cfg, name):
    fr = cfg["frames"][name]
    fps = f"{1000 / cfg.get('ms', 60):.0f}"
    pace = cfg.get("pace", "calm" if cfg.get("motion", "slow") == "slow" else "fast")
    loop = f"a {pace} looping 2D game animation played at about {fps} frames per second"
    if fr["from"] == ART:
        role = f"this is the first keyframe of {loop}. Later frames will be edited from this one, so keep the character locked 100%."
    else:
        kind = "an in-between frame" if fr.get("kind") == "inbetween" else "a keyframe"
        role = (f"keep the character locked 100%: this is {kind} of {loop}, and it will be played right next to the uploaded "
                "image, so anything that moves by even one pixel will visibly jitter.")
    moving = set(fr.get("moves", []))
    locked = [p["describe"] for p in cfg["parts"] if p["name"] not in moving] + fr.get("keep_also", [])
    if not locked:
        raise SystemExit(f"{name}: every part moves, nothing is locked; this method needs most of the drawing to stay put")
    if cfg.get("motion", "slow") == "slow":
        motion = SLOW
    else:
        motion = SMEAR.format(part=fr["smear"]) if fr.get("smear") else FAST
    ref = fr.get("reference")
    ref_note = ref_role = ""
    if ref:
        ref_name = os.path.basename(ref["image"])
        ref_note = f". The second attached image, {ref_name}, is {ref['use']} only: do not edit it and do not copy it into the result"
        ref_role = f" and {ref_name} as {ref['use']}"
    with open(TEMPLATE) as f:
        return f.read().format(
            input=f"in/{fr['from']}.png", output=f"raw/{name}.png", subject=cfg["subject"], role=role,
            locked=join(locked), style=cfg.get("style", "outlines, line thickness, colors and cel shading"),
            change=fr["change"].strip(), motion=motion, ref_note=ref_note, ref_role=ref_role)


def main(work):
    cfg = load_config(work)
    os.makedirs(os.path.join(work, "prompts"), exist_ok=True)
    for name in cfg["frames"]:
        with open(os.path.join(work, "prompts", f"{name}.txt"), "w") as f:
            f.write(prompt(cfg, name))
    print(f"wrote {len(cfg['frames'])} prompts to {os.path.join(work, 'prompts')}")


if __name__ == "__main__":
    main(*sys.argv[1:])
