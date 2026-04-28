# AI Proxy v2

An OpenAI-compatible API proxy with logging, model routing, and a web UI for reviewing request history.

## Stack

- **Backend**: Python 3.10 + FastAPI
- **Database**: PostgreSQL 16
- **Frontend**: React 18 + Vite + TypeScript
- **Reverse proxy**: Traefik (production only)

## Quick start

### 1. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with infrastructure secrets:

```env
POSTGRES_PASSWORD=your-secure-password

# Default provider API key (used when no key_mapping overrides it)
OPENROUTER_API_KEY=sk-or-...
```

### 2. Configure secrets

```bash
cp config.secrets.example.yml config.secrets.yml
```

Edit `config.secrets.yml` with your application secrets:

```yaml
# Proxy access keys — clients authenticate with these
api_keys:
  - "your-proxy-key-1"
  - "your-proxy-key-2"

# Web UI dashboard key
ui_api_key: "your-ui-key"

# Per-client provider key routing (optional)
# Client keys are stored in plaintext — auto-hashed at load time
key_mappings:
  "your-proxy-key-1":
    provider_keys:
      openrouter: "sk-or-v1-client-specific-key"
```

This file is gitignored and must never be committed.

### 3. Configure routing

Edit `config.yml` to set up providers and model mappings:

```yaml
providers:
  openrouter:
    type: openai_compatible
    endpoint: https://openrouter.ai/api/v1

model_mappings:
  "gpt-4o": "openrouter:openai/gpt-4o"
  "claude-*": "openrouter:anthropic/claude-3.5-sonnet"
  "*": "openrouter:openai/gpt-4o-mini"  # fallback
```

Model names support `fnmatch` glob patterns. The first matching rule wins.

### 3a. Provider-aware routing (optional)

Provider-aware routing lets you send the same model to different gateways depending on which sub-provider the client requests. This is useful when a particular sub-provider is cheaper, faster, or only available on a specific gateway.

Add provider-qualified entries to `model_mappings` using the `model+provider` format on the left side:

```yaml
model_mappings:
  # Base route (no provider preference)
  "openai/gpt-oss-120b": "kilocode:openai/gpt-oss-120b"
  # Route to kilocode when the client requests bedrock
  "openai/gpt-oss-120b+bedrock": "kilocode:openai/gpt-oss-120b+bedrock"
  # Route to openrouter when the client requests deepinfra
  "openai/gpt-oss-120b+deepinfra": "openrouter:openai/gpt-oss-120b+deepinfra"
  # Rename provider slugs (Google -> google-ai-studio)
  "google/gemma-4-26b-a4b-it+Google": "openrouter:google/gemma-4-26b-a4b-it+google-ai-studio"
```

Clients can request a sub-provider in two ways — the proxy handles both transparently:

1. **`+suffix` on the model name**: `"model": "openai/gpt-oss-120b+deepinfra"`
2. **OpenRouter-style `provider.order`** in the request body:
   ```json
   {
     "model": "openai/gpt-oss-120b",
     "provider": { "order": ["deepinfra"] }
   }
   ```

**Resolution order:**

| Priority | Source | Description |
|---|---|---|
| 1 | `+suffix` on model name | Highest — always checked first |
| 2 | `provider.order` in body | Checked when no `+suffix` is present |
| 3 | Base model mapping | Fallback when no provider-qualified entry matches |

**Edge cases:**

- When both `+suffix` and `provider.order` are present, `+suffix` wins.
- Provider names are matched **case-insensitively** (e.g., `DeepInfra` matches `deepinfra`).
- When a provider-qualified config entry renames the provider slug (e.g., `+Google` → `+google-ai-studio`), the renamed slug is forwarded upstream.
- When no matching provider-qualified entry exists, the proxy falls back to the base model mapping and passes through the client's provider preference normally.
- **Conflict detection**: at config load time, the proxy logs an error when ambiguous entries are detected (e.g., a base mapping pins to provider X via one gateway, but a qualified entry routes the same provider through a different gateway).

### 4. Bypass mode (optional)

When bypass is enabled in `config.yml`, clients who are **not** in the `api_keys` list can still use the proxy by sending their own provider API key directly:

```yaml
bypass:
  enabled: true   # accept unknown keys and forward them to the provider
  # enabled: false  # reject all unknown keys (only api_keys accepted)
```

**Key priority** (configured keys always win):

| Client key | Bypass | Result |
|---|---|---|
| Known key + has key_mapping | any | Mapped provider key is used |
| Known key, no mapping | any | Adapter default key (from env) |
| Unknown key | enabled | Client's raw key forwarded to provider |
| Unknown key | disabled | Request rejected (401) |

### 5. Run migrations

Compose now runs Alembic automatically before the backend starts. If you want to run it manually:

```bash
make migrate
```

Use `make migrate-rollback` to verify the last revision can be reversed locally.

### 6. Install quality hooks

Set the repository-local Git hooks path so commits run the tracked pre-commit checks:

```bash
make install-hooks
```

The pre-commit workflow enforces:

