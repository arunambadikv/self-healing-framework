---
name: healing-review
description: Human-in-the-loop review of healing-queue patches (patch_ready). Interactive terminal menu or agent-guided heal/skip/defer with review cards. Use when the user runs /healing-review.
disable-model-invocation: true
---

# Healing Review (Human in the Loop)

## Objective

Review each `patch_ready` entry with full context; apply or skip; produce session summary.

Use **`/playwright-locator-repair`** during propose/MCP; this skill is for **human approval and safe apply**.

Human-in-the-loop is **only at the decision**. After the user picks Heal / Skip / Defer once, **execute immediately** via CLI with `--yes` — do not ask whether to run bash, do not ask for a second confirmation.

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
   - If the card (or failure JSON) lists a **Screenshot** path, **Read** that PNG so the image appears in chat before asking.
   - Present failure context, screenshot, before → after, risk, and `validation_command` in plain language.
   - Use **AskQuestion** (or equivalent) with options:
     - **Heal** — apply patch now
     - **Skip** — reject (include a short reason in the same choice when possible)
     - **Defer** — mark deferred (status → `deferred`; re-queue later with `--promote` or list via `--list-deferred`)
     - **Show failure report** — read `healer-artifacts/failures/F-*.md` (+ screenshot) and re-ask
     - **Dry run** — preview only, then re-ask
4. **Immediately** execute the user's choice (no “should I run this?”):

### Heal (after user chose Heal)

```bash
python -m healing.healing_review --patch P-<id> --decision heal --yes
```

`--yes` confirms high-risk patches when the user already approved in chat. Runs validation, updates `pages/*.py` via `healing.pom_apply`, moves patch to `applied/`. Report success/failure; then continue to the next patch.

Prefer the CLI over hand-editing so only `architecture_updates[].file` under `pages/` are touched.

### Skip (after user chose Skip)

```bash
python -m healing.healing_review --patch P-<id> --decision skip --reason "suspected app regression" --yes
```

If the user did not give a reason, ask once for a short reason, then run skip. Writes `healer-artifacts/healing-queue/skipped/P-<id>-rca.md`.

### Defer (after user chose Defer)

```bash
python -m healing.healing_review --patch P-<id> --decision defer --yes
```

Sets queue status to `deferred` (no longer `patch_ready`).

### Dry run

```bash
python -m healing.healing_review --patch P-<id> --decision heal --dry-run
```

Then re-present AskQuestion for the same patch.

5. When no `patch_ready` remains:

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
- Always surface the failure **screenshot** (Read the PNG) when the path exists.
- Never heal without an explicit user decision for that patch; once decided, run CLI with `--yes` without further prompts.
- One patch at a time — wait for user decision before moving to the next.
