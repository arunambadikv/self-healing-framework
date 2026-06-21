---
name: push-to-dev
description: Stage, commit, and push current work to the dev branch. Use when the user runs /push-to-dev or asks to push changes to dev.
disable-model-invocation: true
---

# Push to Dev

When invoked, push immediately — do not ask for a commit message.

## Steps

1. `git status`, `git diff`, and recent `git log` — draft a concise commit message from the changes.
2. Ensure on `dev` (checkout if needed).
3. Stage relevant changes; exclude secrets (`.env`, credentials).
4. Commit with the drafted message.
5. Push: `git push origin dev` (no force push).

## Rules

- Target branch: `dev` only — never push to `main`.
- Do not amend or force-push unless the user explicitly asks.
- If there is nothing to commit, push existing commits only.
