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

Edit `.env`:

```env
POSTGRES_PASSWORD=your-secure-password

# Provider API keys
OPENROUTER_API_KEY=sk-or-...

# Comma-separated keys clients use to authenticate to this proxy
API_KEYS=your-proxy-key-1,your-proxy-key-2

# Key for the web UI
UI_API_KEY=your-ui-key
```

### 2. Configure routing

Edit `config.yml` to set up providers and model mappings:

```yaml
providers:
  openrouter:
    type: openai_compatible
    endpoint: https://openrouter.ai/api/v1

model_mappings:
  # Catch-all: route everything to GPT-4o-mini via OpenRouter
  "*": "openrouter:openai/gpt-4o-mini"
  # Or map specific models:
  # "gpt-4o": "openrouter:openai/gpt-4o"
  # "claude-*": "openrouter:anthropic/claude-3.5-sonnet"
```

Model names support `fnmatch` glob patterns. The first matching rule wins.

### 3. Run migrations

Once PostgreSQL is running, apply the Alembic schema before starting the backend:

```bash
make migrate
```

Use `make migrate-rollback` to verify the last revision can be reversed locally.

### 4. Run

**Development** (backend on :8000, hot reload, frontend served separately):

```bash
POSTGRES_PASSWORD=your-secure-password docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
cd frontend && npm install && npm run dev
```

- API: http://localhost:8000
- UI: http://localhost:5173

**Production** (requires a domain with DNS pointed at the server):

```bash
DOMAIN=your.domain.com ACME_EMAIL=you@example.com docker compose up -d
```

- API: `https://your.domain.com`
- UI: `https://logs.your.domain.com`
- Traefik dashboard: `http://127.0.0.1:8080`

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
| `POST /v1/chat/completions` | `API_KEYS` | Proxy chat completions |
| `GET /v1/models` | `API_KEYS` | List configured models |
| `GET /ui/v1/health` | `UI_API_KEY` | Authenticated UI connectivity check |
| `GET /ui/v1/requests` | `UI_API_KEY` | Request log browser |
| `GET /ui/v1/requests/{request_id}` | `UI_API_KEY` | Request detail |
| `GET /ui/v1/search` | `UI_API_KEY` | Full-text request search |
| `GET /ui/v1/stats` | `UI_API_KEY` | UI summary metrics |
| `GET /ui/v1/conversations` | `UI_API_KEY` | Grouped conversations |
| `GET /ui/v1/conversations/{group_key}/messages` | `UI_API_KEY` | Conversation messages |
| `GET /ui/v1/export/requests/{request_id}` | `UI_API_KEY` | Export a request as JSON or Markdown |

## Configuration reference

### `config.yml`

| Field | Description |
|---|---|
| `providers` | Named provider definitions (type, endpoint, headers) |
| `model_mappings` | `client-model: provider:real-model` mappings (glob patterns ok) |
| `access_rules` | Per-key model allow/deny lists (optional) |
| `modification_rules` | Rewrite request fields before forwarding (optional) |
| `logging.log_retention_days` | Auto-delete logs older than N days (default: 30) |

### Environment variables

| Variable | Required | Description |
|---|---|---|
| `POSTGRES_PASSWORD` | Yes | Database password |
| `API_KEYS` | Yes | Comma-separated proxy auth keys |
| `UI_API_KEY` | Yes | Web UI auth key |
| `OPENROUTER_API_KEY` | If using OpenRouter | Provider API key |
| `DOMAIN` | Production | Your domain name |
| `ACME_EMAIL` | Production | Email for Let's Encrypt |
