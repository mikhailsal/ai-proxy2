# Plan: AI Proxy v2

## TL;DR

Greenfield proxy server between AI clients and providers. **Python 3.12 + FastAPI** backend (proven in v1), **PostgreSQL 16** for log storage (replacing dual SQLite+text), **React 18 + Vite + TypeScript** frontend. Docker Compose deployment. 8 phases, each independently testable. Fixes all v1 pain points: single DB source of truth, typed DTOs, proper API key hashing (SHA-256), hot-reloadable config, real dialog grouping.

## Architecture Decisions
you choose
| Decision | Choice | Rationale |
|----------|--------|-----------|
| Language | **Python 3.12+** | V1 uses Python/FastAPI successfully; LiteLLM available; rich AI ecosystem |
| Web framework | **FastAPI + Uvicorn** | Async-native, streaming support proven in v1, OpenAPI docs built-in |
| HTTP client | **httpx** (async) | Non-blocking, streaming support, same as v1 |
| Database | **PostgreSQL 16** | JSONB for flexible request/response storage, FTS via `tsvector`, concurrent access, proper ACID. Replaces v1's dual text+SQLite approach |
| ORM/Query | **SQLAlchemy 2.0 async** + Alembic migrations | Type-safe queries, migration management, async engine |
| Frontend | **React 18 + Vite + TypeScript** | Same as v1 (team knows it), huge ecosystem, virtual scrolling libraries (`@tanstack/virtual`) |
| State management | **TanStack Query (React Query)** | Server state caching, pagination, real-time invalidation |
| Deployment | **Docker Compose** | Traefik + proxy + DB + frontend |
| Config | **YAML** (same as v1) | Human-readable, proven pattern |
| Testing | **pytest + pytest-asyncio + httpx test client** (backend), **Vitest + Playwright** (frontend) |
| Linting | **ruff** (replaces black+isort+flake8), **mypy** strict mode |

## Project Structure (target)

```
ai-proxy2/
├── backend/
│   ├── ai_proxy/
│   │   ├── __init__.py
│   │   ├── app.py                    # FastAPI app factory
│   │   ├── config/
│   │   │   ├── settings.py           # Pydantic Settings (env + YAML)
│   │   │   └── loader.py             # YAML config loader, hot-reload
│   │   ├── api/
│   │   │   ├── deps.py               # Dependency injection
│   │   │   ├── proxy/
│   │   │   │   ├── router.py         # /v1/chat/completions, /v1/models
│   │   │   │   └── streaming.py      # SSE streaming logic
│   │   │   └── ui/
│   │   │       ├── requests.py       # Log browsing API
│   │   │       ├── chats.py          # Chat reconstruction API
│   │   │       ├── diagnostics.py    # Cache issue detection API
│   │   │       └── export.py         # Export endpoints
│   │   ├── core/
│   │   │   ├── routing.py            # Provider selection + model mapping
│   │   │   ├── modification.py       # Request enrichment/modification rules
│   │   │   └── access.py             # Model allowlist/blocklist
│   │   ├── adapters/
│   │   │   ├── base.py               # Abstract BaseAdapter (typed)
│   │   │   ├── openai_compat.py      # Generic OpenAI-compatible adapter
│   │   │   └── registry.py           # Adapter registry
│   │   ├── logging/
│   │   │   ├── service.py            # Async logging service (background tasks)
│   │   │   ├── masking.py            # API key masking
│   │   │   └── models.py             # Log entry Pydantic models
│   │   ├── db/
│   │   │   ├── engine.py             # Async engine + session factory
│   │   │   ├── models.py             # SQLAlchemy ORM models
│   │   │   ├── repositories/         # Repository pattern per entity
│   │   │   │   ├── requests.py
│   │   │   │   └── chats.py
│   │   │   └── migrations/           # Alembic
│   │   │       └── versions/
│   │   ├── services/
│   │   │   ├── chat_reconstruction.py  # Dialog flow reconstruction
│   │   │   ├── diagnostics.py          # Cache/history issue detection
│   │   │   └── grouping.py            # Request grouping logic
│   │   └── security/
│   │       └── auth.py               # API key validation (SHA-256)
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/
│   │   ├── functional/
│   │   └── conftest.py               # Shared fixtures (test DB, app client)
│   ├── pyproject.toml
│   ├── alembic.ini
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── RequestBrowser/        # Request list + filters
│   │   │   ├── RequestDetail/         # Request/response cards
│   │   │   ├── ChatView/             # Chat reconstruction view
│   │   │   ├── JsonViewer/           # Universal JSON renderer
│   │   │   ├── Diagnostics/          # Cache issue indicators
│   │   │   └── common/               # Shared UI components
│   │   ├── hooks/                     # Custom React hooks
│   │   ├── api/                       # API client (typed)
│   │   ├── types/                     # TypeScript types
│   │   └── App.tsx
│   ├── tests/
│   │   ├── unit/                      # Vitest component tests
│   │   └── e2e/                       # Playwright
│   ├── package.json
│   ├── vite.config.ts
│   └── Dockerfile
├── docker-compose.yml
├── docker-compose.dev.yml
├── config.yml                         # Main configuration
├── Makefile
└── .pre-commit-config.yaml
```

