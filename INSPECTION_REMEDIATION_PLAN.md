# Prioritized Remediation Plan

This document converts the implementation inspection into a concrete repair sequence. The ordering is based on delivery risk, plan compliance, and how many later phases depend on each fix.

## Priority 0: Restore Baseline Correctness

These items block reliable development and invalidate core Phase 1 to Phase 3 expectations.

### 1. Decouple app startup from a live database

Problem:
- App lifespan currently initializes the engine and immediately runs `Base.metadata.create_all`, which makes startup depend on a correctly configured PostgreSQL instance.
- The current backend test suite fails because of that dependency.

Actions:
- Remove schema creation from application startup.
- Make startup initialize shared services only.
- Keep schema management exclusively in Alembic migrations.
- Update tests so app construction and lifespan can run without a live production database.

Acceptance criteria:
- `backend/tests/unit/test_app.py` passes without requiring external PostgreSQL credentials.
- App startup no longer mutates schema automatically.
- Database creation and migration happen only through migration commands.

### 2. Preserve upstream HTTP semantics in the proxy

Problem:
- The adapter raises on all upstream non-2xx responses.
- The router turns those into synthetic 502 responses.
- Streaming failures are emitted after the response starts and still logged as HTTP 200.

Actions:
- Return upstream status code, headers, and error body transparently for non-streaming requests.
- Distinguish transport failures from provider HTTP failures.
- For streaming, propagate provider failures before response start when possible.
- If a streaming failure happens mid-stream, log the request as failed instead of always `200`.

Acceptance criteria:
- Provider `401`, `403`, `429`, and `5xx` responses reach clients unchanged except for explicit proxy-added framing.
- Transport failures still return proxy-generated `502` or `504` as appropriate.
- Logs record the actual final outcome for streaming and non-streaming requests.

### 3. Fix the UI auth handshake

Problem:
- The frontend connection test calls `/health`, which is public and does not validate the UI API key.

Actions:
- Add an authenticated UI health endpoint such as `/ui/v1/health`.
- Change the frontend connection test to use that endpoint.
- Show a clear auth error when the UI token is invalid.

Acceptance criteria:
- Invalid UI API keys fail at connection time.
- Valid UI API keys can reach all protected UI routes.

## Priority 1: Complete Missing Foundation Work From Phases 2 to 4

These items are the minimum required to make the current architecture match the plan instead of looking complete only at the directory level.

### 4. Implement real Alembic migrations

Problem:
- Migration commands exist in the Makefile, but Alembic configuration and revision history are missing.

Actions:
- Add `backend/alembic.ini`.
- Add async Alembic environment under the migrations directory.
- Create an initial schema migration for all current tables and indexes.
- Add rollback verification to CI or local verification steps.

Acceptance criteria:
- `make migrate` applies schema cleanly on a fresh PostgreSQL instance.
- `make migrate-rollback` reverts cleanly.
- No schema creation happens outside migrations.

### 5. Bring the database schema and repositories in line with the plan

Problem:
- Search is JSON text `ILIKE`, not PostgreSQL FTS.
- Cursor pagination is timestamp-only and not stable.
- The repository API is narrower than planned.
- Some planned schema features such as FTS-specific indexing are missing.

Actions:
- Add `tsvector`-backed search and GIN index support.
- Replace timestamp-only cursoring with a stable compound cursor such as `(timestamp, id)`.
- Add repository methods for grouped chat retrieval and conversation flow.
- Add tests against a real PostgreSQL database.

Acceptance criteria:
- Search returns expected matches using PostgreSQL FTS.
- Pagination has no duplicates or gaps across page boundaries.
- Repository coverage exists for filtering, search, grouping, and pagination.

### 6. Persist complete log records

Problem:
- Logging drops relational and detail fields needed by later phases.
- `provider_id` exists in the schema but is never resolved or stored.
- Proxy log entries omit request and response headers even though the UI detail view expects them.

Actions:
- Resolve provider name to `provider_id` during log persistence.
- Capture and persist masked request headers and response headers.
- Add a `LogEntry.from_proxy_context(...)` factory so proxy logging is consistent.
- Add failure-path tests proving logging errors do not break proxy responses.

Acceptance criteria:
- Stored requests contain the fields needed by request detail, export, and diagnostics views.
- Provider foreign keys are populated for routed requests.
- Logging failure is isolated from proxy response delivery.

### 7. Finish planned Phase 4 services

Problem:
- Provider debug-log ingestion and TTL cleanup tasks are missing.

Actions:
- Add `POST /v1/debug-logs/{provider}`.
- Link debug logs to proxy requests via correlation ID or request ID.
- Add retention cleanup as a background task with interval and TTL from config.

Acceptance criteria:
- Debug payloads can be stored and queried by request.
- Old log rows are cleaned up according to configuration.

## Priority 2: Fix Proxy Feature Gaps From Phase 3

### 8. Correct `/v1/models`

Problem:
- The endpoint returns mapping keys, including wildcard patterns, and does not apply access rules.

Actions:
- Expose only concrete client-visible models.
- Decide how wildcard-only configs should be represented.
- Filter returned models using the caller's access rules.

