# Consumer CI — healing propose on failure

Minimal GitHub Actions pattern for a POM repo that installs healing from git.

## Secrets / vars

| Name | Type | Purpose |
|------|------|---------|
| `HEALING_LLM_PROVIDER` | Repository **variable** (optional) | `cursor` (default), `openai`, or `anthropic` |
| `HEALING_LLM_MODEL` | Variable (optional) | Override default model |
| `CURSOR_API_KEY` | Secret | When provider=`cursor` |
| `OPENAI_API_KEY` | Secret | When provider=`openai` |
| `ANTHROPIC_API_KEY` | Secret | When provider=`anthropic` |

## Workflow sketch

```yaml
name: Tests + healing propose

on:
  push:
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: |
          pip install "healing[propose] @ git+https://github.com/arunambadikv/self-healing-framework.git"
          playwright install chromium
          # optional in-job auto chain (needs matching secret):
          # echo "HEALING_MCP_AUTO=1" >> "$GITHUB_ENV"
      - run: pytest tests/ -q
        id: pytest
        continue-on-error: true
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: healing-artifacts
          path: |
            healer-artifacts/failures/
            healer-artifacts/healing-queue/
            healer-artifacts/architecture/
          if-no-files-found: ignore
      - if: steps.pytest.outcome == 'failure'
        run: exit 1

  propose-on-failure:
    needs: test
    if: failure()
    runs-on: ubuntu-latest
    env:
      HEALING_LLM_PROVIDER: ${{ vars.HEALING_LLM_PROVIDER || 'cursor' }}
      CURSOR_API_KEY: ${{ secrets.CURSOR_API_KEY }}
      OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
      ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - uses: actions/download-artifact@v4
        with:
          name: healing-artifacts
          path: .
      - run: |
          pip install "healing[propose] @ git+https://github.com/arunambadikv/self-healing-framework.git"
          playwright install chromium
      - run: python -m healing.pom_propose --process-all
      - run: python -m healing.mcp_propose_runner --process-all
      - run: |
          python -m healing.healing_review --promote-all || true
          python -m healing.healing_review --list --json
        if: always()
```

Human review/apply stays local:

```bash
gh run download
healing-review --interactive    # auto-merges into healer-artifacts/
# or: healing-import && healing-review --list
```

See also [CONSUMER_SETUP.md](CONSUMER_SETUP.md).