---

## Phase 1: Project Scaffolding & CI Infrastructure

**Goal**: Runnable project skeleton with all tooling — any future code drops into established patterns.

**Steps**:

- [ ] **1.1** Initialize monorepo structure: `backend/`, `frontend/`, root `Makefile`, `.gitignore`, `.editorconfig`
- [ ] **1.2** Backend skeleton:
  - `pyproject.toml` with all dependencies (fastapi, uvicorn, httpx, sqlalchemy[asyncio], asyncpg, alembic, pydantic-settings, structlog, pyyaml, ruff, mypy, pytest, pytest-asyncio, pytest-cov)
  - Ruff config (replaces black+isort+flake8; max line length, target Python 3.12)
  - Mypy strict config
  - `ai_proxy/app.py` — minimal FastAPI app with health endpoint returning `{"status": "ok"}`
- [ ] **1.3** Frontend skeleton:
  - Vite + React + TypeScript via `npm create vite@latest`
  - ESLint + Prettier config
  - Vitest config
  - Placeholder `App.tsx` rendering "AI Proxy v2"
- [ ] **1.4** Docker infrastructure:
  - `backend/Dockerfile` (multi-stage: deps → app, non-root user)
  - `frontend/Dockerfile` (multi-stage: build → nginx)
  - `docker-compose.yml`: postgres (16-alpine), backend, frontend
  - `docker-compose.dev.yml`: with hot-reload mounts, exposed ports
  - Traefik reverse proxy config (HTTPS, routing rules)
- [ ] **1.5** Pre-commit hooks (`.pre-commit-config.yaml`):
  - ruff (format + lint)
  - mypy
  - trailing whitespace, EOF fixer, YAML lint
  - Frontend: ESLint
- [ ] **1.6** Makefile targets:
  - `make lint`, `make format`, `make test-unit`, `make test-integration`, `make test-all`, `make coverage`, `make up`, `make down`, `make migrate`

**Verification**:
- [ ] `make lint` passes with zero findings
- [ ] `make test-unit` runs and passes (health endpoint test)
- [ ] `docker compose up` starts all 3 services, frontend serves page, backend responds to `/health`
- [ ] Pre-commit hooks execute on `git commit`
- [ ] `make coverage` reports 100% on the minimal codebase

---

## Phase 2: Database Schema & Migrations

**Goal**: Complete database schema that supports all features described in the spec, with migrations.

**Steps**:

- [ ] **2.1** Set up SQLAlchemy 2.0 async engine in `db/engine.py`:
  - Async engine factory with connection pooling
  - Async session factory (scoped per request via FastAPI dependency)
  - `get_db_session` dependency for injection
- [ ] **2.2** Alembic configuration (`alembic.ini`, `migrations/env.py`) with async support
- [ ] **2.3** Define ORM models in `db/models.py`:
  - **`Provider`** table: `id`, `name`, `endpoint_url`, `api_key_encrypted`, `provider_type`, `is_active`, `settings_json`, `created_at`
  - **`ProxyRequest`** table: `id` (UUID), `timestamp`, `client_ip`, `client_api_key_hash` (SHA-256), `method`, `path`, `request_headers` (JSONB), `request_body` (JSONB), `response_status_code`, `response_headers` (JSONB), `response_body` (JSONB), `stream_chunks` (JSONB array), `model_requested`, `model_resolved`, `provider_id` (FK), `latency_ms`, `input_tokens`, `output_tokens`, `total_tokens`, `cost`, `cache_status`, `reasoning_tokens`, `error_message`, `metadata` (JSONB for any extra fields)
  - **`ProviderDebugLog`** table: `id`, `proxy_request_id` (FK), `timestamp`, `raw_payload` (JSONB), `source`
  - Proper indices: on `timestamp`, `client_api_key_hash`, `model_requested`, `model_resolved`, `provider_id`, `response_status_code`; GIN index on `request_body` and `response_body` for JSONB queries; GIN index on `tsvector` column for FTS
