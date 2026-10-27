-include .env
APP_USER ?= rss_app
APP_USER_PASSWORD ?= rss_app
ORACLE_PWD ?= Oracle123

PIPELINE = docker compose run --rm pipeline python -m rss.pipeline

.PHONY: up down logs status build pipeline demo demo-data migrate eval bench test sql sql-admin

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

status:
	docker compose ps

build:
	docker compose build

pipeline:
	$(PIPELINE) all

demo:
	DATA_DIR=/app/demo $(PIPELINE) all

demo-data:
	docker compose run --rm pipeline python -m rss.demo

migrate:
	$(PIPELINE) migrate

eval:
	docker compose run --rm pipeline python -m rss.eval search llm

bench:
	docker compose run --rm pipeline python -m rss.eval ann

test:
	docker compose run --rm --no-deps pipeline sh -c "pip install -q -r requirements-dev.txt && ruff check src tests && pytest -q"

sql:
	docker compose exec oracle sqlplus $(APP_USER)/$(APP_USER_PASSWORD)@//localhost:1521/FREEPDB1

sql-admin:
	docker compose exec oracle sqlplus sys/$(ORACLE_PWD)@//localhost:1521/FREEPDB1 as sysdba
