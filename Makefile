.PHONY: install format lint typecheck test verify-artifacts check

install:
	python -m pip install -e '.[dev]'

format:
	ruff format .
	ruff check . --fix

lint:
	ruff check .
	ruff format --check .

typecheck:
	mypy src/civicdecision

test:
	pytest -q --cov=civicdecision --cov-report=term-missing

verify-artifacts:
	python scripts/verify_repository.py

check: lint typecheck test verify-artifacts
