# Koinoflow — Development Makefile
# Run `make help` to see available targets.

COMPOSE = docker compose -f infra/docker-compose.yml
BACKEND_EXEC = $(COMPOSE) exec backend
MANAGE = $(BACKEND_EXEC) python manage.py
FRONTEND_EXEC = $(COMPOSE) exec frontend

# ──────────────────────────────────────────────
# First-time setup
# ──────────────────────────────────────────────

.PHONY: install
install: ## Full first-time setup (env, build, migrate, superuser)
	@echo ""
	@echo "╔══════════════════════════════════════════╗"
	@echo "║       Koinoflow — first-time setup       ║"
	@echo "╚══════════════════════════════════════════╝"
	@echo ""
	@test -f .env || (cp .env.example .env && echo "✓ Created .env from .env.example")
	@test -f .env && echo "✓ .env exists"
	@rm -rf ~/.mcp-auth/ && echo "✓ Cleared MCP auth cache (~/.mcp-auth/)"
	@echo ""
	@echo "→ Building and starting containers..."
	$(COMPOSE) up -d --build
	@echo ""
	@echo "→ Waiting for database..."
	@$(COMPOSE) exec db sh -c 'until pg_isready -U koinoflow; do sleep 1; done' > /dev/null 2>&1
	@echo "✓ Database is ready"
	@echo ""
	@echo "→ Running migrations..."
	$(MANAGE) sync_squashed_migration_names
	$(MANAGE) migrate
	@echo ""
	@echo "→ Seeding default data..."
	$(MANAGE) seed_plans
	$(MANAGE) seed_feature_flags
	@echo ""
	@echo "→ Create your admin account (used to log in at http://localhost:8002/admin/):"
	@echo ""
	$(MANAGE) createsuperuser
	@echo ""
	@echo "╔══════════════════════════════════════════╗"
	@echo "║              Setup complete!              ║"
	@echo "╠══════════════════════════════════════════╣"
	@echo "║  Frontend:  http://localhost:5173         ║"
	@echo "║  Backend:   http://localhost:8002         ║"
	@echo "║  Admin:     http://localhost:8002/admin/  ║"
	@echo "║  MCP:       http://localhost:8001         ║"
	@echo "║                                           ║"
	@echo "║  1. Log in at /admin/ with your account   ║"
	@echo "║  2. Visit http://localhost:5173            ║"
	@echo "║  3. Create your workspace on /onboarding   ║"
	@echo "║                                           ║"
	@echo "║  Run 'make help' for available commands.  ║"
	@echo "╚══════════════════════════════════════════╝"

# Keep `setup` as an alias for backwards compat
.PHONY: setup
setup: install

# ──────────────────────────────────────────────
# Day-to-day development
# ──────────────────────────────────────────────

.PHONY: up
up: ## Start all services
	$(COMPOSE) up -d --build

.PHONY: down
down: ## Stop all services
	$(COMPOSE) down

.PHONY: restart
restart: down up ## Restart all services

.PHONY: logs
logs: ## Tail logs for all services
	$(COMPOSE) logs -f

.PHONY: logs-backend
logs-backend: ## Tail backend logs only
	$(COMPOSE) logs -f backend

.PHONY: logs-frontend
logs-frontend: ## Tail frontend logs only
	$(COMPOSE) logs -f frontend

# ──────────────────────────────────────────────
# Database
# ──────────────────────────────────────────────

.PHONY: migrate
migrate: ## Run Django migrations
	$(MANAGE) sync_squashed_migration_names
	$(MANAGE) migrate

.PHONY: makemigrations
makemigrations: ## Generate new Django migrations
	$(MANAGE) makemigrations

.PHONY: seed
seed: ## Seed plans and feature flags
	$(MANAGE) seed_plans
	$(MANAGE) seed_feature_flags

.PHONY: superuser
superuser: ## Create a Django superuser
	$(MANAGE) createsuperuser

.PHONY: dbshell
dbshell: ## Open a psql shell
	$(COMPOSE) exec db psql -U koinoflow

# ──────────────────────────────────────────────
# Testing
# ──────────────────────────────────────────────

