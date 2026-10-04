PY := .venv/bin/python
PIP := .venv/bin/pip

.PHONY: setup test lint ingest profile clean

## Create virtualenv and install the project in editable mode.
setup:
	python3 -m venv .venv
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"
	@test -f .env || cp .env.example .env
	@echo "Setup complete. Edit .env to add a SOCRATA_APP_TOKEN (optional)."

test:
	$(PY) -m pytest

lint:
	.venv/bin/ruff check .

## Ingest one source: make ingest SOURCE=nyc_311 [MAX=50000]
SOURCE ?= nyc_311
MAX ?=
ingest:
	$(PY) scripts/ingest.py --source $(SOURCE) $(if $(MAX),--max-records $(MAX),)

## Profile an ingested source: make profile SOURCE=nyc_311
profile:
	$(PY) scripts/profile_dataset.py --source $(SOURCE)

clean:
	rm -rf .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -exec rm -rf {} +

## Normalization, entity resolution, evaluation
normalize:
	$(PY) scripts/normalize.py

resolve:
	$(PY) scripts/resolve_entities.py

evaluate:
	$(PY) scripts/evaluate_er.py

## dbt (absolute DB path because dbt runs from dbt/)
DBT := MIP_DUCKDB_PATH=$(abspath data/warehouse/mip.duckdb) ../.venv/bin/dbt
dbt-run:
	cd dbt && $(DBT) run --profiles-dir .

dbt-test:
	cd dbt && $(DBT) test --profiles-dir .

## Full local pipeline: ingest all sources -> normalize -> resolve -> dbt
pipeline:
	$(PY) scripts/ingest.py --source nyc_311 --incremental
	$(PY) scripts/ingest.py --source dob_permits --incremental
	$(PY) scripts/ingest.py --source dca_licenses --incremental
	$(PY) scripts/ingest.py --source pluto --incremental
	$(PY) scripts/ingest.py --source hpd_registrations --incremental
	$(PY) scripts/ingest.py --source hpd_contacts --incremental
	$(PY) scripts/normalize.py
	$(PY) scripts/resolve_entities.py
	cd dbt && $(DBT) run --profiles-dir . && $(DBT) test --profiles-dir .

## Analytics stack (docker)
up:
	docker-compose up -d postgres metabase

publish:
	$(PY) scripts/publish_postgres.py

dashboard:
	$(PY) scripts/provision_metabase.py

airflow-up:
	docker-compose --profile airflow up -d --build airflow

down:
	docker-compose --profile airflow down
