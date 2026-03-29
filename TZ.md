# Technical Specification: AI Proxy v2

## 1. Project Overview

### 1.1. Purpose

AI Proxy v2 is a proxy server positioned between client applications and AI model providers. Its main goals are:

- Transparent proxying of requests to AI providers with streaming support
- Detailed logging of all requests and responses without data loss
- Convenient visualization of interaction history in chat format
- Detection and diagnostics of data exchange issues between client and provider
- Flexible request modification and routing

### 1.2. Target Audience

Developers of AI applications who need to:

- Debug client interactions with AI providers
- See what the client actually sends and what the provider actually returns
- Track caching issues, incomplete history, and data loss
- Control model access and route requests

### 1.3. Differences from the Previous Version (v1)

- Log storage in a database instead of text files
- Greenfield design based on accumulated experience
- Focus on OpenAI-compatible protocols as the primary format
- Higher requirements for code quality and test coverage

---

## 2. Functional Requirements

### 2.1. Request Proxying

#### 2.1.1. Basic Proxying

- Transparent forwarding of requests from client to provider and back
- Full streaming support (Server-Sent Events)
- Preservation of all headers, metadata, and structure of original requests/responses
- Support for all standard HTTP methods

#### 2.1.2. Routing Between Providers

- Support for **multiple providers simultaneously**: each provider is configured separately (endpoint, API key, provider-specific settings)
- Automatic routing of requests to the required provider based on the requested model
- The client works through a single entry point (the proxy) and **does not know** which specific provider receives the request
- Configurable mapping table: model -> provider
- Support for fallback providers (if the primary is unavailable, route to a backup)

#### 2.1.3. Protocol Support

- **First priority:** OpenAI Chat Completions API (v1) with full compatibility
- **Second priority (future):** Transformation between provider formats:
  - OpenAI v1 <-> OpenAI v2
  - OpenAI <-> Anthropic
  - Other providers
- Consider using existing libraries (e.g., LiteLLM) for format transformation instead of building custom implementations

#### 2.1.4. Request Modification

- Ability to automatically enrich requests with missing fields depending on the target provider (for example, provider-specific fields for OpenRouter)
- Modification of request parts based on configurable rules
- Insertion/removal/replacement of headers and request body fields

### 2.2. Model Management

#### 2.2.1. Model Mapping

- Ability to define aliases: the client requests model A, while the actual request is sent to model B
- Configurable mapping table
- Support for mapping both specific models and patterns

#### 2.2.2. Model Access Restrictions

- Allowlist and/or blocklist of available models
- Ability to scope restrictions by clients/API keys

### 2.3. Logging

#### 2.3.1. Logging Completeness

- Recording the **full** contents of every request and response, including:
  - Request body (all fields without exceptions)
  - Response body (including stream chunks assembled into the full response)
  - Request and response headers
  - Metadata: timestamps, latency, response codes
- Preservation of original ("native") data: nothing should be lost or modified during logging
- Logging of streaming responses: store both individual chunks and the assembled final result

#### 2.3.2. Log Storage

- Storage in a database (the specific DBMS is chosen during architecture design)
- Ability to export logs in text/JSON formats for external tools
- Log rotation and cleanup policies (configurable TTL)

#### 2.3.3. Provider Debug Logs

- Support for receiving provider debug logs on dedicated endpoints (for example, OpenRouter debug logs)
- Linking provider debug logs to corresponding requests in the system
- Architecture should account for this capability from the very beginning

### 2.4. Visualization and Interface

#### 2.4.1. Request-Response View

- Convenient presentation of individual requests and responses as structured cards
- Even for very large requests (with long message history), the interface must remain responsive and performant
- Clean, readable rendering: JSON syntax highlighting, collapsible sections for large blocks, visual separation of headers and body
- Ability to quickly navigate from an individual request to the full chat history in which it was sent
- Pagination or virtual scrolling for request lists

#### 2.4.2. Chat View Mode

- Display interaction history as a full chat, not just a list of separate requests
- Automatic reconstruction of dialogue flow:
  - Detect how many times the same history was resent
  - Track "forks" - moments when the user deleted the last message and sent a new one
  - Visualize dialogue branching
