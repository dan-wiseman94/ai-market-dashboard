#!/usr/bin/env bash
# Pre-commit guard — checks STAGED content only: leaked credentials, ruff lint/format,
# and oversized visual baselines.
#
# Every check runs in a throwaway, version-pinned container that mounts THIS worktree,
# so the hook behaves identically in the main checkout and in .claude/worktrees/*.
# It never touches the dev stack, never rewrites or re-stages files, and never blocks
# on infrastructure: if docker is unavailable it warns and passes.
#
# Install: make hooks     Bypass: git commit --no-verify   (or SKIP_HOOKS=1)
set -uo pipefail

[[ "${SKIP_HOOKS:-0}" == "1" ]] && exit 0

# Pinned to the ruff in pyproject.toml/uv.lock so results match `make lint` exactly.
readonly RUFF_IMAGE="ghcr.io/astral-sh/ruff:0.15.14"
# Floating, to match .github/workflows/check.yml, which also tracks :latest.
readonly GITLEAKS_IMAGE="ghcr.io/gitleaks/gitleaks:latest"

top="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
[[ -n "$top" ]] || exit 0

mapfile -d '' -t staged < <(git diff --cached --name-only --diff-filter=ACM -z)
(( ${#staged[@]} )) || exit 0

if ! docker info >/dev/null 2>&1; then
  printf '\033[33m! pre-commit: docker unavailable, skipping checks (make check still gates)\033[0m\n' >&2
  exit 0
fi

# A linked worktree's .git is a FILE holding an ABSOLUTE gitdir pointer, so mounting
# only the worktree leaves gitleaks unable to resolve the repo. It then reports
# "no leaks found" after scanning ZERO bytes — a silent pass. Mounting the shared git
# dir at its real path too is what makes worktrees work. Verified both ways in-repo.
common="$(cd "$(git rev-parse --git-common-dir 2>/dev/null)" 2>/dev/null && pwd)" || common=""
mounts=(-v "$top:$top")
if [[ -n "$common" && "$common" != "$top"/* ]]; then
  mounts+=(-v "$common:$common")
fi

failures=()

# --- leaked credentials ------------------------------------------------------
if [[ -f "$top/.gitleaks.toml" ]]; then
  scan_out="$(docker run --rm "${mounts[@]}" -w "$top" "$GITLEAKS_IMAGE" \
    git --staged --redact --config="$top/.gitleaks.toml" "$top" 2>&1)"
  scan_rc=$?
  if (( scan_rc != 0 )); then
    failures+=("credentials detected in the staged diff")
    printf '%s\n' "$scan_out" | tail -20 >&2
  elif [[ "$scan_out" == *"scanned ~0 bytes"* ]] && [[ -n "$(git diff --cached -p)" ]]; then
    # Self-check for the silent-pass mode described above: a non-empty staged patch
    # must produce a non-zero byte count. Zero means the hook is broken, not clean.
    failures+=("scanner read 0 bytes from a non-empty staged diff — hook misconfigured, NOT clean")
  fi
fi

# --- ruff (read-only: never --fix, never re-stage) ---------------------------
py=()
for f in "${staged[@]}"; do [[ "$f" == *.py ]] && py+=("$f"); done
if (( ${#py[@]} )); then
  if ! out="$(docker run --rm "${mounts[@]}" -w "$top" "$RUFF_IMAGE" \
      check --force-exclude -- "${py[@]}" 2>&1)"; then
    failures+=("ruff check")
    printf '%s\n' "$out" | tail -25 >&2
  fi
  if ! out="$(docker run --rm "${mounts[@]}" -w "$top" "$RUFF_IMAGE" \
      format --check --force-exclude -- "${py[@]}" 2>&1)"; then
    failures+=("ruff format — run 'make fmt'")
    printf '%s\n' "$out" | tail -15 >&2
  fi
fi

# --- visual baseline size ----------------------------------------------------
guard="$top/tools/hooks/check_visual_baseline_size.sh"
if [[ -x "$guard" ]] && ! "$guard"; then
  failures+=("visual baseline over the size limit")
fi

if (( ${#failures[@]} )); then
  printf '\n\033[31m✗ pre-commit failed:\033[0m\n' >&2
  printf '  - %s\n' "${failures[@]}" >&2
  printf '\nNothing was modified or unstaged. Bypass with: git commit --no-verify\n' >&2
  exit 1
fi

exit 0
