.PHONY: setup test test-network test-postgres audit audit-network audit-samples vertical-slice vertical-slice-offline historical-preflight historical historical-offline coaching-validate coaching-sources coaching-load expected-performance coach-impact db-migrate db-load api frontend-install frontend-dev frontend-test frontend-e2e frontend-check frontend-build

PYTHON ?= python3
PROJECT_ROOT := $(CURDIR)

setup:
	$(PYTHON) -m pip install -r requirements.lock
	$(PYTHON) -m pip install --no-deps -e .

test:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -v

test-network:
	RUN_NETWORK_TESTS=1 PYTHONPATH=src $(PYTHON) -m unittest tests.test_checkpoint_three_network -v

test-postgres:
	PYTHONPATH=src $(PYTHON) scripts/run_postgres_tests.py

audit:
	$(PYTHON) scripts/audit_sources.py

audit-network:
	$(PYTHON) scripts/audit_sources.py --network

audit-samples:
	$(PYTHON) scripts/audit_sources.py --network --download-samples

vertical-slice:
	PYTHONPATH=src $(PYTHON) -m nfl_coaching_impact.cli vertical-slice --project-root "$(PROJECT_ROOT)"

vertical-slice-offline:
	PYTHONPATH=src $(PYTHON) -m nfl_coaching_impact.cli vertical-slice --project-root "$(PROJECT_ROOT)" --offline

historical-preflight:
	PYTHONPATH=src $(PYTHON) -m nfl_coaching_impact.cli historical --project-root "$(PROJECT_ROOT)" --preflight-only

historical:
	PYTHONPATH=src $(PYTHON) -m nfl_coaching_impact.cli historical --project-root "$(PROJECT_ROOT)"

historical-offline:
	PYTHONPATH=src $(PYTHON) -m nfl_coaching_impact.cli historical --project-root "$(PROJECT_ROOT)" --offline

coaching-validate:
	PYTHONPATH=src $(PYTHON) scripts/validate_coaching_data.py

coaching-sources:
	PYTHONPATH=src $(PYTHON) scripts/check_coaching_sources.py

coaching-load:
	@test -n "$$DATABASE_URL" || (echo "DATABASE_URL is required" && exit 2)
	PYTHONPATH=src $(PYTHON) scripts/load_coaching_data.py --database-url "$$DATABASE_URL"

expected-performance:
	PYTHONPATH=src $(PYTHON) -m nfl_coaching_impact.cli expected-performance --project-root "$(PROJECT_ROOT)"

coach-impact:
	PYTHONPATH=src $(PYTHON) -m nfl_coaching_impact.cli coach-impact --project-root "$(PROJECT_ROOT)"

db-migrate:
	@test -n "$$DATABASE_URL" || (echo "DATABASE_URL is required" && exit 2)
	DATABASE_URL="$$DATABASE_URL" $(PYTHON) -m alembic upgrade head

db-load:
	@test -n "$$DATABASE_URL" || (echo "DATABASE_URL is required" && exit 2)
	PYTHONPATH=src $(PYTHON) -m nfl_coaching_impact.cli load-serving --project-root "$(PROJECT_ROOT)" --database-url "$$DATABASE_URL"

api:
	@test -n "$$DATABASE_URL" || (echo "DATABASE_URL is required" && exit 2)
	PYTHONPATH=src $(PYTHON) -m uvicorn nfl_coaching_impact.api:app --reload

frontend-install:
	pnpm install --frozen-lockfile

frontend-dev:
	pnpm --filter nfl-coaching-impact-web dev

frontend-test:
	pnpm --filter nfl-coaching-impact-web test

frontend-e2e:
	pnpm --filter nfl-coaching-impact-web test:e2e

frontend-check:
	pnpm --filter nfl-coaching-impact-web lint
	pnpm --filter nfl-coaching-impact-web format
	pnpm --filter nfl-coaching-impact-web typecheck
	pnpm --filter nfl-coaching-impact-web test
	pnpm --filter nfl-coaching-impact-web build

frontend-build:
	pnpm --filter nfl-coaching-impact-web build
