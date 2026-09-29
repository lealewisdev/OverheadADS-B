#!/usr/bin/env bash
# Prune stale entries from per-image .trivyignore files.
#
# Usage: prune-trivyignore.sh [--write] <context>=<image-ref> [...]
#
#   <context>    directory holding the Dockerfile and its .trivyignore
#   <image-ref>  published image to scan, e.g. host/owner/repo:tag-latest
#
# An entry is stale when it no longer shows up in a scan run the same way
# the build gate runs it (SBOM -> trivy sbom, --ignore-unfixed,
# CRITICAL,HIGH) but with an empty ignore file.
#
# Without --write: list stale entries, exit 1 if any were found.
# With --write:    remove them in place, exit 0.
set -euo pipefail
export LC_ALL=C

: "${TRIVY_CACHE_DIR:=$HOME/.cache/trivy}"

write=0
if [ "${1:-}" = "--write" ]; then write=1; shift; fi
if [ "$#" -lt 1 ]; then
  echo "usage: $0 [--write] <context>=<image-ref> [...]" >&2
  exit 2
fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
# An explicit empty ignore file stops Trivy from auto-loading ./.trivyignore
: > "$tmp/empty"

status=0

for target in "$@"; do
  context=${target%%=*}
  image=${target#*=}
  if [ "$context" = "$target" ] || [ -z "$context" ] || [ -z "$image" ]; then
    echo "invalid target '$target' (expected <context>=<image-ref>)" >&2
    exit 2
  fi

  ignorefile="$context/.trivyignore"
  if [ ! -f "$ignorefile" ]; then
    echo "$ignorefile: not found, skipping"
    continue
  fi

  work="$tmp/${context//\//_}"
  mkdir -p "$work"

  # Mirror the build gate: image -> CycloneDX SBOM -> trivy sbom.
  # --image-src remote scans the published image, never a stale local copy.
  trivy image \
    --quiet \
    --cache-dir "$TRIVY_CACHE_DIR" \
    --image-src remote \
    --format cyclonedx \
    --output "$work/sbom.cdx.json" \
    "$image"

  trivy sbom \
    --quiet \
    --cache-dir "$TRIVY_CACHE_DIR" \
    --ignorefile "$tmp/empty" \
    --ignore-unfixed \
    --severity CRITICAL,HIGH \
    --format json \
    --output "$work/report.json" \
    "$work/sbom.cdx.json"

  # Never treat a missing/broken report as "no vulnerabilities".
  jq -e '.SchemaVersion != null' "$work/report.json" >/dev/null

  jq -r '.Results[]?.Vulnerabilities[]?.VulnerabilityID' "$work/report.json" \
    | sort -u > "$work/live"

  # First token of every non-blank, non-comment line is the ID.
  awk '!/^[[:space:]]*(#|$)/ { print $1 }' "$ignorefile" \
    | sort -u > "$work/ignored"

  comm -23 "$work/ignored" "$work/live" > "$work/stale"

  if [ ! -s "$work/stale" ]; then
    echo "$ignorefile: no stale entries"
    continue
  fi

  echo "Stale entries in $ignorefile:"
  sed 's/^/  /' "$work/stale"

  if [ "$write" = 1 ]; then
    awk 'NR==FNR { stale[$1]; next } !($1 in stale)' \
      "$work/stale" "$ignorefile" > "$work/new"
    cat "$work/new" > "$ignorefile"
  else
    status=1
  fi
done

exit "$status"
