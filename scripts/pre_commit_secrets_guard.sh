#!/usr/bin/env bash
set -euo pipefail

# Simple pre-commit secrets guard: scans staged changes for high-risk patterns

PATTERNS=(
  'sk-[A-Za-z0-9]{16,}'
  'HYPERLIQUID_.*PRIVATE_KEY=.{3,}'
  '-----BEGIN [A-Z ]*PRIVATE KEY-----'
  'API_KEY=.{3,}'
  'API_SECRET=.{3,}'
)

fail=0
diff=$(git diff --cached -U0 || true)

for re in "${PATTERNS[@]}"; do
  if echo "$diff" | grep -E "$re" >/dev/null 2>&1; then
    echo "\n[SECRETS-GUARD] Potential secret detected matching pattern: $re" >&2
    fail=1
  fi
done

if [ "$fail" -ne 0 ]; then
  cat >&2 <<'EOF'

Commit aborted by secrets guard.
Move sensitive values into your local .env (or ~/.cryptobot/.env) and re-stage.

If this is a false positive, adjust your commit or tweak the guard patterns.
To bypass in emergencies, you can use: git commit --no-verify (not recommended).
EOF
  exit 1
fi

exit 0