- [ ] **2.4** Create initial Alembic migration (`make migrate-create msg="initial schema"`)
- [ ] **2.5** Repository layer in `db/repositories/requests.py`:
  - `create_request()` — insert ProxyRequest
  - `get_request(id)` — fetch by UUID
  - `list_requests(filters, pagination)` — cursor-based pagination with filters (time range, model, client, status)
  - `search_requests(query)` — full-text search via PostgreSQL tsvector
  - `get_requests_for_chat(grouping_criteria)` — fetch grouped requests for chat reconstruction
- [ ] **2.6** Repository for `db/repositories/chats.py`:
  - `get_grouped_conversations(group_by, filters)` — group by system prompt, client, model, session_id, custom field
  - `get_conversation_flow(conversation_id)` — ordered requests within a conversation

**Verification**:
- [ ] `make migrate` applies migration against clean PostgreSQL instance; `make migrate-rollback` reverses it cleanly
- [ ] Unit tests for all repository methods with real PostgreSQL (via testcontainers or docker-compose test service)
- [ ] Schema matches the spec: all fields from spec section 2.3.1 are captured
- [ ] FTS search returns correct results for request/response content
- [ ] Cursor-based pagination returns correct pages with stable ordering

---

## Phase 3: Core Proxy Engine

**Goal**: Fully working transparent proxy for OpenAI-compatible requests, with streaming, routing, and model mapping. No logging yet — just correct proxying.

**Steps**:

- [ ] **3.1** Configuration system (`config/settings.py`, `config/loader.py`):
  - Pydantic Settings class loading from environment + YAML file
  - Sections: `providers` (list of provider configs), `model_mappings` (model → provider:model), `access_rules`, `modification_rules`
  - YAML loader with validation via Pydantic models
  - Hot-reload: file watcher (watchfiles) that reloads config on change, exposed via `POST /admin/reload-config` endpoint
  - Reference: v1's `core/config.py` pattern with `fnmatch` wildcards — reuse the wildcard matching
- [ ] **3.2** Adapter base and registry (`adapters/base.py`, `adapters/registry.py`):
  - `BaseAdapter` abstract class with:
    - `async chat_completions(request_body: dict, headers: dict) -> httpx.Response`
    - `async stream_chat_completions(request_body: dict, headers: dict) -> AsyncGenerator[bytes, None]`
  - `AdapterRegistry`: maps provider name → adapter instance, constructed from config
