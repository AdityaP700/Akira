.PHONY: up down migrate seed test lint

up:
	docker compose up --build

down:
	docker compose down

migrate:
	alembic upgrade head

seed:
	python scripts/seed_goa_trip.py

test:
	pytest -q --cov=app

lint:
	ruff check . && ruff format --check . && mypy app/domain app/services
