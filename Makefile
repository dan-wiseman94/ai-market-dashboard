.DEFAULT_GOAL := help
SHELL := /bin/bash
COMPOSE := docker compose

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-18s\033[0m %s\n", $$1, $$2}'

.PHONY: dev
dev: ## Start dev stack with hot reload (and storybook)
	$(COMPOSE) --profile dev up --watch

.PHONY: up
up: ## Start stack detached
	$(COMPOSE) --profile dev up -d

.PHONY: down
down: ## Stop and remove containers
	$(COMPOSE) down

.PHONY: build
build: ## Build images
	$(COMPOSE) build

.PHONY: shell
shell: ## Bash in web container
	$(COMPOSE) exec web bash

.PHONY: migrate
migrate: ## Run Django migrations
	$(COMPOSE) exec web uv run python manage.py migrate

.PHONY: makemigrations
makemigrations: ## Create Django migrations
	$(COMPOSE) exec web uv run python manage.py makemigrations

.PHONY: check-migrations
check-migrations: ## Fail if models changed without a migration
	$(COMPOSE) exec web uv run python manage.py makemigrations --check --dry-run

.PHONY: schema
schema: ## Regenerate backend/schema.yml (OpenAPI) from the DRF views
	$(COMPOSE) exec -w /app/backend web uv run python manage.py spectacular --file schema.yml --validate

.PHONY: test
test: test-backend test-frontend ## Run all tests

.PHONY: test-backend
test-backend: ## Run backend tests
	$(COMPOSE) exec web uv run pytest

.PHONY: test-frontend
test-frontend: ## Run frontend tests
	$(COMPOSE) exec frontend pnpm test --run

.PHONY: test-cov
test-cov: ## Run frontend tests with v8 coverage
	$(COMPOSE) exec frontend pnpm run test:cov

.PHONY: storybook
storybook: ## Start just the Storybook service on :6006 (make dev already starts it)
	$(COMPOSE) --profile dev up storybook

.PHONY: test-storybook
test-storybook: ## Run Storybook stories as browser tests (needs chromium in the frontend image)
	$(COMPOSE) exec frontend pnpm exec vitest --project storybook run

.PHONY: fmt
fmt: ## Format backend (ruff) + frontend (prettier via eslint)
	$(COMPOSE) exec -w /app web uv run ruff format .
	$(COMPOSE) exec -w /app web uv run ruff check --fix .

.PHONY: lint
lint: lint-backend lint-imports typecheck lint-frontend ## Lint everything

.PHONY: lint-backend
lint-backend: ## ruff + ty (ruff scans repo root incl. e2e/, like CI)
	$(COMPOSE) exec -w /app web uv run ruff check .
	$(COMPOSE) exec -w /app web uv run ruff format --check .
	$(COMPOSE) exec web uv run ty check .

.PHONY: lint-imports
lint-imports: ## Enforce architecture import contracts (import-linter)
	# Runs from /app (where pyproject lives); PYTHONPATH=/app/backend keeps `apps` importable.
	$(COMPOSE) exec -w /app web uv run lint-imports

.PHONY: mutate
mutate: ## Mutation-test the money paths (slow; nightly in CI). Surviving mutants = weak tests.
	# Runs from /app (where [tool.mutmut] lives). `run` exits non-zero on survivors — that's
	# informational here, so `results` always prints the summary.
	$(COMPOSE) exec -w /app web sh -c 'uv run mutmut run || true; uv run mutmut results'

.PHONY: typecheck
typecheck: ## ORM-aware mypy, gated against mypy-baseline.txt (fails on NEW errors only)
	# sh pipe (no pipefail): mypy always exits non-zero on baselined errors, so the
	# filter's exit governs. New (unbaselined) errors make mypy-baseline filter exit 1.
	$(COMPOSE) exec -w /app web sh -c 'uv run mypy backend/apps backend/config | uv run mypy-baseline filter'

.PHONY: lint-frontend
lint-frontend: ## eslint + tsc
	$(COMPOSE) exec frontend pnpm run lint

.PHONY: check
check: lint test ## What CI runs

.PHONY: logs
logs: ## Tail logs: make logs s=worker
	$(COMPOSE) logs -f $(or $(s),)

.PHONY: prod
prod: ## Start prod stack (frontend baked into web)
	$(COMPOSE) -f compose.yaml -f compose.prod.yaml up

.PHONY: reload-workers
reload-workers: ## Restart worker + beat to pick up new tasks / beat schedule
	$(COMPOSE) restart worker beat

.PHONY: restore
restore: ## Restore DB from /data/backups/<file>. Usage: make restore file=2026-04-18.sql.gz
	@test -n "$(file)" || (echo "usage: make restore file=<name>" >&2; exit 1)
	@$(COMPOSE) exec web test -f /data/backups/$(file) || (echo "not found: /data/backups/$(file)" >&2; exit 1)
	$(COMPOSE) stop beat worker
	$(COMPOSE) exec web sh -c 'pg_restore --clean --if-exists -h $$PGHOST -U $$PGUSER -d $$PGDATABASE /data/backups/$(file)'
	$(COMPOSE) start beat worker

# E2E lanes — UI / visual / a11y / perf run in `worker` (carries chromium playwright).
# API / WS run in `web` (no browser needed). Both use --workdir /app so pytest sees the
# repo-root layout, not /app/backend.
# E2E runs use a DEDICATED compose project so an e2e stack never recreates the dev
# stack's shared `web`/`worker`/`beat` containers (which would flip them into
# MOCK_EXTERNAL=true and serve "Mocked response" in the dev UI) or share its redis.
# Two layers of isolation, both pointing away from the dev `ai-dashboard` project:
#   1. compose.e2e.yaml sets `name: ai-dashboard-e2e`, so even a raw
#      `docker compose -f compose.yaml -f compose.e2e.yaml ...` (or CI) is isolated.
#   2. The `-p <checkout>-e2e` below (flag beats file `name:`) gives each git
#      worktree its own project, so two checkouts can run e2e simultaneously.
# compose.e2e.yaml also drops host port bindings (`ports: !reset []`) so the e2e
# stack can run alongside `make dev` without 5432/6379/5173 conflicts; tests reach
# services over the compose network via exec. Override: `make e2e E2E_PROJECT=foo`.
E2E_PROJECT ?= $(notdir $(CURDIR))-e2e
E2E_COMPOSE = $(COMPOSE) -p $(E2E_PROJECT) -f compose.yaml -f compose.e2e.yaml
E2E_RUN = $(E2E_COMPOSE) exec -T --workdir /app
E2E_UI_LANES = e2e/ui/ e2e/visual/ e2e/a11y/
E2E_TXT_LANES = e2e/api/ e2e/ws/

.PHONY: e2e
e2e: ## Run all E2E lanes sequentially
	$(E2E_COMPOSE) up -d
	$(E2E_RUN) web uv run pytest $(E2E_TXT_LANES) -n 2 -m integration -v
	$(E2E_RUN) worker uv run pytest $(E2E_UI_LANES) -n 2 --dist=loadscope -m integration -v
	$(E2E_COMPOSE) down

.PHONY: e2e-one
e2e-one: ## Run a single test by path. Usage: make e2e-one t=ui/test_dashboard.py
	@case "$(t)" in \
		ui/*|visual/*|a11y/*|perf/*) $(E2E_RUN) worker uv run pytest e2e/$(t) -m integration -v ;; \
		api/*|ws/*) $(E2E_RUN) web uv run pytest e2e/$(t) -m integration -v ;; \
		*) $(E2E_RUN) web uv run pytest e2e/$(t) -m integration -v ;; \
	esac

.PHONY: e2e-up
e2e-up: ## Bring e2e stack up with overlay, leave running
	$(E2E_COMPOSE) up -d

.PHONY: e2e-down
e2e-down: ## Tear down e2e stack
	$(E2E_COMPOSE) down

.PHONY: e2e-ui
e2e-ui: ## E2E UI lane (Playwright journeys)
	$(E2E_COMPOSE) up -d
	$(E2E_RUN) worker uv run pytest e2e/ui/ -n 2 --dist=loadscope -m integration -v

.PHONY: e2e-api
e2e-api: ## E2E API lane (httpx contract)
	$(E2E_COMPOSE) up -d
	$(E2E_RUN) web uv run pytest e2e/api/ -n 2 -m integration -v

.PHONY: e2e-schemathesis
e2e-schemathesis: ## Fuzz every endpoint for 5xx crashes (schemathesis, under MOCK_EXTERNAL)
	$(E2E_COMPOSE) up -d
	$(E2E_RUN) web sh -c 'uv run schemathesis run http://localhost:8000/api/schema/ -u http://localhost:8000 -c not_a_server_error -n 6'

.PHONY: e2e-ws
e2e-ws: ## E2E WebSocket lane
	$(E2E_COMPOSE) up -d
	$(E2E_RUN) web uv run pytest e2e/ws/ -n 2 -m integration -v

.PHONY: e2e-visual
e2e-visual: ## E2E visual regression lane
	$(E2E_COMPOSE) up -d
	$(E2E_RUN) worker uv run pytest e2e/visual/ -n 2 -m integration -v

.PHONY: e2e-visual-update
e2e-visual-update: ## Regenerate visual baselines
	$(E2E_COMPOSE) up -d
	# helpers/visual.capture_or_compare creates a baseline if the file is missing.
	# Wipe via the container — baselines are owned by root inside the worker.
	$(E2E_RUN) worker rm -rf /app/e2e/visual/__screenshots__
	$(E2E_RUN) worker uv run pytest e2e/visual/ -n 2 -m integration -v
	@echo "Inspect diffs: git diff e2e/visual/__screenshots__/"

.PHONY: e2e-a11y
e2e-a11y: ## E2E accessibility lane
	$(E2E_COMPOSE) up -d
	$(E2E_RUN) worker uv run pytest e2e/a11y/ -n 4 -m integration -v

.PHONY: e2e-perf
e2e-perf: ## E2E performance lane (runs prod overlay)
	# Perf runs the prod overlay (web on host:8000) on the DEFAULT project — prod
	# needs its host port, so it can't take the e2e ports-reset isolation. Don't run
	# this alongside `make dev`/`make prod` (it recreates the shared web container).
	$(COMPOSE) -f compose.yaml -f compose.prod.yaml up -d
	$(COMPOSE) -f compose.yaml -f compose.prod.yaml exec -T --workdir /app worker uv run pytest e2e/perf/ -m integration -v