- Metadata must be visible for each message:
  - Request cost (tokens/cost)
  - Cache status (cache hit/miss)
  - Reasoning tokens (if applicable)
  - Response time
  - Model used
  - Any other fields present in the response

#### 2.4.3. Data Parsing and Rendering

- Automatic JSON parsing into a readable format
- **Universality:** the interface must not depend on a fixed set of fields; any request/response field should be rendered correctly
- Flexible display: ability to switch between "pretty" and "raw" viewing modes

#### 2.4.4. Grouping and Filtering

- Group requests by:
  - Client (name/identifier)
  - Model used
  - System prompt or first message
  - Session ID (if provided)
  - Arbitrary fields from request/response
- Configurable grouping rules for cases where standard identifiers (session ID) are absent
- Filtering by time range, model, client, response status
- Full-text search across request and response contents

### 2.5. Problem Diagnostics

#### 2.5.1. Caching Issue Detection

- Automatic detection of cases where the client sends incomplete history, resulting in provider cache breakage:
  - Missing reasoning tokens
  - Modified messages in the middle of the history
  - Message order mismatch compared to previous requests
- Visual indication of detected issues

#### 2.5.2. Request Comparison

- Ability to compare two consecutive requests within the same chat and view the diff
- Highlighting of changes between iterations

---

## 3. Non-Functional Requirements

### 3.1. Code Quality

- Maximum file size: **500 lines**
- Function length limit (exact value is determined during design)
- Unit test coverage: **at least 95%**
- Presence of functional (integration) tests
- Configured pre-commit hooks
- Mandatory use of linters and formatters

### 3.2. Performance

- Minimal additional latency during proxying (the proxy should be speed-transparent)
- Efficient streaming handling: do not buffer the entire response before sending to the client
- Logging must not block the main proxying flow

### 3.3. Reliability

- Logging or interface errors must not affect core proxying functionality
- Graceful handling when provider is unavailable
- Correct handling of connection interruptions (both client-side and provider-side)

### 3.4. Configurability

- All settings (model mapping, request modification, grouping rules, restrictions) must be configurable without code changes
- Configuration format must be human-readable (YAML/TOML)

### 3.5. Security

- Do not log API keys in plain text (masking required)
- Support authorization for access to the log viewing interface
- Optional encryption of sensitive data in logs

---

## 4. Additional Capabilities (Suggestions)

> Additional ideas that may increase project value. Subject to discussion.

### 4.1. Metrics and Analytics

- Dashboard with aggregated statistics: number of requests, average latency, token/cost spend by models and clients
- Tracking usage trends over time

### 4.2. Alerting

- Notifications when anomalies are detected: sharp error increase, unusually expensive requests, caching issues
- Configurable thresholds and notification channels (webhook, email)

### 4.3. Request Replay

- Ability to resend a saved request to the provider (replay) for debugging
- Ability to modify the request before resending

### 4.4. Multi-Tenancy

- Support for multiple independent users/projects with data isolation
- Separate model mapping and restriction configurations for each tenant

### 4.5. Integration API

- REST API for programmatic access to logs and metrics
- Webhooks for specific events (error, issue detected)

### 4.6. Export and Integration

- Export conversations to formats: JSON, Markdown, HTML
- Ability to integrate with external monitoring systems (Grafana, Prometheus)

---

## 5. Constraints and Assumptions

- The first implementation supports only the OpenAI-compatible protocol (Chat Completions API v1)
- Support for other provider formats is planned in subsequent iterations
- The previous version (v1) can be used as a source of insights, but not as a codebase foundation
- Specific technical decisions (programming language, DBMS, frameworks) are made during architecture design

---

## 6. Acceptance Criteria

- The proxy correctly proxies OpenAI-compatible requests with streaming support
- All requests and responses are fully stored in the database without data loss
- The interface displays history in chat format with metadata
- Grouping and filtering work by major criteria
- Caching issues are detected (missing fields, history modification)
- Model mapping and access restrictions work according to configuration
- Test coverage is at least 95%
- Linters and pre-commit hooks are configured and pass without errors
