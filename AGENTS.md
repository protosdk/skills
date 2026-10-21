# Contributing a skill

This file is for people and agents adding or changing skills in this repository.

## Layout

```
skills/<name>/
  SKILL.md         what the agent reads: frontmatter, when to use, steps, checks, rules
  scripts/         deterministic tools the steps call; prompt templates in scripts/templates/
  references/      detail loaded on demand: config format, checks, failure modes
```

`npx skills add` installs only `skills/<name>/`. Keep it light: no images or test fixtures in the skill
folder. Tests and their fixtures live in a privately maintained test suite, not in this repository (a local
`evals/` folder is ignored by git).

## What makes a skill here

A skill earns its place by making an agent's result measurably better or more reliable than the agent
alone. The pattern every skill follows:

1. **The model does only what needs a model.** Painting, redrawing, judging taste. Anything that has to be
   exact (alignment, colour, cutting, file formats, timing) is a script.
2. **Every step is measured.** A script prints numbers and compares them with limits; the agent reports the
   numbers. A limit comes from a real accepted result, plus a deliberately broken input that it catches.
3. **Prompts are templates.** Fixed wording lives in `scripts/templates/`; only the subject-specific words
   come from config. Each sentence in a template exists because leaving it out failed.
4. **Failure modes are written down** as symptom, cause, fix, including approaches that were tried and did
   not work, so the next agent does not try them again.

## Writing SKILL.md

- Frontmatter: `name` (lowercase, hyphens, same as the folder) and `description` (what it does and when to
  use it, under 1024 characters; this is what decides whether an agent picks the skill, so name the tasks
  and the words people use for them).
- Keep the main file to what an agent needs on every run: when to use it and when not, the steps, the
  checks table, the rules. Move formats, long tables and background into `references/` and link them.
- Write instructions, not essays. Say what to do and why in one clause; give numbers, file names and
  commands.
- Say what the skill cannot check, and tell the agent to look at those things and to report what it did
  not test.
- English. Add Traditional Chinese only where the owner asks for it.

## Scripts

- Python 3 with Pillow and numpy only, unless a dependency is unavoidable. Run with `python3 -I` (isolated:
  no imports from the current folder). Scripts import their siblings by path.
- Set `sys.dont_write_bytecode = True` before importing siblings, so a run never leaves `__pycache__` in the
  installed skill's folder (`-I` does not stop it).
- Deterministic: the same inputs give byte-identical outputs. No randomness, no timestamps in outputs.
- One job per script, a usage line in the docstring, and readable output: one line per step, with numbers.
- External tools (codex, ffmpeg) are called from one wrapper per tool that checks what came back.
- Image model calls run one at a time. Never parallelise them.

## Testing a change

The tests are maintained privately, outside this repository. They have three levels, and a change needs
the one it touches:

- **Offline replay** (any script change). The whole pipeline runs on recorded model outputs, with no model
  calls, and must reproduce the recorded result exactly, unless the change is meant to alter results; then
  the commit says what changed and why, and the recorded result is updated. Compare on the same Pillow and
  numpy versions: others can change the last digits.
- **Live run** (prompt, template or model changes). The skill runs end to end with real image edits, one at
  a time, on characters drawn by code whose true layers are known, and is scored against them. A recorded
  run is replaced only by one that is at least as good on every check.
- **Agent eval** (changes to SKILL.md, the references or anything an agent reads to plan). An agent gets only
  an image the skill has never seen and the skill itself, decides and plans on its own, and is scored
  against the true layers; one held-out image is out of scope and must be refused.

Held-out characters must never be described anywhere in `skills/`: not their name, not their plan, not their
part count. Otherwise the agent eval measures copying.

Without access to the test suite, say which levels you could not run. Report what you ran and what you did
not: a run that was skipped is "not run", not "passed".

## Content rules

- Test characters are original and drawn for the test suite, for example by code, with every part drawn
  whole on its own layer first so that the truth includes the hidden areas. No characters, art or text from
  other works, games or companies, and nothing from private projects in this repository.
- No credentials, tokens, account details or internal information in files, logs or commits. Codex logs
  are not committed.
- MIT licensed: only add what you have the right to publish under it.
