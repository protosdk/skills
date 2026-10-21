"""Write the codex prompts for every peel step and part map from rig.json and the fixed templates.

Usage: python3 -I prompts.py <workdir> <rig.json>

Writes <workdir>/prompts/peel-step1..N.txt and partmap-step0..N-1.txt. Only the character-specific words
(subject, style, part descriptions, what each removal reveals, colours) come from rig.json; the rest of the
wording is fixed in templates/, because each sentence there fixes a failure seen in practice
(see references/failure-modes.md). Edit the templates only with a before/after measurement.
"""
import os
import sys

sys.dont_write_bytecode = True  # no __pycache__ in the skill's folder
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import PALETTE, check_palette, load_rig  # noqa: E402

TEMPLATES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")


def join(items):
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def fill(name, **kw):
    with open(os.path.join(TEMPLATES, name)) as f:
        return f.read().format(**kw)


def main(work, rig_path):
    rig = load_rig(rig_path)
    problems = check_palette(rig)
    if problems:
        raise SystemExit("rig.json colours:\n  " + "\n  ".join(problems))
    parts = rig["parts"]
    common = {"subject": rig["subject"], "style": rig.get("style", "outlines, colors and shading")}
    out_dir = os.path.join(work, "prompts")
    os.makedirs(out_dir, exist_ok=True)
    written = []
    for k, step in enumerate(rig["peel"], start=1):
        remove = step.get("remove_text") or join([parts[p]["describe"] for p in step["remove"]])
        where = "it was" if len(step["remove"]) == 1 else "they were"
        # Late steps show little of the character; told only the full subject, the model drew removed parts back
        # (a whole head and paws on a headless body, 2 of 3 tries). So name what is gone and must stay gone.
        before = [p.replace("_", " ") for s in rig["peel"][:k - 1] for p in s["remove"]]
        gone = (f" (earlier steps already removed its {join(before)}; they stay removed, so do not draw them back)"
                if before else "")
        text = fill("peel.txt", input=f"in/step{k - 1}.png", output=f"raw/step{k}.png", remove=remove, where=where, gone=gone,
                    reveal=step["reveal"].rstrip(".") + ".", **common)
        written.append((f"peel-step{k}.txt", text))
    for k, present in rig["step_parts"].items():
        assignments = "; ".join(f"{parts[p]['describe']} = solid {PALETTE[parts[p]['color'].upper()]} {parts[p]['color'].upper()}"
                                for p in present)
        text = fill("partmap.txt", input=f"in/step{k}.png", output=f"seg-raw/step{k}.png", assignments=assignments, **common)
        written.append((f"partmap-step{k}.txt", text))
    for name, text in written:
        with open(os.path.join(out_dir, name), "w") as f:
            f.write(text)
    print(f"wrote {len(written)} prompts to {out_dir}")


if __name__ == "__main__":
    main(*sys.argv[1:])
