#!/usr/bin/env bash
# Portable Hermes Project Contract self-check. No Hermes/PyYAML needed — runs in
# CI (.github/workflows/contract.yml) and locally. Exit 0 = compliant.
set -uo pipefail
fail=0
err() { echo "FAIL: $1"; fail=1; }

# 1. Base compose exists and parses (dev overlay included when present).
if [ ! -f docker-compose.yml ]; then
  err "docker-compose.yml missing"
elif command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  files=(-f docker-compose.yml)
  [ -f docker-compose.dev.yml ] && files+=(-f docker-compose.dev.yml)
  # Ensure .env exists so explicit env_file references don't break CI parsing.
  [ -f .env ] || touch .env
  docker compose "${files[@]}" config -q || err "compose does not parse"
fi

# 2. Only canonical service names (frontend/api/worker/postgres/redis).
for bad in backend database db app; do
  grep -qE "^[[:space:]]{2}${bad}:" docker-compose.yml 2>/dev/null \
    && err "non-canonical service '${bad}:' (use frontend/api/worker/postgres/redis)"
done

# 3. Published host ports must be overridable (${VAR:-default}), not hard-coded.
grep -qE '^[[:space:]]*-[[:space:]]*"?[0-9]+:[0-9]+"?[[:space:]]*$' docker-compose.yml 2>/dev/null \
  && err 'hard-coded published port(s); use "${VAR:-default}:..."'

# 4. No forbidden tracked secrets / artifacts.
for f in .env.production .env.production.local deploy-manifest.json; do
  git ls-files --error-unmatch "$f" >/dev/null 2>&1 && err "forbidden tracked file: $f"
done
git ls-files 2>/dev/null | grep -qE '\.env\..*\.vps$' && err "tracked .env.*.vps secret"

# 5. An env template is committed.
ls .env.example .env.*.example >/dev/null 2>&1 || err ".env.example (or .env.<svc>.example) missing"

# 6. Required docs present and non-empty.
for d in README.md docs/ARCHITECTURE.md docs/RUNBOOK.md; do
  [ -s "$d" ] || err "missing/empty required doc: $d"
done

if [ "$fail" -eq 0 ]; then echo "Project Contract: OK"; else echo "Project Contract: FAILED"; fi
exit "$fail"
