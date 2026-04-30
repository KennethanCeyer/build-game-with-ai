.PHONY: format check test mypy

format:
	black src tests run_demo.py

check:
	black --check src tests run_demo.py
	mypy
	pytest tests -q -s

test:
	pytest tests -q -s

mypy:
	mypy
