.PHONY: setup test test-network test-postgres audit audit-network audit-samples vertical-slice vertical-slice-offline historical-preflight historical historical-offline coaching-validate coaching-sources coaching-load expected-performance coach-impact

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
	@test -n "$$TEST_DATABASE_URL" || (echo "TEST_DATABASE_URL is required" && exit 2)
	$(PYTHON) -c "import psycopg"
	$(PYTHON) -m unittest tests.test_postgres_behavior -v

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
