#!/usr/bin/env bash
# The gate every ticket and the trunk must pass.
#
# Every check runs even after one fails, so a single pass reports everything an
# engineer needs to fix rather than one error at a time.
set -uo pipefail

cd "$(dirname "$0")/.."

failed=0
run() {
  local name="$1"; shift
  printf '\n=== %s ===\n' "$name"
  if "$@"; then
    echo "--- $name: PASS"
  else
    echo "--- $name: FAIL (exit $?)"
    failed=1
  fi
}

if [ ! -d node_modules ]; then
  echo "node_modules is missing; run 'npm ci' first" >&2
  exit 1
fi

run typecheck   npm run --silent typecheck
run lint        npm run --silent lint
run format      npm run --silent format:check
run test        npm run --silent test -- --ci --silent

printf '\n'
if [ "$failed" -eq 0 ]; then
  echo "verify: PASS"
else
  echo "verify: FAIL"
fi
exit "$failed"
