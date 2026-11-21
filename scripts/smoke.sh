#!/usr/bin/env bash
# Verifies through the ingress that a release is live and healthy.
# Usage: scripts/smoke.sh <git-sha>
set -euo pipefail

expected="${1:-}"
if [[ ! "$expected" =~ ^[0-9a-f]{7,40}$ ]]; then
  echo "Usage: $0 <git-sha>" >&2
  exit 2
fi

host="${SMOKE_HOST:-niyam.local}"
address="${SMOKE_ADDRESS:-127.0.0.1}"
port="${SMOKE_PORT:-80}"
timeout_seconds="${SMOKE_TIMEOUT_SECONDS:-120}"
required_passes="${SMOKE_REQUIRED_PASSES:-5}"

for tool in curl jq; do
  command -v "$tool" >/dev/null || { echo "FAIL: $tool is not installed" >&2; exit 2; }
done

# WSL does not inherit the Windows hosts entry, so the name is pinned here.
fetch() {
  curl --silent --fail --max-time 5 \
    --resolve "${host}:${port}:${address}" \
    "http://${host}:${port}$1" 2>/dev/null
}

reason=""

check_release() {
  local version ready page

  if ! version="$(fetch /version | jq -er '.app_version')"; then
    reason="/version is unavailable"
    return 1
  fi
  if [[ "$version" != "$expected" ]]; then
    reason="/version reports ${version}"
    return 1
  fi

  if ! ready="$(fetch /readyz | jq -er '.ready')" || [[ "$ready" != "true" ]]; then
    reason="/readyz is not ready"
    return 1
  fi

  if ! page="$(fetch /)"; then
    reason="the web page is unavailable"
    return 1
  fi
  if [[ "$page" != *"id=\"app-version\">${expected}<"* ]]; then
    reason="the page footer does not show ${expected}"
    return 1
  fi
}

# Several passes in a row prove old pods have left the load balancer.
passes=0
last_reason=""
deadline=$((SECONDS + timeout_seconds))

while ((SECONDS < deadline)); do
  if check_release; then
    passes=$((passes + 1))
    if ((passes >= required_passes)); then
      echo "PASS: ${expected} is live at http://${host}"
      exit 0
    fi
    sleep 1
  else
    passes=0
    if [[ "$reason" != "$last_reason" ]]; then
      echo "Waiting: ${reason}"
      last_reason="$reason"
    fi
    sleep 2
  fi
done

echo "FAIL: ${expected} was not live after ${timeout_seconds}s (${reason:-too few passes})" >&2
exit 1
