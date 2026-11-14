# Agent Notes — ai-proxy2

## Updating `config.yml` on the remote server

When **only** `config.yml` changes (no backend/frontend code or dependency changes):

- **Do NOT run `scripts/deploy.sh` / `make deploy`** — it rebuilds the Docker images from scratch.
- `config.yml` is bind-mounted into the `backend` container (`./config.yml:/app/config.yml:ro` in `docker-compose.yml`).
- Read target coordinates (`DEPLOY_SSH_HOST`, `DEPLOY_LXD_CONTAINER`, `DEPLOY_APP_DIR`, `DEPLOY_COMPOSE_FILES`) from gitignored `deploy.env`, copy `config.yml` into `$DEPLOY_APP_DIR/config.yml` inside the LXD container, and **restart the `backend` container** (`docker compose ... restart backend`).
- **Known issue**: despite `WATCHFILES_FORCE_POLLING=true` and `POST /admin/reload-config`, config changes on the remote container are not always picked up reliably without restarting `backend` — always restart `backend` and verify `/health` + a test request.
- Never commit or hardcode server hostnames, IPs, container names, or secrets from `deploy.env`.
