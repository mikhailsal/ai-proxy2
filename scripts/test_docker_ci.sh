#!/usr/bin/env bash
# Run only against the disposable CI stack, never the production compose file.
set -euo pipefail
cd "$(dirname "$0")/.."
project="ai-proxy-ci-${GITHUB_RUN_ID:-local}-$$"
compose=(docker compose -p "$project" -f docker-compose.ci.yml)
cleanup() {
    status=$?
    if (( status != 0 )); then
        "${compose[@]}" logs --no-color || true
    fi
    "${compose[@]}" down --volumes --remove-orphans || true
    exit "$status"
}
trap cleanup EXIT

docker info >/dev/null
"${compose[@]}" config --quiet
"${compose[@]}" build
"${compose[@]}" up --detach --wait --wait-timeout 120 backend frontend
"${compose[@]}" exec -T backend python - <<'PY'
import json
import urllib.request

base = "http://localhost:8000"
for path in ("/health", "/ui/v1/health"):
    with urllib.request.urlopen(base + path, timeout=10) as response:
        assert response.status == 200
        assert json.load(response) == {"status": "ok"}
request = urllib.request.Request(base + "/admin/reload-config", method="POST")
with urllib.request.urlopen(request, timeout=10) as response:
    assert json.load(response) == {"status": "reloaded"}
PY
"${compose[@]}" exec -T frontend wget -q -O - http://localhost/ | grep -i '<!doctype html>' >/dev/null
echo 'Docker integration passed: migrations, backend health/reload, frontend HTML.'
