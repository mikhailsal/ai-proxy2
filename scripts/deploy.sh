#!/usr/bin/env bash
# Deploy the current working tree to a remote server.
#
# The application runs inside an LXD container on the remote host, so the
# deploy is a two-hop sync:
#   1. rsync the working tree to a staging directory on the remote host
#   2. tar-pipe the staging directory into the LXD container's app directory
#   3. rebuild + restart the Docker Compose stack inside the container
#
# All environment-specific values (host, container, paths) come from the
# gitignored `deploy.env` file in the repo root. Copy `deploy.env.example`
# to `deploy.env` and fill it in. Never commit `deploy.env`: the repository
# is public and must not contain server names, addresses, or secrets.
#
# Server-only files (.env, config.secrets.yml, compose overrides) are never
# shipped and never deleted on the server: rsync excludes them, and the tar
# extraction only overwrites files present in the archive.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_FILE="$REPO_ROOT/deploy.env"

log() { printf '\033[36m[deploy]\033[0m %s\n' "$*"; }
die() { printf '\033[31m[deploy] ERROR:\033[0m %s\n' "$*" >&2; exit 1; }

[[ -f "$CONFIG_FILE" ]] || die "deploy.env not found. Copy deploy.env.example to deploy.env and fill it in."

# shellcheck disable=SC1090
source "$CONFIG_FILE"

: "${DEPLOY_SSH_HOST:?DEPLOY_SSH_HOST must be set in deploy.env}"
: "${DEPLOY_LXD_CONTAINER:?DEPLOY_LXD_CONTAINER must be set in deploy.env}"
: "${DEPLOY_APP_DIR:?DEPLOY_APP_DIR must be set in deploy.env}"
DEPLOY_COMPOSE_FILES="${DEPLOY_COMPOSE_FILES:-docker-compose.yml}"
DEPLOY_STAGING_DIR="${DEPLOY_STAGING_DIR:-.deploy-staging/ai-proxy2}"
DEPLOY_HEALTH_URL="${DEPLOY_HEALTH_URL:-}"

COMPOSE_ARGS=""
for f in $DEPLOY_COMPOSE_FILES; do
    COMPOSE_ARGS+=" -f $f"
done

# Never ship secrets, local-only config, build artifacts, or VCS data.
RSYNC_EXCLUDES=(
    --include '.env.example'
    --exclude '.git/'
    --exclude '.env'
    --exclude '.env.*'
    --exclude 'config.secrets.yml'
    --exclude 'deploy.env'
    --exclude 'tmp-credentials-for-testing.md'
    --exclude 'certs/'
    --exclude 'backups/'
    --exclude 'node_modules/'
    --exclude 'frontend/dist/'
    --exclude 'frontend/coverage/'
    --exclude '__pycache__/'
    --exclude '.venv/'
    --exclude '.mypy_cache/'
    --exclude '.ruff_cache/'
    --exclude '.coverage'
    --exclude 'htmlcov/'
    --exclude '*.log'
    --exclude '.cursor/'
    --exclude '.idea/'
    --exclude '.vscode/'
)

log "Syncing working tree to $DEPLOY_SSH_HOST:$DEPLOY_STAGING_DIR ..."
ssh "$DEPLOY_SSH_HOST" "mkdir -p '$DEPLOY_STAGING_DIR'"
rsync -az --delete "${RSYNC_EXCLUDES[@]}" "$REPO_ROOT/" "$DEPLOY_SSH_HOST:$DEPLOY_STAGING_DIR/"

log "Copying code into container '$DEPLOY_LXD_CONTAINER' at $DEPLOY_APP_DIR ..."
ssh "$DEPLOY_SSH_HOST" \
    "tar -C '$DEPLOY_STAGING_DIR' -cf - . | sudo lxc exec '$DEPLOY_LXD_CONTAINER' -- tar -C '$DEPLOY_APP_DIR' -xof -"

run_in_app() {
    ssh "$DEPLOY_SSH_HOST" \
        "sudo lxc exec '$DEPLOY_LXD_CONTAINER' -- sh -c 'cd \"$DEPLOY_APP_DIR\" && $1'"
}

log "Building images (compose files:$COMPOSE_ARGS) ..."
run_in_app "docker compose$COMPOSE_ARGS build"

log "Validating config ..."
run_in_app "docker compose$COMPOSE_ARGS run --rm --no-deps backend python -m ai_proxy.config.validate"

log "Restarting stack ..."
run_in_app "docker compose$COMPOSE_ARGS up -d"

log "Applying database migrations ..."
run_in_app "docker compose$COMPOSE_ARGS run --rm backend python -m alembic upgrade head"

log "Stack status:"
run_in_app "docker compose$COMPOSE_ARGS ps"

if [[ -n "$DEPLOY_HEALTH_URL" ]]; then
    log "Health check: $DEPLOY_HEALTH_URL"
    if curl --fail --silent --show-error --max-time 15 "$DEPLOY_HEALTH_URL" > /dev/null; then
        log "Health check passed."
    else
        die "Health check failed."
    fi
fi

log "Deploy complete."