- [ ] **3.3** OpenAI-compatible adapter (`adapters/openai_compat.py`):
  - Single adapter handling any OpenAI-compatible provider (OpenRouter, direct OpenAI, etc.)
  - Configurable endpoint URL, API key, custom headers per provider
  - Non-streaming: forward request via httpx, return response
  - Streaming: forward and yield SSE chunks, handle `[DONE]` marker
  - Provider-specific enrichment hooks (e.g., OpenRouter's additional fields)
  - Timeout configuration per provider
- [ ] **3.4** Request routing (`core/routing.py`):
  - `Router.resolve(model_requested: str) -> tuple[str, str, BaseAdapter]` — returns (provider_name, mapped_model, adapter)
  - Model mapping: exact match → wildcard match (fnmatch) → default
  - Fallback providers: if primary adapter raises connection error, try fallback chain
  - Reference v1: `core/routing.py` `_get_adapter()` pattern, but with typed return
- [ ] **3.5** Model access control (`core/access.py`):
  - Allowlist/blocklist per API key (from config)
  - Check runs before routing
  - Return 403 with clear error message for blocked models
- [ ] **3.6** Request modification engine (`core/modification.py`):
  - Rule-based modifications from config:
    - `add_header`, `remove_header`, `set_field`, `remove_field`
    - Conditional: applies only when provider/model matches pattern
  - Provider-specific field enrichment (e.g., OpenRouter `transforms`, `route`)
- [ ] **3.7** Proxy API endpoint (`api/proxy/router.py`):
  - `POST /v1/chat/completions` — main proxy endpoint
    - Parse request body
    - Authenticate client API key (`security/auth.py` — SHA-256 hashing, not v1's `hash()`)
    - Check model access
    - Resolve model + provider via Router
    - Apply modification rules
    - Forward to adapter (streaming or non-streaming based on `stream` field)
    - Return response to client
  - `GET /v1/models` — return list of available models from config (filtered by client's access rules)
- [ ] **3.8** SSE streaming handler (`api/proxy/streaming.py`):
  - Async generator that reads from adapter stream and yields to client
  - Parse each chunk to accumulate full response (for logging in Phase 4)
  - Handle connection drops (client disconnects mid-stream)
  - Handle provider errors mid-stream (send SSE error event + close)
  - Preserve original chunk format exactly (v1's successful pattern)

**Verification**:
- [ ] Unit tests for: config loading + validation, model mapping (exact/wildcard/default), access control (allow/block), modification rules, Router resolution, adapter construction
- [ ] Integration test: start FastAPI test client → send non-streaming request → receive correct response from mocked httpx
- [ ] Integration test: streaming request → receive all SSE chunks correctly, `[DONE]` marker present
- [ ] Integration test: model mapping transforms requested model to mapped model in the outgoing request
- [ ] Integration test: blocked model returns 403
- [ ] Integration test: modification rules add/remove fields correctly
- [ ] Integration test: fallback provider activated when primary returns connection error
- [ ] Integration test: client disconnect during stream is handled gracefully (no server crash)
- [ ] Functional test: docker compose up → real (mocked) proxy request end-to-end
- [ ] Coverage ≥ 95% for all Phase 3 code

---

## Phase 4: Async Logging Pipeline

**Goal**: Every request/response is logged to PostgreSQL without blocking the proxy path. Streaming chunks are accumulated and stored as complete records.

**Steps**:

- [ ] **4.1** Log entry models (`logging/models.py`):
  - Pydantic models for `LogEntry`: all fields matching `ProxyRequest` DB model
  - Factory method `LogEntry.from_proxy_context(request, response, timing, model_info)`
- [ ] **4.2** API key masking (`logging/masking.py`):
  - Mask API keys in headers before logging: `sk-abc...xyz` → `sk-***xyz`
  - Recursively scan JSONB for any field matching `*key*`, `*token*`, `*secret*` patterns and mask
  - Unit-testable pure function
- [ ] **4.3** Async logging service (`logging/service.py`):
  - `LoggingService` receives `LogEntry` objects via asyncio.Queue
  - Background task consumes queue and batch-inserts to PostgreSQL
  - Batch size + flush interval configurable
  - Backpressure: if queue is full, log a warning but do NOT block the proxy response
  - Graceful shutdown: flush remaining entries on app shutdown
  - For streaming: accumulate chunks in memory during stream, submit complete entry after stream ends
- [ ] **4.4** Integrate logging into proxy pipeline:
  - In `api/proxy/router.py`: capture request context before forwarding
  - After response received (or stream completed), construct `LogEntry` and enqueue
  - Timing: record `start_time` before adapter call, `end_time` after
  - Token counts: extract from response if present (`usage` field)
  - Cost: extract from response if present (OpenRouter includes cost)
- [ ] **4.5** Provider debug log endpoint:
  - `POST /v1/debug-logs/{provider}` — receives debug log payloads from providers
  - Links to `ProxyRequest` via request ID or correlation header
  - Stores in `ProviderDebugLog` table
  - Architecture hook: any provider can push debug data here
- [ ] **4.6** Log rotation / cleanup:
  - Background task (configurable via `log_retention_days` setting)
  - Deletes records older than TTL
  - Runs on app startup and then periodically (configurable interval)

**Verification**:
- [ ] Unit tests: `LogEntry.from_proxy_context()` produces correct model from various inputs (streaming, non-streaming, error cases)
- [ ] Unit tests: masking correctly handles nested keys, edge cases (empty string, None, already masked)
- [ ] Integration test: send proxy request → verify record appears in PostgreSQL with all fields
- [ ] Integration test: streaming request → verify `response_body` contains assembled full response AND `stream_chunks` contains individual chunks
- [ ] Integration test: logging failure does NOT affect proxy response (inject DB error → client still gets provider response)
- [ ] Integration test: debug log endpoint stores payload and links to request
- [ ] Integration test: TTL cleanup removes old records, keeps new ones
- [ ] Load test: 100 concurrent requests → all logged correctly, no data loss, proxy latency increase < 5ms

---

## Phase 5: Backend API for UI

**Goal**: Complete REST API serving the frontend with paginated logs, grouping, filtering, search, chat reconstruction, diagnostics, and export. Separate from the proxy endpoints.

**Steps**:

- [ ] **5.1** UI authentication (`security/auth.py`):
  - Separate auth for UI access (not the same as proxy API keys)
  - Simple bearer token or basic auth (configurable)
  - UI API key configured in settings
- [ ] **5.2** Request browsing API (`api/ui/requests.py`):
  - `GET /ui/v1/requests` — cursor-based pagination
    - Filters: `since`, `until`, `model`, `client_hash`, `status_code`, `provider`
    - Sort: by timestamp (desc by default)
    - Returns: lightweight list (id, timestamp, model, status, latency, tokens, cost — no full bodies)
  - `GET /ui/v1/requests/{id}` — full request detail (headers, body, response, chunks, metadata)
  - `GET /ui/v1/requests/{id}/diff/{other_id}` — compare two requests, return structured diff of request bodies
- [ ] **5.3** Search API:
  - `GET /ui/v1/search?q=...` — full-text search across request/response content using PostgreSQL tsvector
  - Returns matching requests with highlighted snippets
- [ ] **5.4** Grouping API (`api/ui/chats.py`):
  - `GET /ui/v1/conversations` — list grouped conversations
    - Group by: `system_prompt`, `client`, `model`, `session_id`, `custom_field` (configurable)
    - Grouping rules from config: define which fields/patterns constitute a "conversation"
    - Returns: conversation summaries (first message preview, message count, time range, models used)
  - `GET /ui/v1/conversations/{id}/messages` — full message list within a conversation, ordered chronologically
- [ ] **5.5** Chat reconstruction service (`services/chat_reconstruction.py`):
  - Algorithm: given a set of requests belonging to a conversation:
    1. Sort by timestamp
    2. For each request, extract message array from `request_body.messages`
    3. Detect "resends": if request N contains the same messages as request N-1 plus one new message → continuation
    4. Detect "forks": if request N diverges from request N-1 at some point → fork
    5. Build a tree/timeline of the conversation with fork points marked
  - Handles: missing messages, reasoning tokens, cache status per message
  - Returns structured conversation graph (linear with fork annotations)
- [ ] **5.6** Diagnostics service (`services/diagnostics.py`):
  - Cache issue detection:
    - Compare consecutive requests in a conversation
    - Flag if: reasoning tokens missing from resent messages, message modified mid-history, message order changed
    - Return list of `DiagnosticIssue(type, severity, description, request_id, message_index)`
  - Runs on demand via API: `GET /ui/v1/conversations/{id}/diagnostics`
- [ ] **5.7** Export API (`api/ui/export.py`):
  - `GET /ui/v1/export/requests/{id}` — single request as JSON
  - `GET /ui/v1/export/conversations/{id}` — full conversation as JSON/Markdown
  - Content-Type negotiation or `?format=json|markdown` parameter
- [ ] **5.8** Aggregation endpoints:
  - `GET /ui/v1/stats` — dashboard data: request count, avg latency, token spend by model, error rates
  - Time bucketing for trend graphs

**Verification**:
- [ ] Integration tests for every endpoint with real PostgreSQL (seed test data, verify responses)
- [ ] Pagination test: seed 1000 requests, paginate through all, verify no duplicates/gaps
- [ ] Grouping test: seed requests with known system prompts → verify correct conversation grouping
- [ ] Chat reconstruction test: seed a conversation with forks → verify fork points detected correctly
- [ ] Diagnostics test: seed requests with missing reasoning tokens → verify diagnostic issues raised
- [ ] Diff test: two requests with known differences → verify diff output
- [ ] Search test: seed requests with specific text → query returns correct results
- [ ] Export test: verify JSON/Markdown output format
- [ ] Auth test: unauthenticated requests return 401

---

## Phase 6: Frontend — Request Browser & Detail View

**Goal**: Working web UI for browsing, filtering, and inspecting individual requests.

**Steps**:

- [ ] **6.1** API client layer (`api/`):
  - Typed TypeScript client matching backend endpoints
  - Uses TanStack Query for data fetching, caching, pagination
  - Auth token stored in localStorage (same pattern as v1)
- [ ] **6.2** Connection & auth page:
  - Base URL + API key input
  - Connection test on submit (hit `/ui/v1/health`)
  - Persist to localStorage
- [ ] **6.3** Request browser (`components/RequestBrowser/`):
  - Virtual scrolling table (TanStack Virtual) for large datasets — v1 pain point: UI not responsive with large lists
  - Columns: timestamp, model, status, latency, tokens, cost, cache status
  - Cursor-based infinite scroll (load more on scroll)
  - Filter bar: date range picker, model selector (populated from data), status code, client
- [ ] **6.4** Request detail view (`components/RequestDetail/`):
  - Structured card layout: request headers, request body, response headers, response body
  - Collapsible sections for large blocks (long message histories)
  - Toggle: "Pretty" (formatted JSON with syntax highlighting) vs "Raw" (original text)
  - Metadata sidebar: timing, tokens, cost, cache, model, provider
  - Link to "View in Chat" → navigates to chat view focused on this request's conversation
- [ ] **6.5** Universal JSON viewer (`components/JsonViewer/`):
  - Recursive tree renderer for any JSON structure
  - Syntax highlighting (use a lightweight library like `react-json-view-lite` or custom)
  - Collapsible nodes
  - Copy button per value/node
  - Handles very large objects (virtualize if > N nodes)
  - No hardcoded field assumptions — renders any shape
- [ ] **6.6** Theming and layout:
  - Dark mode (primary), light mode toggle
  - Responsive layout
  - Use a lightweight component library (e.g., Radix UI primitives) or CSS modules

**Verification**:
- [ ] Vitest unit tests for API client, JSON viewer tree logic, filter state management
- [ ] Playwright E2E:
  - Login flow → see request list → click request → see detail
  - Filter by model → list updates correctly
  - Scroll through 500+ items → no UI jank (virtual scrolling works)
  - Toggle pretty/raw → both render correctly
  - JSON viewer: expand/collapse nodes, copy value
- [ ] Visual regression: screenshots of key views (optional but valuable)

---

## Phase 7: Frontend — Chat View & Diagnostics

**Goal**: Chat-style conversation view with fork detection, metadata per message, and diagnostic indicators.

**Steps**:

- [ ] **7.1** Conversation list (`components/ChatView/ConversationList`):
  - Grouped list of conversations (by system prompt, client, or configurable field)
  - Preview: first message snippet, message count, time span, models used
  - Filtering and search
- [ ] **7.2** Chat timeline view (`components/ChatView/ChatTimeline`):
  - Messages rendered in chat bubble format (user on right, assistant on left, system at top)
  - Each message shows:
    - Content (markdown rendered)
    - Metadata badge row: tokens used, cost, cache hit/miss, reasoning tokens, response time, model
  - Fork visualization: when conversation branches, show branch point with indicator and ability to switch branches
  - "Resend" indicators: mark when the same history was sent multiple times (e.g., "History resent 3 times before this response")
- [ ] **7.3** Request-level metadata drawer:
  - Click any message → slide-out drawer showing full request/response detail
  - Quick navigation: "Previous request" / "Next request" buttons
- [ ] **7.4** Diagnostic overlay (`components/Diagnostics/`):
  - Warning icons on messages with detected issues
  - Issue types: missing reasoning tokens, modified history, cache break, order mismatch
  - Click warning → detailed explanation panel
  - Conversation-level diagnostic summary banner at top
- [ ] **7.5** Request diff view (`components/Diagnostics/DiffView`):
  - Side-by-side comparison of two consecutive requests
  - Highlighted added/removed/changed messages and fields
  - Uses a diff library (e.g., `diff` npm package)
  - Accessible from chat timeline: "Compare with previous" button

**Verification**:
- [ ] Vitest: chat message rendering, fork detection UI logic, metadata badge rendering
- [ ] Playwright E2E:
  - Navigate to conversations → select one → see chat timeline
  - Verify messages appear in correct order with user/assistant attribution
  - Fork point visible and switchable
  - Diagnostic warnings appear on seeded problematic conversations
  - Diff view shows correct differences between two requests
- [ ] Performance test: render conversation with 200+ messages → UI remains responsive

---

## Phase 8: Production Readiness & Polish

**Goal**: Security hardening, documentation, production Docker Compose, comprehensive E2E validation.

**Steps**:

- [ ] **8.1** Security hardening:
  - CORS configuration (configurable allowed origins)
  - Rate limiting on proxy endpoints (optional, configurable)
  - Ensure API keys never appear in logs (verify masking coverage)
  - Optional: encrypt sensitive fields in DB (API key hash is not reversible, but request bodies may contain sensitive data)
  - CSP headers for frontend
  - Secrets management: provider API keys read from environment/secrets, not stored in YAML
- [ ] **8.2** Production Docker Compose:
  - Traefik with HTTPS (Let's Encrypt), same pattern as v1
  - PostgreSQL with persistent volume, backup configuration
  - Resource limits per container
  - Health checks for all services
  - `.env.example` with all required variables documented
- [ ] **8.3** Configuration documentation:
  - `config.example.yml` with comprehensive comments explaining every section
  - README.md: architecture overview, quickstart, configuration reference, development guide
  - API documentation: auto-generated from FastAPI OpenAPI spec
- [ ] **8.4** Error handling & resilience:
  - Graceful shutdown: flush logs, close DB connections, complete in-flight streams
  - Provider unavailable: return clear error to client, log event, trigger fallback if configured
  - DB unavailable: proxy continues working (logging to fallback file or stderr), alerts in logs
  - Connection interruption: client disconnect → cancel upstream request; provider disconnect → error response to client
- [ ] **8.5** Final test coverage audit:
  - Run `make coverage` — target ≥ 95% on backend
  - Identify untested paths, add missing tests
  - Frontend coverage audit (Vitest)
- [ ] **8.6** End-to-end validation:
  - Full docker compose up from scratch
  - Send real requests through proxy (multiple models, streaming + non-streaming)
  - Verify logs appear in UI
  - Navigate chat view, verify conversation reconstruction
  - Verify diagnostics on intentionally broken requests
  - Test model mapping, access control, request modification
  - Test config hot-reload
  - Test log export

**Verification**:
- [ ] Security checklist: no plain API keys in logs (grep full DB dump), CORS configured, auth required on UI
- [ ] E2E smoke test: fresh docker compose up → configure → send 10 requests → browse in UI → view chat → export
- [ ] Resilience test: kill PostgreSQL mid-request → proxy still responds → restart DB → logs resume
- [ ] Resilience test: kill provider mid-stream → client gets error event → logged correctly
- [ ] Load test: 50 concurrent streaming requests → all proxied, all logged, < 10ms added latency
- [ ] Pre-commit hooks pass on all files
- [ ] Coverage ≥ 95%

---

## V1 Codebase References

| V1 File | What to Reuse | What to Fix |
|---------|---------------|-------------|
| `ai_proxy/api/v1/chat_completions.py` | SSE streaming pattern (`log_and_stream()` async generator) | — |
| `ai_proxy/adapters/base.py` | Abstract adapter pattern | Use typed DTOs instead of `Dict[str, Any]` |
| `ai_proxy/core/routing.py` | `fnmatch` wildcard model matching | Add typed return, fallback chain |
| `ai_proxy/core/config.py` | YAML loading pattern | Use Pydantic Settings with validation |
| `ai_proxy/security/auth.py` | Auth flow | Use SHA-256 instead of `hash()` |
| `ai_proxy/logdb/schema.py` | Index design | Upgrade to PostgreSQL + SQLAlchemy |
| `docker-compose.yml` | Traefik + multi-service pattern | Add PostgreSQL, merge into single backend |
| `config.yml` | Model mapping format | Extend with providers, access rules, modifications |

## Key Decisions

- **Single backend service**: proxy + UI API as two FastAPI routers in one process (simpler than v1's two services)
- **No LiteLLM in v2.0**: OpenAI-compatible only; added later when multi-format needed (avoids heavy dependency)
- **Background async logging via queue**: non-blocking, prevents logging-blocks-proxy
- **PostgreSQL over SQLite**: eliminates v1's dual storage pain point, JSONB + FTS built-in
- **Ruff over black+isort+flake8**: single tool, faster, same results

## Scope Boundaries

**Included (v2.0)**: OpenAI Chat Completions v1 proxy (stream+non-stream), multi-provider routing, model mapping, full logging to PG, web UI (browser + chat + diagnostics + export), access control, request modification, cache issue detection, Docker Compose deployment.

**Deferred**: multi-format transformation (v2.1, LiteLLM), metrics dashboard (v2.1), alerting (v2.2), request replay (v2.1), multi-tenancy (v2.2), Prometheus/Grafana (v2.2), provider debug log UI (v2.1).
