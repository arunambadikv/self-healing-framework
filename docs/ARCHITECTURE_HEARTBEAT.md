# Architecture discovery heartbeat

Keeps `pomhealer-artifacts/architecture/manifest.json` fresh even when no PR is open.

## GitHub Actions (repo)

Workflow: [`.github/workflows/architecture-heartbeat.yml`](../.github/workflows/architecture-heartbeat.yml)

- Schedule: daily **06:00 UTC**
- Manual: `gh workflow run architecture-heartbeat.yml && gh run watch`

Uploads `architecture-manifest` artifact; does not fail the default CI merge path.

## Cursor Automation (local / cloud agent)

Create a **daily** Cursor Automation with:

| Field | Value |
|-------|--------|
| Name | Architecture discovery heartbeat |
| Trigger | Schedule — once per day |
| Instructions | Run `python -m pomhealer.architecture_scan` from the repo root. Read `pomhealer-artifacts/architecture/manifest.json`. Report whether `content_hash` changed. Do not edit `pages/` or `tests/`. |
| Tools | Shell / terminal only (no Playwright MCP required) |

Finish creation in the Cursor Automations editor (Agents Window → Automations). Prefer linking the automation to this repository’s `dev` or default working branch.

## On-demand

```bash
python -m pomhealer.architecture_scan
# or Cursor: /architecture-discovery
```
