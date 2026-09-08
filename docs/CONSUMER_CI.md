# Consumer CI — pomhealer propose on failure

Minimal GitHub Actions pattern for a POM repo that installs pomhealer from git.

## Secrets / vars

| Name | Type | Purpose |
|------|------|---------|
| `POMHEALER_LLM_PROVIDER` | Repository **variable** (optional) | `cursor` (default), `openai`, `gemini`, `groq`, or `litellm` |
| `POMHEALER_LLM_MODEL` | Variable (optional) | Override default (`composer-2.5` / `gpt-4.1` / `gemini-3.6-flash` / `openai/gpt-oss-120b` / `gpt-4o-mini`) |
| `CURSOR_API_KEY` | Secret | When provider=`cursor` |
| `OPENAI_API_KEY` | Secret | When provider=`openai` |
| `GEMINI_API_KEY` | Secret | When provider=`gemini` |
| `GROQ_API_KEY` | Secret | When provider=`groq` |
| `LITE_LLM_KEY` | Secret | When provider=`litellm` (Keyvalue Lite LLM) |

## Workflow sketch

```yaml
name: Tests + pomhealer propose

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
          pip install "pomhealer @ git+https://github.com/arunambadikv/self-healing-framework.git"
          playwright install chromium
          # optional in-job auto chain (needs matching secret):
          # echo "POMHEALER_MCP_AUTO=1" >> "$GITHUB_ENV"
      - run: pytest tests/ -q
        id: pytest
        continue-on-error: true
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: pomhealer-artifacts
          path: |
            pomhealer-artifacts/failures/
            pomhealer-artifacts/pomhealer-queue/
            pomhealer-artifacts/architecture/
          if-no-files-found: ignore
      - if: steps.pytest.outcome == 'failure'
        run: exit 1

  propose-on-failure:
    needs: test
    if: failure()
    runs-on: ubuntu-latest
    env:
      POMHEALER_LLM_PROVIDER: ${{ vars.POMHEALER_LLM_PROVIDER || 'cursor' }}
      CURSOR_API_KEY: ${{ secrets.CURSOR_API_KEY }}
      OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
      GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
      GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}
      LITE_LLM_KEY: ${{ secrets.LITE_LLM_KEY }}
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
          name: pomhealer-artifacts
          path: .
      - run: |
          pip install "pomhealer @ git+https://github.com/arunambadikv/self-healing-framework.git"
          playwright install chromium
      - run: python -m pomhealer.pom_propose --process-all
      - run: python -m pomhealer.mcp_propose_runner --process-all
      - run: |
          python -m pomhealer.review --promote-all || true
          python -m pomhealer.review --list --json
        if: always()
```

Human review/apply stays local:

```bash
gh run download
pomhealer-review --interactive    # auto-merges into pomhealer-artifacts/
# or: pomhealer-import && pomhealer-review --list
```

See also [CONSUMER_SETUP.md](CONSUMER_SETUP.md).
