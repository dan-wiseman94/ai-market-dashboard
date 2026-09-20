# Project Claude Code config

Committed, team-shared Claude Code setup for this repo. Personal, machine-local overrides go in
`.claude/settings.local.json` (gitignored).

## settings.json
- **permissions.deny** — blocks Read/Edit (and recognized file commands) from touching local
  secrets: env files, `*.key`, `*.pem`, repo-root `data/`, `secret.salt`. The example env file
  stays readable.
- **permissions.allow** — pre-approves the safe daily commands (make targets, read-only
  `docker compose`, in-container pytest/pnpm) to cut permission prompts.
- **hooks**
  - `PreToolUse(Bash)` → `hooks/guard-secrets.sh`: blocks shell commands that read secret files
    (the deny rules don't cover e.g. `python -c "open(...)"`).
  - `PostToolUse(Edit|Write|MultiEdit)` → `hooks/ruff-format-edited.sh`: formats the edited `.py`
    file inside the `web` container (the host has no deps). No-op if the stack is down.

## agents/  (auto-dispatched subagents)
- `conventions-reviewer` — reviews a diff against this repo's silent-failure landmines.
- `migration-reviewer` — reviews Django migrations for reversibility / data safety.

## skills/  (invoke with `/<name>`, or let Claude pick)
- `new-django-app` — scaffolds + wires a new `backend/apps/<name>/` the project's way.
- `conventions-check` — inline conventions pass (lighter than the subagent).

## ../.mcp.json (repo root)
- `postgres` — read-only (restricted) Postgres MCP against the dev DB; credentials via env refs,
  never hardcoded.
