---
name: healing-review
description: Human-in-the-loop review of healing-queue patches (patch_ready). Interactive terminal menu or agent-guided heal/skip/defer with review cards. Use when the user runs /healing-review.
disable-model-invocation: true
---

# Healing Review (Human in the Loop)

## Objective

Review each `patch_ready` entry with full context; apply or skip; produce session summary.

Use **`/playwright-locator-repair`** during propose/MCP; this skill is for **human approval and safe apply**.

## Steps

### Terminal (recommended)

```bash
python -m healing.healing_review --interactive
# or simply (TTY default):
python -m healing.healing_review
```

Guided menu per patch: **Heal** | **Skip** | **Defer** | **Show failure** | **Dry run** | **Quit**

List patches first (table view):

```bash
python -m healing.healing_review --list
```

### Cursor chat (agent)

1. Run `python -m healing.healing_review --promote-all` if any patches may still be `awaiting_agent`.
2. Run `python -m healing.healing_review --list` (read-only table of `patch_ready` patches).
3. For **each** pending patch:
   - Run `python -m healing.healing_review --show P-<id>` for the review card.
   - Present failure context, before → after, risk, and `validation_command` in plain language.
   - Use **AskQuestion** (or equivalent) with options:
     - **Heal** — apply patch
     - **Skip** — reject (ask for reason if not obvious)
     - **Defer** — leave for later
     - **Show failure report** — read `artifacts/failures/F-*.md` and continue
     - **Dry run** — `python -m healing.healing_review --patch P-<id> --decision heal --dry-run`
3. Execute the user's choice via CLI (never auto-heal without confirmation).

### Heal

```bash
python -m healing.healing_review --patch P-<id> --decision heal
```

Runs validation, updates `pages/*.py` via `healing.pom_apply`, moves patch to `applied/`.

Prefer the CLI over hand-editing so only `architecture_updates[].file` under `pages/` are touched.

### Skip

```bash
python -m healing.healing_review --patch P-<id> --decision skip --reason "suspected app regression"
```

Writes `artifacts/healing-queue/skipped/P-<id>-rca.md` with bug/RCA hints.

Interactive mode offers common skip reasons; custom text is also supported.

### Defer

```bash
python -m healing.healing_review --patch P-<id> --decision defer
```

Or choose **Defer** in interactive mode — skips for now; patch stays `patch_ready`.

4. When no `patch_ready` remains:

```bash
python -m healing.healing_review --summary
```

(Interactive mode writes summary automatically when all patches are processed.)

## Patch safety (apply time)

**Allowed**

- Replace stale locator expression in a `@property` on `pages/*.py`
- Fix wrong `get_by_role` / `get_by_*` name from MCP-verified snapshot
- Add a new page method only if the test flow requires it (rare; call out in review)

**Not allowed**

- Remove or weaken assertions
- Skip tests to make CI green
- Add arbitrary sleeps
- Patch `tests/*.py` to inline selectors instead of page methods
- Edit files outside `pages/` (except with explicit user approval)
- Apply patches that still contain `TODO` placeholders in `after`

**After heal, verify**

1. `validation_command` from the patch passes
2. Locator is not overly broad (e.g. bare `button` without name)
3. No unrelated diff in the PR

## Presentation rules

- Use plain language; include test name, page class, method, and locator id.
- Always show `validation_command` before heal.
- Never auto-heal **high** risk without explicit user confirmation in chat (interactive mode requires typing `yes`).
- One patch at a time — wait for user decision before moving to the next.
