#!/usr/bin/env bash
# Fail if any version-bump-guarded path changed without pyproject.toml's
# [project] version also changing.
#
# Usage:
#   guard-version-bump.sh <base-ref> [<head-ref>]
#
#   <base-ref>  git ref to diff from (a commit, tag, or branch)
#   <head-ref>  git ref to diff to; omit to compare against the current
#               working tree instead of a commit (used by the pre-commit
#               hook, which runs before HEAD includes the staged changes)
#
# Guarded paths are read from .forgejo/version-bump-paths.txt at the
# repo root, resolved via `git rev-parse --show-toplevel` so this works
# no matter which directory it's invoked from.
set -euo pipefail

if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
  echo "usage: $0 <base-ref> [<head-ref>]" >&2
  exit 2
fi
BASE=$1
HEAD=${2:-}

TOPLEVEL=$(git rev-parse --show-toplevel)
GUARD_PATHS_FILE="$TOPLEVEL/.forgejo/version-bump-paths.txt"

# Read as an array (not an unquoted command substitution) so each line
# is passed to git as its own pathspec, without the shell glob-expanding
# any wildcard entries first.
mapfile -t GUARD_PATHS < "$GUARD_PATHS_FILE"

if [ -n "$HEAD" ]; then
  CHANGED=$(git diff --name-only "$BASE" "$HEAD" -- "${GUARD_PATHS[@]}")
else
  CHANGED=$(git diff --name-only "$BASE" -- "${GUARD_PATHS[@]}")
fi

if [ -z "$CHANGED" ]; then
  exit 0
fi

extract_version() {
  grep -m1 -E '^version[[:space:]]*=' \
    | sed -E 's/version[[:space:]]*=[[:space:]]*"([^"]+)"/\1/'
}

BASE_VERSION=$(git show "$BASE:pyproject.toml" 2>/dev/null | extract_version || true)
if [ -n "$HEAD" ]; then
  HEAD_VERSION=$(git show "$HEAD:pyproject.toml" 2>/dev/null | extract_version || true)
  HEAD_LABEL=$HEAD
else
  HEAD_VERSION=$(extract_version < "$TOPLEVEL/pyproject.toml" || true)
  HEAD_LABEL="the working tree"
fi

if [ -z "$BASE_VERSION" ] || [ -z "$HEAD_VERSION" ]; then
  echo "::error::Could not read project.version from pyproject.toml at" \
    "$BASE or $HEAD_LABEL" >&2
  exit 1
fi

if [ "$BASE_VERSION" = "$HEAD_VERSION" ]; then
  # Carve-out: if the only guarded paths that changed are pyproject.toml
  # and/or uv.lock, it's possible only a dev-only dependency-group moved
  # - nothing that would actually change the runtime image. A single
  # Renovate dependency PR touches BOTH files together (constraint +
  # resolution), lockFileMaintenance touches just uv.lock, so both need
  # to be allowed here - anything else guarded (src/**, Dockerfile, ...)
  # falls through to the normal check below. Only worth the extra check
  # (a full two-ref worktree export) in CI; not worth the cost locally.
  ONLY_DEP_FILES=true
  if [ -n "$HEAD" ]; then
    while IFS= read -r f; do
      case "$f" in
        pyproject.toml | uv.lock) ;;
        *) ONLY_DEP_FILES=false ;;
      esac
    done <<<"$CHANGED"
  else
    ONLY_DEP_FILES=false
  fi

  if [ "$ONLY_DEP_FILES" = "true" ]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    if bash "$SCRIPT_DIR/runtime-deps-unchanged.sh" "$BASE" "$HEAD"; then
      echo "Only pyproject.toml/uv.lock changed, and the runtime" \
        "dependency set is unchanged (a dev-only dependency-group" \
        "bump) - no version bump required." >&2
      echo "runtime_unchanged=true" >> "${GITHUB_OUTPUT:-/dev/null}"
      exit 0
    fi
  fi

  echo "Changes touch files that would trigger a rebuild, but" \
    "pyproject.toml's version is still ${HEAD_VERSION}." >&2
  echo "Bump the version in pyproject.toml before merging" \
    "(devenv run bump-semver, or edit it by hand)." >&2
  exit 1
fi

exit 0