Acceptance criteria:
- Clients never see wildcard patterns such as `*` as model IDs.
- Blocked models are excluded from the result.

### 9. Add fallback routing and real config reload behavior

Problem:
- The plan requires fallback providers and hot-reloadable config.
- Current implementation only reloads on manual endpoint call and has no watcher or fallback chain.

Actions:
- Add typed fallback definitions in config.
- Retry transport failures through the configured fallback chain.
- Add file watching for config reload.
- Add tests for exact, wildcard, default, and fallback behavior.

Acceptance criteria:
- Primary transport failure can fall through to a backup provider.
- Config file changes are picked up without restarting the app.

### 10. Harden streaming behavior

Problem:
- Mid-stream failures are only partially handled.
- Client disconnect handling is not implemented.

Actions:
- Detect downstream disconnects and cancel upstream streaming work.
- Preserve original SSE framing while still assembling final content for logging.
- Add tests for disconnect and provider interruption cases.

Acceptance criteria:
- Client disconnects do not leak upstream work or crash the server.
- Streaming logs reflect completed versus failed streams accurately.

## Priority 3: Replace Placeholder Conversation Features With Real Phase 5 to 7 Behavior

### 11. Build actual conversation reconstruction

Problem:
- Current grouping uses `messages[0].content` and the frontend renders each request as an isolated transcript.
- Resends, forks, and continuation detection are not implemented.

Actions:
- Add backend services for grouping and chat reconstruction.
- Base grouping on configurable rules, not only the first message content.
- Detect resend and fork behavior from ordered message histories.
- Return structured conversation graphs to the frontend.

Acceptance criteria:
- Conversation timelines do not duplicate full history per request.
- Fork points and resent history are explicitly represented.
- Grouping matches configured rules and does not assume the first message is always a system prompt.

### 12. Implement diagnostics and diff features

Problem:
- Planned diagnostics endpoints, backend service logic, and frontend overlays are missing.

Actions:
- Add backend diagnostics service and endpoint.
- Add request diff endpoint.
- Add frontend diagnostics badges, summary banner, and diff view.

Acceptance criteria:
- Seeded broken histories produce deterministic diagnostic issues.
- Users can compare consecutive requests from the conversation view.

### 13. Finish UI browsing and detail capabilities

Problem:
- The current UI covers the basic shell but omits several planned behaviors.

Actions:
- Add richer filters for status, provider, date range, and client.
- Add pretty/raw toggle in request detail.
- Add navigation from request detail into the conversation view.
- Add conversation export.

Acceptance criteria:
- Request browser and detail match the Phase 5 and Phase 6 endpoint set.
- UI workflows align with the documented product behavior.

## Priority 4: Production Readiness and Documentation Cleanup

### 14. Align documentation with the real API

Problem:
- The README advertises Python 3.12 while the backend targets Python 3.10.
- The documented UI endpoints do not match the implemented route prefixes.

Actions:
- Decide whether the project truly targets Python 3.12, then update code and tooling or the docs consistently.
- Rewrite the endpoint table to match actual route paths.
- Add missing setup notes for migrations and UI auth.

Acceptance criteria:
- README matches actual runtime requirements and endpoint paths.
- New contributors can start the stack without following stale instructions.

### 15. Add real automated coverage for the implemented system

Problem:
- Backend tests cover only app wiring and health.
- Frontend tests are only an import smoke test.
- No integration or end-to-end suites exist for the highest-risk paths.

Actions:
- Backend: add unit and integration coverage for routing, access rules, modification rules, adapters, logging, repositories, UI auth, and UI endpoints.
- Frontend: add Vitest coverage for API client, request browser behavior, JSON viewer, and chat rendering logic.
- Add Playwright for the login, browse, inspect, and conversation flows.
- Use a real PostgreSQL test environment for repository and API integration tests.

Acceptance criteria:
- Backend tests cover all implemented core modules, not only app boot.
- Frontend tests validate user-visible behavior instead of importability only.
- The repository has at least one end-to-end path for authenticated UI and proxy behavior.

## Recommended Execution Order

1. Remove `create_all` from startup and land Alembic.
2. Fix proxy error propagation and logging correctness.
3. Add authenticated UI health and repair connection flow.
4. Upgrade repositories: stable pagination, PostgreSQL FTS, chat-oriented queries.
5. Complete logging persistence: headers, provider linkage, debug logs, retention.
6. Fix `/v1/models`, fallback routing, config watch reload, and streaming disconnect handling.
7. Implement conversation reconstruction, diagnostics, diff API, and matching frontend UI.
8. Rewrite docs and expand automated coverage until the phase verification criteria are credible.

## Suggested Delivery Slices

### Slice A: Unblock development
- Priority 0 items 1 to 3.

### Slice B: Make the backend trustworthy
- Priority 1 items 4 to 7.

### Slice C: Reach real Phase 3 parity
- Priority 2 items 8 to 10.

### Slice D: Reach real Phase 5 to 7 parity
- Priority 3 items 11 to 13.

### Slice E: Production hardening
- Priority 4 items 14 to 15.