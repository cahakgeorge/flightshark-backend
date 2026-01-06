.PHONY: help build up down logs shell migrate test lint format clean

# Default target
help:
	@echo "Flightshark Backend Commands"
	@echo "============================"
	@echo ""
	@echo "Development:"
	@echo "  make build        - Build all Docker images"
	@echo "  make up           - Start all services"
	@echo "  make down         - Stop all services"
	@echo "  make restart      - Restart all services"
	@echo "  make logs         - View logs (all services)"
	@echo "  make logs-api     - View API logs"
	@echo "  make logs-worker  - View worker logs"
	@echo ""
	@echo "Database:"
	@echo "  make migrate      - Run database migrations"
	@echo "  make makemigrations - Create new migrations"
	@echo "  make db-shell     - Open PostgreSQL shell"
	@echo "  make mongo-shell  - Open MongoDB shell"
	@echo "  make redis-cli    - Open Redis CLI"
	@echo ""
	@echo "Testing & Quality:"
	@echo "  make test         - Run all tests"
	@echo "  make test-api     - Run API tests"
	@echo "  make lint         - Run linters"
	@echo "  make format       - Format code"
	@echo ""
	@echo "Utilities:"
	@echo "  make shell-api    - Shell into API container"
	@echo "  make shell-worker - Shell into worker container"
	@echo "  make clean        - Remove all containers and volumes"
	@echo "  make setup        - Initial setup (copy env, build, migrate)"

# ===================
# Development
# ===================
build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

restart:
	docker compose restart

logs:
	docker compose logs -f

logs-api:
	docker compose logs -f api

logs-worker:
	docker compose logs -f worker beat

logs-admin:
	docker compose logs -f admin

# ===================
# Database
# ===================
migrate:
	docker compose exec api alembic upgrade head

makemigrations:
	docker compose exec api alembic revision --autogenerate -m "$(msg)"

db-shell:
	docker compose exec postgres psql -U flightshark -d flightshark

mongo-shell:
	docker compose exec mongo mongosh flightshark

redis-cli:
	docker compose exec redis redis-cli

# ===================
# Testing & Quality
# ===================
test:
	docker compose exec api pytest -v

test-api:
	docker compose exec api pytest tests/ -v

test-cov:
	docker compose exec api pytest --cov=app --cov-report=html

lint:
	docker compose exec api ruff check .
	docker compose exec api mypy app/

format:
	docker compose exec api ruff format .
	docker compose exec api ruff check --fix .

# ===================
# Shells
# ===================
shell-api:
	docker compose exec api /bin/bash

shell-worker:
	docker compose exec worker /bin/bash

shell-admin:
	docker compose exec admin /bin/bash

# ===================
# Utilities
# ===================
clean:
	docker compose down -v --remove-orphans
	docker system prune -f

setup:
	@if [ ! -f .env ]; then cp .env.example .env; echo "Created .env file"; fi
	docker compose build
	docker compose up -d postgres redis mongo rabbitmq
	@echo "Waiting for databases to be ready..."
	@sleep 10
	docker compose up -d
	@echo "Running migrations..."
	@sleep 5
	docker compose exec api alembic upgrade head || true
	@echo ""
	@echo "Setup complete! Services running at:"
	@echo "  API:      http://localhost:8000"
	@echo "  Admin:    http://localhost:8001"
	@echo "  RabbitMQ: http://localhost:15672"
	@echo "  Grafana:  http://localhost:3002"

# ===================
# Django Admin
# ===================
admin-superuser:
	docker compose exec admin python manage.py createsuperuser

admin-migrate:
	docker compose exec admin python manage.py migrate

admin-makemigrations:
	docker compose exec admin python manage.py makemigrations

admin-collectstatic:
	docker compose exec admin python manage.py collectstatic --noinput

admin-shell:
	docker compose exec admin python manage.py shell_plus

# Production build
build-prod:
	docker compose -f docker-compose.yml -f docker-compose.prod.yml build

# Production up
up-prod:
	docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

