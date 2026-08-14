.PHONY: install install-release format lint typecheck test verify-artifacts performance release-candidate check

install:
	python -m pip install -e '.[dev]'

install-release:
	python -m pip install -e '.[dev,release]'

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

performance:
	python scripts/benchmark_product.py --output verification/milestone-8-performance.json

release-candidate:
	python scripts/build_release_candidate.py --output-dir dist/release-0.8.1

check: lint typecheck test verify-artifacts
