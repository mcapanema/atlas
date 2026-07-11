.DEFAULT_GOAL := help

.PHONY: help install migrate dev test lint typecheck security check build run clean \
	docker-build docker-up docker-down docker-logs

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-16s\033[0m %s\n", $$1, $$2}'

install: ## Install backend and frontend dependencies
	uv sync
	cd web && npm install
	test -f .env || cp .env.example .env

migrate: ## Apply database migrations
	uv run alembic upgrade head

dev: ## Run backend + frontend dev servers together (Ctrl+C stops both)
	@trap 'kill 0' EXIT; \
	uv run uvicorn app.main:app --reload --port 8000 & \
	(cd web && npm run dev) & \
	wait

test: ## Run backend and frontend test suites (with coverage gates)
	uv run pytest --cov -v
	cd web && npm run test:coverage

lint: ## Lint backend and frontend
	uv run ruff check .
	cd web && npm run lint

typecheck: ## Type-check backend and frontend
	uv run mypy
	cd web && npm run typecheck

security: ## Audit backend and frontend dependencies for known vulnerabilities
	uv run --with pip-audit pip-audit
	cd web && npm audit --audit-level=high

check: lint typecheck test security ## Run the full CI gate locally

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
