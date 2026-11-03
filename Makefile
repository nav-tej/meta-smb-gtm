.PHONY: setup dev lint format test check

PY := .venv/bin

setup:
	uv venv --python 3.12
	uv pip install -r requirements.txt -r requirements-dev.txt

dev:
	$(PY)/uvicorn src.api.main:app --reload --port 8000

lint:
	$(PY)/ruff check .

format:
	$(PY)/ruff format .

test:
	$(PY)/pytest

check: lint
	$(PY)/ruff format --check .
	$(PY)/pytest
