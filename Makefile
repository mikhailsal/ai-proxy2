.PHONY: help lint format test-unit test-integration test-all coverage up down up-dev down-dev migrate migrate-create frontend-install frontend-lint frontend-test

# ── Defaults ──────────────────────────────────────────────────────────
SHELL := /bin/bash
BACKEND_DIR := backend
FRONTEND_DIR := frontend

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Backend ───────────────────────────────────────────────────────────
lint: ## Run ruff linter + mypy on backend
	cd $(BACKEND_DIR) && python -m ruff check .
	cd $(BACKEND_DIR) && python -m mypy ai_proxy/

format: ## Format backend code with ruff
	cd $(BACKEND_DIR) && python -m ruff format .
	cd $(BACKEND_DIR) && python -m ruff check --fix .

test-unit: ## Run backend unit tests
	cd $(BACKEND_DIR) && python -m pytest tests/unit/ -v

test-integration: ## Run backend integration tests
	cd $(BACKEND_DIR) && python -m pytest tests/integration/ -v

test-all: ## Run all backend tests
	cd $(BACKEND_DIR) && python -m pytest tests/ -v

coverage: ## Run backend tests with coverage
	cd $(BACKEND_DIR) && python -m pytest tests/ --cov=ai_proxy --cov-report=term-missing --cov-report=html

# ── Frontend ──────────────────────────────────────────────────────────
frontend-install: ## Install frontend dependencies
	cd $(FRONTEND_DIR) && npm ci

frontend-lint: ## Lint frontend
	cd $(FRONTEND_DIR) && npx eslint .

frontend-test: ## Run frontend tests
	cd $(FRONTEND_DIR) && npx vitest run

frontend-build: ## Build frontend for production
	cd $(FRONTEND_DIR) && npm run build

# ── Database ──────────────────────────────────────────────────────────
migrate: ## Apply database migrations
	docker compose run --rm backend python -m alembic upgrade head

migrate-rollback: ## Rollback last migration
	docker compose run --rm backend python -m alembic downgrade -1

migrate-create: ## Create a new migration (usage: make migrate-create msg="description")
	cd $(BACKEND_DIR) && python -m alembic revision --autogenerate -m "$(msg)"

# ── Docker ────────────────────────────────────────────────────────────
up: ## Start production stack
	docker compose up -d --build

down: ## Stop production stack
	docker compose down

up-dev: ## Start development stack (hot-reload backend, no Traefik)
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build

down-dev: ## Stop development stack
	docker compose -f docker-compose.yml -f docker-compose.dev.yml down

logs: ## Tail all container logs
	docker compose logs -f

logs-backend: ## Tail backend logs
	docker compose logs -f backend
