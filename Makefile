.DEFAULT_GOAL := help
SHELL := /bin/bash
COMPOSE := docker compose

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-18s\033[0m %s\n", $$1, $$2}'

.PHONY: dev
dev: ## Start dev stack with hot reload
	$(COMPOSE) up --watch

.PHONY: up
up: ## Start stack detached
	$(COMPOSE) up -d

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
	$(COMPOSE) exec web python manage.py migrate

.PHONY: makemigrations
makemigrations: ## Create Django migrations
	$(COMPOSE) exec web python manage.py makemigrations

.PHONY: test
test: test-backend test-frontend ## Run all tests

.PHONY: test-backend
test-backend: ## Run backend tests
	$(COMPOSE) exec web pytest

.PHONY: test-frontend
test-frontend: ## Run frontend tests
	$(COMPOSE) exec frontend npm test -- --run

.PHONY: lint
lint: lint-backend lint-frontend ## Lint everything

.PHONY: lint-backend
lint-backend: ## ruff + mypy
	$(COMPOSE) exec web ruff check .
	$(COMPOSE) exec web mypy .

.PHONY: lint-frontend
lint-frontend: ## eslint + tsc
	$(COMPOSE) exec frontend npm run lint

.PHONY: check
check: lint test ## What CI runs

.PHONY: logs
logs: ## Tail logs: make logs s=worker
	$(COMPOSE) logs -f $(or $(s),)

.PHONY: prod
prod: ## Start prod stack (frontend baked into web)
	$(COMPOSE) -f compose.yaml -f compose.prod.yaml up

.PHONY: restore
restore: ## Restore DB from /data/backups/<file>. Usage: make restore file=2026-04-18.sql.gz
	@test -n "$(file)" || (echo "usage: make restore file=<name>" >&2; exit 1)
	@$(COMPOSE) exec web test -f /data/backups/$(file) || (echo "not found: /data/backups/$(file)" >&2; exit 1)
	$(COMPOSE) stop beat worker
	$(COMPOSE) exec web sh -c 'pg_restore --clean --if-exists -h $$PGHOST -U $$PGUSER -d $$PGDATABASE /data/backups/$(file)'
	$(COMPOSE) start beat worker