- backend Ruff and mypy
- frontend ESLint
- repository code-size limits
- backend coverage of at least 95%
- frontend line and statement coverage of at least 95%

### 7. Run

**Development** (backend on :8000, Dockerized frontend on :3000, optional Vite frontend for local UI edits):

```bash
POSTGRES_PASSWORD=your-secure-password docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
cd frontend && npm install && npm run dev
```

`make up` and `make up-dev` now run a config validation step in the backend container first and fail immediately if `config.yml` or `config.secrets.yml` is invalid.

When the backend is already running, you can hot-reload `config.yml` and `config.secrets.yml` without restarting the stack:

```bash
make reload-config
```

Override the backend URL when needed, for example `make reload-config API_BASE_URL=http://127.0.0.1:8001`.

- API: http://localhost:8000
- Docker UI: http://localhost:3000
- Vite UI: http://localhost:5173

**Production** (requires a domain with DNS pointed at the server):

```bash
DOMAIN=your.domain.com ACME_EMAIL=you@example.com docker compose up -d
```

- API: `https://your.domain.com`
- UI: `https://logs.your.domain.com`
- Traefik dashboard: `http://127.0.0.1:18080` by default, or `TRAEFIK_DASHBOARD_PORT` if overridden

## Connecting clients

The proxy exposes an OpenAI-compatible API. Point any OpenAI client at it:

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://your.domain.com/v1",
    api_key="your-proxy-key",
)

response = client.chat.completions.create(
    model="gpt-4o-mini",  # must match a key in model_mappings
    messages=[{"role": "user", "content": "Hello"}],
)
```

Or with curl:

```bash
curl https://your.domain.com/v1/chat/completions \
  -H "Authorization: Bearer your-proxy-key" \
  -H "Content-Type: application/json" \
  -d '{"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "Hello"}]}'
```

Streaming (`"stream": true`) is supported.

## API endpoints

| Endpoint | Auth | Description |
|---|---|---|
| `POST /v1/chat/completions` | `api_keys` / bypass | Proxy chat completions |
| `GET /v1/models` | `api_keys` / bypass | List current proxy models, including wildcard-expanded provider models |
| `POST /admin/reload-config` | none | Hot-reload config and secrets |
| `GET /ui/v1/health` | `ui_api_key` | Authenticated UI connectivity check |
| `GET /ui/v1/requests` | `ui_api_key` | Request log browser |
| `GET /ui/v1/requests/{request_id}` | `ui_api_key` | Request detail |
| `GET /ui/v1/search` | `ui_api_key` | Full-text request search |
| `GET /ui/v1/stats` | `ui_api_key` | UI summary metrics |
| `GET /ui/v1/conversations` | `ui_api_key` | Grouped conversations |
| `GET /ui/v1/conversations/{group_key}/messages` | `ui_api_key` | Conversation messages |
| `GET /ui/v1/export/requests/{request_id}` | `ui_api_key` | Export a request as JSON or Markdown |

## Configuration reference

Configuration is split into two files:

- **`config.yml`** (committed) — public routing and behavior settings
- **`config.secrets.yml`** (gitignored) — all API keys and secrets

### `config.yml`

| Field | Description |
|---|---|
| `providers` | Named provider definitions (type, endpoint, headers) |
| `model_mappings` | `client-model: provider:real-model` mappings (glob patterns ok on both sides; upstream metadata is forwarded on `/v1/models` when available). Provider-qualified keys (`model+provider`) enable gateway selection based on sub-provider — see §3a |
| `response.include_ai_proxy_route` | Add the resolved `provider:model` route to JSON client responses (default: true) |
| `bypass.enabled` | Accept unknown keys and forward them to the provider (default: false) |
| `access_rules` | Per-key model allow/deny lists (optional) |
| `modification_rules` | Rewrite request fields before forwarding (optional) |
| `logging.log_retention_days` | Auto-delete logs older than N days (default: 30) |
| `grouping.default_field` | Field used for conversation grouping (default: `system_prompt_first_user_first_assistant`) |

### `config.secrets.yml`

| Field | Description |
|---|---|
| `api_keys` | List of proxy access keys that clients use to authenticate |
| `ui_api_key` | Key required to access the web UI endpoints |
| `key_mappings` | Per-client mapping of proxy key to upstream provider keys |

Client keys in `key_mappings` are written in plaintext — the proxy hashes them automatically at load time (SHA-256). See `config.secrets.example.yml` for the full template.

### Environment variables (`.env`)

| Variable | Required | Description |
|---|---|---|
| `POSTGRES_PASSWORD` | Yes | Database password |
| `OPENROUTER_API_KEY` | If using OpenRouter | Default provider API key |
| `DOMAIN` | Production | Your domain name |
| `ACME_EMAIL` | Production | Email for Let's Encrypt |

Legacy support: `API_KEYS` and `UI_API_KEY` env vars still work as fallback if `config.secrets.yml` is absent.

## Quality checks

Run the full local quality gate before opening a PR:

```bash
make quality-check
```

This runs the repository line-limit checker, backend lint/type checks,
backend coverage, frontend lint, and frontend coverage.
