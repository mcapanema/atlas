.DEFAULT_GOAL := help

.PHONY: help install hooks migrate dev test lint format typecheck security check build run clean \
	deps fetch-base docker-build docker-up docker-down docker-logs

# Base for diff coverage; CI passes the PR's base branch instead.
DIFF_COVER_BASE ?= origin/main

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-16s\033[0m %s\n", $$1, $$2}'

install: ## Install backend and frontend dependencies
	uv sync
	cd web && npm ci
	test -f .env || cp .env.example .env

hooks: ## Install pre-commit hooks (ruff, eslint, prettier) + blame-ignore for reformat commits
	uv run pre-commit install
	git config blame.ignoreRevsFile .git-blame-ignore-revs

migrate: ## Apply database migrations
	uv run alembic upgrade head

dev: ## Run backend + frontend dev servers together (Ctrl+C stops both)
	@trap 'kill 0' EXIT; \
	uv run uvicorn app.main:app --reload --port 8000 & \
	(cd web && npm run dev) & \
	wait

test: ## Run test suites (coverage floors + >=90% coverage of changed lines vs origin/main)
	uv run pytest --cov -v
	cd web && npm run test:coverage
	uv run diff-cover coverage.xml --compare-branch=$(DIFF_COVER_BASE) --fail-under=90
	uv run diff-cover web/coverage/cobertura-coverage.xml --compare-branch=$(DIFF_COVER_BASE) --fail-under=90

lint: ## Lint, format-check, and dead-code-check backend and frontend
	uv run ruff check .
	uv run ruff format --check .
	cd web && npm run lint && npm run format:check && npm run knip

format: ## Auto-format backend (ruff) and frontend (prettier)
	uv run ruff format .
	cd web && npm run format

typecheck: ## Type-check backend and frontend
	uv run mypy
	cd web && npm run typecheck

security: ## Audit backend and frontend dependencies for known vulnerabilities
	uv run --with pip-audit pip-audit
	cd web && npm audit --audit-level=high

check: deps fetch-base lint typecheck test build security docker-build ## Run the full CI gate locally: every ci.yml job (Docker must be running)

deps: web/node_modules/.package-lock.json ## Install exactly what the lockfiles pin, like CI (fails on a stale lockfile)
	uv sync --locked

# npm's own install marker. npm ci only re-runs when package.json or the
# lockfile changed since the last install, and it fails if the two disagree.
web/node_modules/.package-lock.json: web/package.json web/package-lock.json
	cd web && npm ci

fetch-base: # refresh the diff-coverage base so it measures only this branch's lines
	git fetch --quiet origin

build: ## Build the frontend for production (single-service mode)
	cd web && npm run build

run: build migrate ## Build the frontend and run the single-service production server
	uv run uvicorn app.main:app --host 0.0.0.0 --port 8000

clean: ## Remove build artifacts and caches
	rm -rf web/dist .pytest_cache .mypy_cache .ruff_cache atlas.db

docker-build: ## Build the Docker image
	docker compose build

docker-up: ## Start Atlas in Docker (build if needed)
	docker compose up --build

docker-down: ## Stop and remove Docker containers
	docker compose down

docker-logs: ## Tail Docker container logs
	docker compose logs -f
