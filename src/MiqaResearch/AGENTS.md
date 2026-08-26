Be extremely concise. Sacrifice grammar for the sake of concision.

You are bound by the Superpowers engineering framework. You have a set of mandatory skills located in the .skills/superpowers/skills/ directory. Before writing or modifying any code, you must search this directory to find the relevant skill for your current phase (e.g., brainstorming, writing-plans, test-driven-development), read its contents, and strictly adhere to its workflow.

## Agent skills

### Issue tracker

GitH Issues via `gh` CLI. PRs are not treated as a triage surface. See `docs/agents/issue-tracker.md`.

### Triage labels

Default canonical labels: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` + `docs/adr/` at repo root. See `docs/agents/domain.md`.