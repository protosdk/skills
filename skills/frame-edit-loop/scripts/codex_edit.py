"""Run one image edit through `codex exec` and make sure the saved file is really this run's output.

Usage: python3 -I codex_edit.py <workdir> <prompt.txt> <input image> <output image> [model] [--ref <reference image>]

Paths are relative to <workdir>. --ref attaches a second image that the prompt names as a reference only
(a perspective or prop reference); the edit is still made on the input image.
The model (default $CODEX_MODEL, else gpt-6-luna) only drives the tool
call; the picture is drawn by codex's built-in image tool either way, so a fast model is fine.

Guards, each against a failure seen in practice:
- One edit at a time per machine (a lock file). Parallel runs race: codex copies "the newest image" and two
  steps end up saving the same picture.
- The saved file must be byte-identical to an image in this run's own ~/.codex/generated_images/<session>/.
  If codex forgot to copy it and the session made exactly one image, that one is copied.
- The output must not already exist (move rejected attempts aside; keep them as evidence) and must be square.
- The work folder gets an AGENTS.md (templates/codex-agents.md) telling codex to pass the attached image to
  the image tool as the edit reference. Once codex skipped it and drew a new character from the prompt text
  alone (shifted 6 px, 29% of it outside the old silhouette); the checks catch that afterwards, this prevents it.
Writes logs/codex-<name>-<attempt>.log, logs/last-message-<name>-<attempt>.txt and logs/<name>-<attempt>.json.
Exit codes: 0 saved and verified, 1 the edit came back unusable (worth a retry), 2 codex did not start (fix setup).
"""
import fcntl
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

from PIL import Image

DEFAULT_MODEL = "gpt-6-luna"
TIMEOUT = 20 * 60


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def ensure_agents_md(work):
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "codex-agents.md")) as f:
        text = f.read()
    path = os.path.join(work, "AGENTS.md")
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write(text)
    elif text not in open(path).read():
        print(f"note: {path} exists and lacks the edit-reference rule from templates/codex-agents.md; add it", flush=True)


def main(work, prompt, src, out, model=None, ref=None):
    model = model or os.environ.get("CODEX_MODEL") or DEFAULT_MODEL
    work = os.path.abspath(work)
    out_path = os.path.join(work, out)
    if os.path.exists(out_path):
        raise SystemExit(f"{out} already exists: move it aside first (rejected attempts are evidence, do not delete them)")
    for needed in [src] + ([ref] if ref else []):
        if not os.path.exists(os.path.join(work, needed)):
            raise SystemExit(f"{needed} not found in {work}")
    name = os.path.splitext(out)[0].replace(os.sep, "-")
    logs = os.path.join(work, "logs")
    os.makedirs(logs, exist_ok=True)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    codex_home = os.environ.get("CODEX_HOME", os.path.expanduser("~/.codex"))
    ensure_agents_md(work)

    lock = open(os.path.join(tempfile.gettempdir(), "codex-image-edit.lock"), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("another image edit is running on this machine; waiting for it (edits must not run in parallel)", flush=True)
        fcntl.flock(lock, fcntl.LOCK_EX)

    tries = len(glob.glob(os.path.join(logs, f"codex-{name}-*.log")))
    name = f"{name}-{tries + 1}"  # one log per attempt: a retry must not overwrite the evidence of the last one
    log_path = os.path.join(logs, f"codex-{name}.log")
    # --skip-git-repo-check: the workdir is usually not a git repo, and codex refuses to start there without it.
    cmd = ["codex", "exec", "--skip-git-repo-check", "-m", model, "-C", work, "-s", "workspace-write", "-i", os.path.join(work, src),
           *([os.path.join(work, ref)] if ref else []),
           "-o", os.path.join(logs, f"last-message-{name}.txt")]
    t0 = time.time()
    with open(os.path.join(work, prompt) if not os.path.isabs(prompt) else prompt) as stdin, open(log_path, "w") as log:
        rc = subprocess.run(cmd, stdin=stdin, stdout=log, stderr=subprocess.STDOUT, timeout=TIMEOUT).returncode
    seconds = round(time.time() - t0)
    with open(log_path, errors="replace") as f:
        log_text = f.read()
    m = re.search(r"session id:\s*([0-9a-f-]+)", log_text)
    session = m.group(1) if m else None
    generated = sorted(glob.glob(os.path.join(codex_home, "generated_images", session, "*.png"))) if session else []

    if not session:
        fcntl.flock(lock, fcntl.LOCK_UN)
        print(f"codex did not start a session (exit {rc}); not a model problem, so no retry. Log: {log_path}", file=sys.stderr)
        sys.exit(2)
    problems = []
    if rc != 0:
        problems.append(f"codex exited with {rc}")
    if not os.path.exists(out_path) and len(generated) == 1:
        shutil.copyfile(generated[0], out_path)
        print(f"codex did not save {out}; copied this session's only image {generated[0]}")
    if not os.path.exists(out_path):
        problems.append(f"{out} was not saved ({len(generated)} images in this session)")
        blocked = re.search(r"safety_violations=\[([^\]]*)\]", log_text)
        if blocked or "moderation_blocked" in log_text:
            problems.append(f"the image model's safety filter blocked the result ({blocked.group(1) if blocked else 'no category'}); "
                            "on an innocent character this is a false positive, see references/failure-modes.md")
    else:
        digest = sha(out_path)
        if generated and digest not in {sha(g) for g in generated}:
            problems.append(f"{out} is not one of this session's generated images (race with another run, or codex post-processed it)")
        if digest == sha(os.path.join(work, src)):
            problems.append(f"{out} is the unedited input")
        w, h = Image.open(out_path).size
        if w != h:
            problems.append(f"{out} is {w}x{h}, not square: the model recomposed the picture, so it will not line up")
    record = {"model": model, "session": session, "seconds": seconds, "prompt": prompt, "input": src, "reference": ref, "output": out,
              "generated": generated, "size": list(Image.open(out_path).size) if os.path.exists(out_path) else None,
              "problems": problems}
    with open(os.path.join(logs, f"{name}.json"), "w") as f:
        json.dump(record, f, indent=2)
        f.write("\n")
    fcntl.flock(lock, fcntl.LOCK_UN)
    if problems:
        raise SystemExit(f"{out}: " + "; ".join(problems) + f" (log: {log_path})")
    print(f"{out}: {record['size'][0]}x{record['size'][1]} in {seconds}s ({model}, session {session})")


if __name__ == "__main__":
    args = sys.argv[1:]
    ref = None
    if "--ref" in args:
        i = args.index("--ref")
        ref = args[i + 1]
        del args[i:i + 2]
    main(*args, ref=ref)
