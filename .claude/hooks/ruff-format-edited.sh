#!/usr/bin/env bash
# PostToolUse(Edit|Write|MultiEdit) — format the just-edited Python file INSIDE the
# `web` container. The host has no Python deps by design (see CLAUDE.md), so a host-level
# `ruff` would be wrong; this mirrors lefthook's container invocation but runs per-edit.
#
# No-op (exit 0) unless: the file is *.py, lives in this repo, and the `web` service is up.
# Never blocks.

file="$(python3 -c 'import json,sys
try:
    print((json.load(sys.stdin).get("tool_input") or {}).get("file_path",""))
except Exception:
    pass' 2>/dev/null || true)"

case "$file" in
  *.py) ;;
  *) exit 0 ;;
esac

root="${CLAUDE_PROJECT_DIR:-}"
if [ -z "$root" ]; then
  root="$(git -C "$(dirname "$file")" rev-parse --show-toplevel 2>/dev/null || true)"
fi
[ -n "$root" ] || exit 0

case "$file" in
  "$root"/*) ;;
  *) exit 0 ;;
esac

cd "$root" || exit 0
docker compose ps --status running --services 2>/dev/null | grep -qx web || exit 0

rel="${file#"$root"/}"
docker compose exec -T --workdir /app web uv run ruff format "$rel" >/dev/null 2>&1 || true
exit 0
