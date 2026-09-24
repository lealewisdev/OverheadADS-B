#!/usr/bin/env bash
set -euo pipefail
export LC_ALL=C

write=0
if [ "${1:-}" = "--write" ]; then write=1; shift; fi
ignorefile=${1:?ignorefile}
image=${2:?image}

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
: > "$tmp/empty"

trivy image \
  --ignorefile "$tmp/empty" \
  --ignore-unfixed \
  --severity CRITICAL,HIGH \
  --quiet --format json "$image" \
  | jq -r '.Results[]?.Vulnerabilities[]?.VulnerabilityID' \
  | sort -u > "$tmp/live"

{ grep -oE '^(CVE-[0-9]+-[0-9]+|GHSA-[a-z0-9-]+)' "$ignorefile" || true; } \
  | sort -u > "$tmp/ignored"

comm -23 "$tmp/ignored" "$tmp/live" > "$tmp/stale"

if [ ! -s "$tmp/stale" ]; then
  echo "No stale entries in $ignorefile"
  exit 0
fi

echo "Stale entries in $ignorefile:"
sed 's/^/  /' "$tmp/stale"

if [ "$write" = 1 ]; then
  awk 'NR==FNR { stale[$1]; next } !($1 in stale)' \
    "$tmp/stale" "$ignorefile" > "$tmp/new"
  cat "$tmp/new" > "$ignorefile"
  exit 0
fi
exit 1
