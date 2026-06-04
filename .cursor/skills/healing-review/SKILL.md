---
name: healing-review
description: Human-in-the-loop review of healing-queue patches (patch_ready). Show failure context and proposed locator changes; apply via pom_apply or skip with RCA. Use when the user runs /healing-review.
disable-model-invocation: true
---

# Healing Review (Human in the Loop)

## Objective

Review each `patch_ready` entry with full context; apply or skip; produce session summary.

Use **`/playwright-locator-repair`** during propose/MCP; this skill is for **human approval and safe apply**.

## Steps

1. Run: `python -m healing.healing_review --list`
2. For each pending patch, present to the user:
   - Failure narrative (`artifacts/failures/F-*.md`)
   - Steps taken, URL, error
   - **Proposed change**: file, symbol, before → after, risk_level
3. Ask: **Heal** | **Skip** | **Defer**

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

### Defer

Leave status `patch_ready` for a later session.

4. When no `patch_ready` remains:

```bash
python -m healing.healing_review --summary
```

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
- Never auto-heal **high** risk without explicit user confirmation in chat.
