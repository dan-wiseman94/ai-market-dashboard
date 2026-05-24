#!/usr/bin/env bash
# Pre-commit guard — block visual baselines larger than 500KB.
set -euo pipefail

max_kb=500
found_large=""

while read -r file; do
  [[ -z "$file" ]] && continue
  size_kb=$(( $(stat -c '%s' "$file") / 1024 ))
  if (( size_kb > max_kb )); then
    found_large+="$file (${size_kb} KB)\n"
  fi
done < <(git diff --cached --name-only --diff-filter=AM | grep '^e2e/visual/__screenshots__/.*\.png$' || true)

if [[ -n "$found_large" ]]; then
  printf "Visual baselines exceed %dKB limit:\n%b" "$max_kb" "$found_large" >&2
  exit 1
fi
