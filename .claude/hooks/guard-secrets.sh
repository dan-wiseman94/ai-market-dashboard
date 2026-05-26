#!/usr/bin/env bash
# PreToolUse(Bash) guard — block shell commands that read/copy local secret files.
#
# Defense-in-depth on top of the Read/Edit deny rules in .claude/settings.json: those
# gate Claude's file tools (and recognized file commands), but NOT arbitrary subprocess
# access like `python -c "open('.env')"`, `xxd`, `base64`, `strings`, etc.
#
# Contract: exit 2 = block (stderr is shown to the model); exit 0 = allow.
# Fails OPEN (exit 0) on internal error so a broken hook never wedges all Bash use.

cmd="$(python3 -c 'import json,sys
try:
    print((json.load(sys.stdin).get("tool_input") or {}).get("command",""))
except Exception:
    pass' 2>/dev/null || true)"

[ -n "$cmd" ] || exit 0

# .env / .env.local  (but allow .env.example / .env.sample / .env.template)
if printf '%s' "$cmd" | grep -Eq '\.env\b' \
   && ! printf '%s' "$cmd" | grep -Eq '\.env\.(example|sample|template)\b'; then
  echo "BLOCKED by .claude/hooks/guard-secrets.sh: command references .env (local secrets — DJANGO_SECRET_KEY, Schwab OAuth, DB creds). Use .env.example, or get the specific non-secret value another way." >&2
  exit 2
fi

# encrypted-secret salt and key/cert material
if printf '%s' "$cmd" | grep -Eq 'secret\.salt\b|[[:alnum:]_/-]\.(pem|key)\b'; then
  echo "BLOCKED by .claude/hooks/guard-secrets.sh: command references key/cert material (*.pem / *.key / secret.salt). These are encrypted-secret inputs; do not read or log them." >&2
  exit 2
fi

exit 0
