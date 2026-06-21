---
name: push-to-dev
description: Silently stage, commit, and push to dev in one shot. Use when the user runs /push-to-dev or asks to push changes to dev.
disable-model-invocation: true
---

# Push to Dev

Execute the full push workflow **immediately**. Do not ask questions. Do not show the user a list of git commands to run — **run them yourself** in the background.

## Agent behavior

- **One execution path:** use a single chained shell command (or at most one commit + one push). Never walk the user through step-by-step CLI instructions.
- **Silent prep:** use `git status`, `git diff`, and `git log` only to draft the commit message — do not paste their output unless push fails.
- **User reply:** on success, report only commit hash, branch (`dev`), and remote push result. On failure, report the error and what blocked the push.

## What to run (agent only — do not echo this list to the user)

```bash
# Ensure dev, stage (no secrets), commit if needed, push — one flow:
git checkout dev 2>/dev/null || git checkout -b dev
git add -A
git reset HEAD -- .env .env.* '**/credentials*.json' 2>/dev/null || true
# if nothing staged and nothing to commit, skip commit
git diff --cached --quiet || git commit -m "<drafted message>"
git push origin dev
```

Draft the commit message from the diff (1–2 sentences, repo style). Exclude `.env` and credential files from staging.

## Rules

- Target branch: **`dev` only** — never push to `main`.
- No force push, no amend, unless the user explicitly asked.
- If working tree is clean, push existing commits only.
- Never update git config.
