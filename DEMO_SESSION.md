# Team demo session — Playwright self-healing framework

**Audience:** QA / automation / dev leads  
**Target:** [SeleniumBase demo page](https://seleniumbase.io/demo_page)  
**Repo:** https://github.com/arunambadikv/self-healing-framework (`dev` branch)  
**Runtime:** ~45–60 minutes (slides optional; this doc is the runbook)

Commands below are for the live session — no need to run them now during prep.

---

## 1. Architecture and flow (2–3 min talking points)

### Idea in one sentence

Tests call **semantic keys** (`demo.green_button`); selectors live in **`locator_registry.yaml`**; at runtime the framework tries **preferred → fallback** deterministically, records **primary / healed / failed**, and produces **reviewable** registry fixes — not silent LLM changes mid-test.

### Layered view

```text
┌─────────────────────────────────────────────────────────────┐
│  Tests                                                       │
│  • Smart:  smart.click("demo.green_button")                  │
│  • Raw:    page.get_by_role(...).click()  (unchanged code)   │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  locator_registry.yaml  (intent, action, preferred, fallback)│
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  SmartPage + locator_builder → Playwright                    │
│  (no AI in the hot path)                                     │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Per-test artifacts (under artifacts/, gitignored)           │
│  • healing-reports/*.json                                      │
│  • patch-suggestions/*.md                                      │
│  • mcp-repair-bundles/prompts|resolved|mcp-plans             │
│  • raw-learning/registry-drafts/*.yaml (raw tests only)      │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Human / agent repair lane (after pytest)                    │
│  • apply_suggestion / mcp_apply / agent_apply (reviewed)     │
│  • Playwright MCP in Cursor: live page → resolved JSON       │
│  • Phase C: agent_runner → executor → approval → apply       │
└─────────────────────────────────────────────────────────────┘
```

### Branch policy (one line)

- **`dev`** — day-to-day work and (planned) auto-healing commits.  
- **`main`** — PR + green **Healing Framework CI** only. See [Branch policy](README.md#branch-policy) in README.

### What we deliberately do *not* do

- No LLM calls during `pytest` execution.  
- No weakening assertions to force green.  
- No silent registry edits on **`main`** in CI today.

---

## 2. How a smart test case works

### Example test

`tests/test_demo_buttons_links.py` — uses the `smart` fixture:

```python
def test_buttons_links(page, smart, base_url):
    page.goto(base_url)
    smart.click("demo.green_button")
    smart.expect_visible("demo.green_text")
```

### What happens at runtime

1. **Registry lookup** — `demo.green_button` must exist; `action` must match (`click` vs `expect_visible`).  
2. **Candidate loop** — `preferred` list, then `fallback`; first match wins.  
3. **Status** — first success in `preferred` → `primary`; success only in `fallback` → **`healed`**.  
4. **Teardown** (`conftest.py`) — JSON report + Markdown patch suggestions; if healed/failed, optional MCP bundle under `artifacts/mcp-repair-bundles/`.

### Registry entry (concept)

```yaml
demo.green_button:
  intent: click the green demo button
  action: click
  preferred: [ ... try first ... ]
  fallback:  [ ... try if preferred fails ... ]
```

### Other smart demos (quick tour, no healing drama)

| File | What it shows |
|------|----------------|
| `tests/test_demo_text_inputs.py` | `fill` + `expect_visible` |
| `tests/test_demo_dropdowns.py` | `select_option` |
| `tests/test_demo_iframe.py` | `frame_css` |
| `tests/test_demo_checkboxes_radios.py` | `check` / radio patterns |

**Say:** “The test reads like a scenario; locators are data, not string soup in every line.”

---

## 3. How a pure Playwright test case works

### Example test (team demo file)

`tests/test_demo_raw_playwright.py` — only `page`, **no** `smart`:

```python
def test_raw_green_button_and_text(page, base_url):
    page.goto(base_url)
    page.get_by_role("button", name="Click Me (Green)", exact=True).click()
    expect(page.locator("#pText")).to_be_visible()
```

### What happens

| Phase | Behavior |
|-------|----------|
| **During test** | Normal Playwright — no registry, no healing loop. |
| **Teardown** (`HEALING_RAW_LEARNING=1`, default) | Hooks record each locator action → semantic key `auto.<module>.<action>_<target>`. |
| **Outputs** | `artifacts/raw-learning/reports/*.json`, `registry-drafts/*.yaml` with proposed `auto.*` keys. |
| **MCP** (`HEALING_RAW_MCP=1`, default) | Repair prompts under `artifacts/mcp-repair-bundles/prompts/` for agent inspection. |

**Say:** “Legacy tests keep running as-is; the framework *learns* drafts and invites repair — it does not rewrite the test file automatically in CI.”

### Contrast with “converted” smart test

`tests/test_pure_playwright_example.py` — same flow as smart, but keys like `auto.pure_playwright_example...` came from an earlier raw → MCP → apply path. Use it to show **end state after** migration, not “pure” execution.

### Optional: migrate raw → smart (mention only)

```bash
python -m healing.convert_to_smart --file tests/test_demo_raw_playwright.py --dry-run
# python -m healing.convert_to_smart --file ... --apply   # after registry keys exist
```

---

## 4. MCP and agents — integrated vs planned

### Today (implemented)

| Lane | Role | Trigger | Human step |
|------|------|---------|------------|
| **Playwright MCP (Cursor)** | Live `browser_navigate` + `browser_snapshot`; propose locators from real DOM | `python -m healing.mcp_repair_pipeline` or smart/raw teardown bundles | Agent writes `artifacts/mcp-repair-bundles/resolved/<key>.json` → `python -m healing.mcp_apply --key ... --apply` |
| **Skills** | Repair / registry-update / patching guidance for agents | Referenced in MCP prompts & `AGENTS.md` | — |
| **agent_runner** | Builds prompt + draft proposal JSON from healing reports | `python -m healing.agent_runner --all` | Review only |
| **Phase C executor** | Runs prompts (`internal_stub` or `cursor_sdk` + `CURSOR_API_KEY`) | `python -m healing.agent_executor` | `approval_manifest approve` → `agent_apply --apply` |
| **CI (main/dev PRs)** | pytest + registry lint + ci_gates | GitHub Actions `Healing Framework CI` | No auto-apply on `main` |

**Key message:** MCP/agents sit **beside** the deterministic runtime — they help **author and approve** registry changes, not replace test execution.

### Planned (roadmap for team)

| Phase | On `dev` | On `main` |
|-------|----------|-----------|
| **D — dev auto-healing** | Bot pipeline: pytest → validate proposals → commit registry (`[healing-auto]` guard) | Still PR + human review only |
| **Stronger metrics** | Per-key heal frequency, promotion recommendations | Same gates, stricter promotion |

See `PROJECT_STATUS.md` §5 for phase checklist.

### MCP flow (whiteboard, 30 seconds)

```text
pytest (healed/failed or raw learning)
  → mcp_repair_pipeline / teardown bundles
  → Cursor Agent + Playwright MCP (live page)
  → resolved/<key>.json
  → mcp_apply --apply
  → pytest + ci_gates
```

### Agent Phase C flow (optional deep dive)

```text
agent_runner → agent_executor → approval_manifest → agent_apply --apply
```

Script: `bash scripts/run_agent_phase_c.sh`

---

## 5. Live demo A — Runtime healing

**Goal:** Show test **passes** while telemetry says **`healed`** → drives registry maintenance.

### Prep (5 minutes before session)

In `locator_registry.yaml`, temporarily make the **first** `demo.green_button` preferred candidate wrong (keep fallbacks):

```yaml
demo.green_button:
  preferred:
    - type: role
      role: button
      name: "THIS_NAME_DOES_NOT_EXIST"   # DEMO ONLY
  fallback:
    - type: text
      value: Click Me (Green)
    - type: css
      value: '#myButton'
```

### Run

```bash
source .venv/bin/activate
pytest tests/test_demo_buttons_links.py -v --headed
```

### Show on screen

1. Test **green** in terminal.  
2. `artifacts/healing-reports/test_buttons_links.json` — event `"status": "healed"` for `demo.green_button`.  
3. `artifacts/patch-suggestions/test_buttons_links.md` — `promote_fallback` suggestion.  
4. Optional: `artifacts/mcp-repair-bundles/prompts/` if MCP auto-bundle ran.

**Talking point:** “Healing is a **signal**, not a free pass — CI can warn/fail on high heal ratio (`healing/ci_gates_config.yaml`).”

### Restore after demo

Revert `demo.green_button` preferred to the real role/CSS (or run promote flow in Demo B).

---

## 6. Live demo B — Registry update (two paths)

### Path 1 — CLI from healing report (no MCP)

After Demo A:

```bash
python -m healing.apply_suggestion \
  --report artifacts/healing-reports/test_buttons_links.json \
  --key demo.green_button \
  --change-type promote_fallback \
  --dry-run

python -m healing.apply_suggestion \
  --report artifacts/healing-reports/test_buttons_links.json \
  --key demo.green_button \
  --change-type promote_fallback \
  --apply
```

Re-run:

```bash
pytest tests/test_demo_buttons_links.py -q
```

Show report now **`primary`** (or fix preferred manually and drop the bogus first candidate).

### Path 2 — MCP + agent (Cursor)

```bash
pytest tests/test_demo_buttons_links.py -q
python -m healing.mcp_repair_pipeline
```

In **Cursor Agent** (Playwright MCP connected per `AGENTS.md`):

```text
Repair demo.green_button using Playwright MCP per
artifacts/mcp-repair-bundles/prompts/demo_green_button__promote_fallback.md
(navigate to demo page, snapshot, propose locators from live DOM, write
artifacts/mcp-repair-bundles/resolved/demo_green_button.json)
```

Apply:

```bash
python -m healing.mcp_apply --key demo.green_button --apply
pytest tests/test_demo_buttons_links.py -q
python -m healing.ci_gates
```

**Talking point:** “Same outcome, two speeds — quick promote from report vs MCP when the UI changed and you need eyes on the page.”

---

## 7. Live demo C — Pure Playwright + raw learning (optional, ~10 min)

```bash
pytest tests/test_demo_raw_playwright.py -v
```

Show:

- `artifacts/raw-learning/reports/test_raw_green_button_and_text.json`  
- `artifacts/raw-learning/registry-drafts/` — draft `auto.test_demo_raw_playwright...` keys  
- `artifacts/mcp-repair-bundles/prompts/` — agent task for adding/refining keys  

**Talking point:** “Onboarding path for hundreds of legacy tests without a big-bang rewrite.”

---

## 8. Live demo D — Total failure → MCP + Cursor fixes registry

**Goal:** Show what happens when **preferred and fallback both fail**, the test **fails**, and **MCP + Cursor Agent** discovers the real locator and updates the registry (no `promote_fallback` shortcut).

### Dedicated demo key and test

| Item | Location |
|------|----------|
| Registry key (intentionally broken) | `demo.session_github_link` in `locator_registry.yaml` |
| Smart test | `tests/test_demo_total_failure.py` |
| Example agent output | `demo-assets/mcp-resolved-demo_session_github_link.json.example` |

The registry entry uses a bogus role name and a non-existent CSS id so **every candidate fails** and `SmartPage` raises `AllLocatorCandidatesFailedError`.

**CI note:** The test is marked `demo_session` and **skipped by default** so normal `pytest` / GitHub Actions stay green. Run it only with `--run-demo-session`.

### Step 1 — Run failing test (expect red)

```bash
source .venv/bin/activate
rm -rf artifacts/   # optional: clean reports
pytest tests/test_demo_total_failure.py --run-demo-session -v
```

### Show on screen

1. Test **fails** with `AllLocatorCandidatesFailedError` and per-candidate errors in the traceback.  
2. Despite failure, teardown still wrote:  
   - `artifacts/healing-reports/test_demo_total_failure.json` — `"status": "failed"` for `demo.session_github_link`  
   - `artifacts/mcp-repair-bundles/prompts/demo_session_github_link__failed.md`  
   - `artifacts/mcp-repair-bundles/mcp-plans/demo_session_github_link__failed.json`  
3. `artifacts/patch-suggestions/test_demo_total_failure.md` — likely “no healed suggestions” (nothing to promote).

**Talking point:** “Runtime healing cannot help here — we need **authoring**, not reordering. That’s where MCP + agent inspection fits.”

### Step 2 — Cursor Agent + Playwright MCP

Prerequisites: Playwright MCP connected in Cursor (see `AGENTS.md` / `.cursor/mcp.json`).

Paste into **Cursor Agent**:

```text
Repair demo.session_github_link using Playwright MCP.

1. Read artifacts/mcp-repair-bundles/prompts/demo_session_github_link__failed.md
2. CallMcpTool: browser_navigate to https://seleniumbase.io/demo_page
3. CallMcpTool: browser_snapshot — find the SeleniumBase GitHub link from the live page (not guesses)
4. Write artifacts/mcp-repair-bundles/resolved/demo_session_github_link.json
   with LocatorPatchResult: patch_type registry_only, YAML patch replacing preferred/fallback
   (mirror demo.github_link: role "SeleniumBase on GitHub" and/or css #myLink2)
5. Do not change the test file or weaken assertions.

Reference shape: demo-assets/mcp-resolved-demo_session_github_link.json.example
```

**Show:** accessibility snapshot in MCP, agent reasoning, resolved JSON with real locators.

### Step 3 — Apply and verify green

```bash
python -m healing.mcp_apply --key demo.session_github_link --apply
pytest tests/test_demo_total_failure.py --run-demo-session -q
```

Optional gates (ignore demo report via config if you ran other demos):

```bash
python -m healing.registry_lint
python -m healing.ci_gates
```

### Narrative arc (30–45 seconds)

```text
broken registry → test fails → failed event in report → MCP bundle
→ agent inspects live UI → resolved JSON → mcp_apply → test passes on primary
```

### Contrast with Demo A

| | Demo A (healing) | Demo D (total failure) |
|--|------------------|-------------------------|
| Preferred | Broken | Broken |
| Fallback | **Works** | **Broken** |
| Test result | Pass (`healed`) | **Fail** |
| Fix path | `promote_fallback` / quick MCP | **Full MCP discovery** — new preferred from DOM |

### After session (optional cleanup)

Leave `demo.session_github_link` repaired in registry, or restore the broken preferred/fallback block if you want to re-run Demo D next time.

---

## 9. Suggested session agenda

| Time | Topic | Artifact / command |
|------|--------|-------------------|
| 5 min | Problem: selector drift, duplicated selectors | — |
| 5 min | Architecture diagram (§1) | This doc |
| 10 min | Smart tests + registry | `test_demo_text_inputs.py`, `locator_registry.yaml` |
| 5 min | Raw vs smart | `test_demo_raw_playwright.py` vs `test_demo_buttons_links.py` |
| 12 min | **Demo A + B** healing → registry | §5–§6 |
| 12 min | **Demo D** total failure → MCP repair | §8 |
| 8 min | MCP + agents positioning | §4, `AGENTS.md` |
| 5 min | CI + branch policy + Q&A | README Branch policy, `.github/workflows/healing-ci.yml` |

---

## 10. Pre-session checklist

- [ ] `python -m venv .venv && pip install -r requirements.txt && playwright install chromium`  
- [ ] Break `demo.green_button` first preferred for healing demo (§5) — skip if `demo.session_github_link` already broken for Demo D  
- [ ] Confirm `demo.session_github_link` has bogus preferred + fallback (§8; committed in repo)  
- [ ] Cursor: Playwright MCP connected (`.cursor/mcp.json`) — **required** for Demo D  
- [ ] `rm -rf artifacts/` for clean reports (optional)  
- [ ] Terminal font size / `--headed` for visibility  
- [ ] Git branch: `dev` (not promoting to `main` during demo)

---

## 11. FAQ snippets

**Q: Does AI fix tests during the run?**  
A: No. Runtime is deterministic YAML + Playwright. AI/MCP runs after, with human or approval gates.

**Q: Can healing hide broken tests?**  
A: Tests can pass on fallback while reports show `healed`. CI gates and review are the guardrails.

**Q: Do we have to convert all tests at once?**  
A: No. Raw path learns drafts; converter and MCP can migrate incrementally.

**Q: What’s on `main` vs `dev`?**  
A: `main` = PR + CI; `dev` = integration and future auto-heal bot (Phase D).

**Q: What if every locator fails?**  
A: Test fails; report status `failed`; MCP bundle type `failed` drives Cursor to inspect the page and rewrite registry entries (Demo D).

---

## 12. Quick reference commands

```bash
# Smart suite
pytest tests/test_demo_buttons_links.py -v --headed

# Raw learning demo
pytest tests/test_demo_raw_playwright.py -v

# Total failure → MCP repair demo
pytest tests/test_demo_total_failure.py --run-demo-session -v
python -m healing.mcp_apply --key demo.session_github_link --apply

# Gates (same as CI job)
pytest tests/ -q && python -m healing.registry_lint && python -m healing.ci_gates

# MCP bundles
python -m healing.mcp_repair_pipeline

# Apply reviewed change
python -m healing.apply_suggestion --report artifacts/healing-reports/<test>.json \
  --key demo.green_button --change-type promote_fallback --apply
```

**Further reading:** `README.md`, `AGENTS.md`, `PROJECT_STATUS.md`
