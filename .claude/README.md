# Project Claude Code config

Committed, team-shared Claude Code setup for this repo. Personal, machine-local overrides go in
`.claude/settings.local.json` (gitignored).

## settings.json
- **permissions.deny** — blocks Claude's Read/Edit tools (and recognized file commands) from
  touching local secrets: `.env`, `.env.local`, `*.key`, `*.pem`, repo-root `data/`, `secret.salt`.
  `.env.example` stays readable.
- **permissions.allow** — pre-approves the safe daily commands (make targets, read-only
  `docker compose`, in-container pytest/pnpm) so there are fewer permission prompts.
- **hooks**
  - `PreToolUse(Bash)` → `hooks/guard-secrets.sh`: blocks shell commands that read secret files
    (defense-in-depth beyond the deny rules, which don't cover e.g. `python -c "open('.env')"`).
  - `PostToolUse(Edit|Write|MultiEdit)` → `hooks/ruff-format-edited.sh`: formats the edited `.py`
    file inside the `web` container (the host has no deps — see CLAUDE.md). No-op if the stack
    is down.

## agents/  (auto-dispatched subagents)
- `conventions-reviewer` — reviews a diff against this repo's documented silent-failure landmines
  (Celery registration, section `done` vs `ready`, URL ordering, direct provider instantiation, …).
- `migration-reviewer` — reviews Django migrations for reversibility / data safety.

## skills/  (invoke with `/<name>`, or let Claude pick)
- `new-django-app` — scaffolds + wires a new `backend/apps/<name>/` the project's way.
- `conventions-check` — inline conventions pass (lighter than the subagent).

## ../.mcp.json (repo root)
- `postgres` — read-only (restricted) Postgres MCP against the dev DB; credentials via env refs,
  never hardcoded.
