.PHONY: help setup install dev up down logs test lint format clean

help: ## Show this help message
	@echo "ACE Enterprise - Development Commands"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

setup: ## Initial project setup
	@echo "Setting up ACE Enterprise..."
	cp .env.example .env
	@echo "✓ Created .env file"
	@echo "Please edit .env with your configuration"

install: ## Install Python dependencies
	pip install -e .[dev]

dev: ## Start development environment
	docker-compose up -d

dev-full: ## Start development with monitoring
	docker-compose --profile monitoring up -d

up: dev ## Alias for dev

down: ## Stop development environment
	docker-compose down

down-volumes: ## Stop and remove volumes
	docker-compose down -v

logs: ## Show logs
	docker-compose logs -f

logs-api: ## Show API logs only
	docker-compose logs -f api

shell: ## Open shell in API container
	docker-compose exec api bash

psql: ## Open PostgreSQL shell
	docker-compose exec postgres psql -U ace_user -d ace_enterprise

redis-cli: ## Open Redis CLI
	docker-compose exec redis redis-cli

migrate: ## Run database migrations
	docker-compose exec api alembic upgrade head

migrate-create: ## Create new migration (usage: make migrate-create MSG="description")
	docker-compose exec api alembic revision --autogenerate -m "$(MSG)"

migrate-down: ## Rollback last migration
	docker-compose exec api alembic downgrade -1

test: ## Run tests
	docker-compose exec api pytest

test-unit: ## Run unit tests only
	docker-compose exec api pytest tests/unit

test-integration: ## Run integration tests only
	docker-compose exec api pytest tests/integration

test-cov: ## Run tests with coverage
	docker-compose exec api pytest --cov=src --cov-report=html --cov-report=term

lint: ## Run linting
	ruff check src/ tests/
	mypy src/

format: ## Format code
	black src/ tests/
	ruff check --fix src/ tests/

clean: ## Clean up temporary files
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.coverage" -delete
	rm -rf .pytest_cache htmlcov/ .mypy_cache/

rebuild: ## Rebuild Docker images
	docker-compose build --no-cache

restart: ## Restart services
	docker-compose restart

health: ## Check service health
	@echo "Checking service health..."
	@curl -s http://localhost:8000/health | python -m json.tool || echo "API not responding"

docs: ## Generate API documentation
	@echo "API docs available at: http://localhost:8000/docs"
	@echo "ReDoc available at: http://localhost:8000/redoc"

monitoring: ## Open monitoring dashboards
	@echo "Grafana: http://localhost:3000 (admin/admin)"
	@echo "Prometheus: http://localhost:9091"
