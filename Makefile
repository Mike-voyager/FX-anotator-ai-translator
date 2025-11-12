.PHONY: help install install-dev format check mypy lint clean

help:
	@echo "Available commands:"
	@echo "  make install      - Install production dependencies"
	@echo "  make install-dev  - Install development dependencies"
	@echo "  make format       - Format code with black"
	@echo "  make check        - Check code formatting"
	@echo "  make mypy         - Run mypy type checker"
	@echo "  make lint         - Run all linters"
	@echo "  make clean        - Remove cache files"

install:
	pip install -r requirements.txt

install-dev:
	pip install -r requirements.txt
	pip install -r requirements-dev.txt

format:
	@echo "Formatting with black..."
	black fx_translator/ main.py

check:
	@echo "Checking formatting..."
	black --check fx_translator/ main.py

mypy:
	@echo "Running mypy..."
	mypy fx_translator/ main.py

lint: check mypy
	@echo "All checks passed!"

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
