.DEFAULT_GOAL := help
# Serial even under `make -j`: `deps` (npm ci wipes web/node_modules) must
# finish before lint/test use it. `dev` parallelizes with shell `&`, not -j.
.NOTPARALLEL:

.PHONY: help install hooks migrate dev test lint format typecheck security check build run clean \
	deps fetch-base pre-push docker-build docker-up docker-down docker-logs

# Base for diff coverage; CI passes the PR's base branch instead.
DIFF_COVER_BASE ?= origin/main

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-16s\033[0m %s\n", $$1, $$2}'

install: ## Install backend and frontend dependencies
	uv sync
	cd web && npm ci
	test -f .env || cp .env.example .env

hooks: ## Install git hooks: pre-commit (ruff, eslint, prettier) + pre-push (make check) + blame-ignore
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

deps: web/node_modules/.package-lock.json ## Sync deps to the lockfiles like CI (fails on a stale lockfile; warns on a Node mismatch)
	@# ponytail: warn, don't fail — no Node version manager is assumed. Upgrade
	@# path: fail here once everyone runs web/.nvmrc's major (nvm/fnm/volta).
	@want=$$(tr -d 'v \n' < web/.nvmrc | cut -d. -f1); have=$$(node -p 'process.versions.node.split(".")[0]'); \
	[ "$$have" = "$$want" ] || echo "warning: Node $$have here but CI uses Node $$want (web/.nvmrc); results can differ."
	uv sync --locked

# npm's own install marker. npm ci only re-runs when package.json or the
# lockfile changed since the last install, and it fails if the two disagree.
web/node_modules/.package-lock.json: web/package.json web/package-lock.json
	cd web && npm ci

fetch-base: # refresh the diff-coverage base so it measures only this branch's lines
	git fetch --quiet origin

pre-push: ## Full CI gate on exactly the commit being pushed (run by the pre-push hook)
	@# ^{commit} peels an annotated tag to the commit it points at.
	@if [ -n "$$PRE_COMMIT_TO_REF" ] && [ "$$(git rev-parse "$$PRE_COMMIT_TO_REF^{commit}")" != "$$(git rev-parse HEAD)" ]; then \
		echo "pre-push: pushing $$PRE_COMMIT_TO_REF but this checkout is at $$(git rev-parse HEAD)."; \
		echo "Push from the worktree that has the branch checked out, so the gate checks what you push."; \
		exit 1; \
	fi
	@git diff --quiet HEAD || { \
		echo "pre-push: uncommitted changes would be checked instead of the pushed commit; commit or stash them."; \
		exit 1; \
	}
	@test -z "$$(git ls-files --others --exclude-standard)" || { \
		echo "pre-push: untracked files would be checked but not pushed; add or remove them:"; \
		git ls-files --others --exclude-standard; \
		exit 1; \
	}
	$(MAKE) check

build: ## Build the frontend for production (single-service mode)
	cd web && npm run build

run: build migrate ## Build the frontend and run the single-service production server
	uv run uvicorn app.main:app --host 127.0.0.1 --port 8000

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