.PHONY: test
test: ## Run all backend tests
	$(BACKEND_EXEC) pytest --tb=short

.PHONY: test-v
test-v: ## Run all backend tests (verbose)
	$(BACKEND_EXEC) pytest -v

.PHONY: test-frontend
test-frontend: ## Run frontend tests
	$(FRONTEND_EXEC) npm run test

# ──────────────────────────────────────────────
# Linting & formatting
# ──────────────────────────────────────────────

.PHONY: lint
lint: ## Run ruff check + format check on backend
	$(BACKEND_EXEC) ruff check .
	$(BACKEND_EXEC) ruff format --check .

.PHONY: lint-frontend
lint-frontend: ## Run ESLint on the frontend
	$(FRONTEND_EXEC) npm run lint

.PHONY: fmt
fmt: ## Auto-format backend code with ruff
	$(BACKEND_EXEC) ruff check --fix .
	$(BACKEND_EXEC) ruff format .

.PHONY: fmt-frontend
fmt-frontend: ## Format frontend files with Prettier
	$(FRONTEND_EXEC) npx prettier --write .

.PHONY: tsc
tsc: ## Run frontend TypeScript type checks
	$(FRONTEND_EXEC) npm run typecheck

# ──────────────────────────────────────────────
# Django shortcuts
# ──────────────────────────────────────────────

.PHONY: shell
shell: ## Django shell
	$(MANAGE) shell

.PHONY: check
check: ## Django system check
	$(MANAGE) check

.PHONY: api-schema
api-schema: ## Export OpenAPI schema for the frontend
	$(MANAGE) export_openapi > frontend/openapi.json

# ──────────────────────────────────────────────
# MCP server
# ──────────────────────────────────────────────

MCP_EXEC = $(COMPOSE) exec mcp-server
MCP_DEV_EXEC = $(COMPOSE) --profile dev run --rm mcp-server-dev

.PHONY: update-mcp-clients
update-mcp-clients: ## Refresh vendored MCP client registry
	curl -sSL -o mcp-server/mcp-clients.json \
		https://raw.githubusercontent.com/apify/mcp-client-capabilities/refs/heads/master/src/mcp_client_capabilities/mcp-clients.json

.PHONY: lint-mcp
lint-mcp: ## Run ruff check + format check on mcp-server (dev image)
	$(MCP_DEV_EXEC) ruff check .
	$(MCP_DEV_EXEC) ruff format --check .

.PHONY: test-mcp
test-mcp: ## Run mcp-server tests (dev image)
	$(MCP_DEV_EXEC) pytest -v

.PHONY: logs-mcp
logs-mcp: ## Tail MCP server logs
	$(COMPOSE) logs -f mcp-server

.PHONY: mcp-build-npm
mcp-build-npm: ## Build TypeScript MCP npm package
	cd mcp-package && npm run build

# ──────────────────────────────────────────────
# Pre-commit & secrets scanning
# ──────────────────────────────────────────────

.PHONY: install-pre-commit
install-pre-commit: ## Install the gitleaks pre-commit hook (requires pipx or pip)
	@command -v pre-commit >/dev/null 2>&1 || (echo "Installing pre-commit..." && pipx install pre-commit 2>/dev/null || pip install --user pre-commit)
	pre-commit install
	@echo "✓ pre-commit hook installed. Run 'pre-commit run --all-files' to scan the repo."

.PHONY: secrets-scan
secrets-scan: ## Run gitleaks against the working tree + history
	@command -v gitleaks >/dev/null 2>&1 || (echo "gitleaks not installed. Install from https://github.com/gitleaks/gitleaks/releases" && exit 1)
	gitleaks detect --source . -c .gitleaks.toml --redact --verbose

# ──────────────────────────────────────────────
# Cleanup
# ──────────────────────────────────────────────

.PHONY: clean
clean: ## Stop services, remove volumes, and clear MCP auth cache
	$(COMPOSE) down -v
	@rm -rf ~/.mcp-auth/
	@echo "✓ Cleared MCP auth cache (~/.mcp-auth/)"

# ──────────────────────────────────────────────
# Help
# ──────────────────────────────────────────────

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
