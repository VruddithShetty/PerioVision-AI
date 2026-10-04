# PerioVision AI - developer shortcuts (macOS/Linux, or Windows with "make" installed).
# Windows without make: use the same targets via PowerShell:  .\run.ps1 <target>
PYTHON ?= python

.PHONY: setup backend frontend test demo lint docs

setup:
	cd backend && $(PYTHON) -m pip install -r requirements-dev.txt
	$(PYTHON) backend/scripts/setup_local.py
	@if [ -f frontend/package.json ]; then cd frontend && npm install; fi

backend:
	cd backend && $(PYTHON) wsgi.py

frontend:
	@if [ -f frontend/package.json ]; then cd frontend && npm run dev; else echo "Frontend is added in Phase 4"; fi

test:
	cd backend && $(PYTHON) -m pytest -q

demo:
	cd backend && DB_MODE=demo $(PYTHON) wsgi.py

lint:
	cd backend && $(PYTHON) -m ruff check .
	cd frontend && npm run lint

docs:
	cd backend && $(PYTHON) scripts/generate_api_docs.py
