.PHONY: all help test check lint clean run

all: test

PYTHON   ?= python3
SRC      := php_analyzer.py
TESTS    := tests/
REPORT   ?= analysis_report.json

help:
	@echo "Targets:"
	@echo "  make test          Run unit tests (unittest)"
	@echo "  make lint          Run ruff linter"
	@echo "  make run DIR=path  Analyse a PHP directory"
	@echo "  make clean         Remove caches and generated files"

check:
	$(PYTHON) -m py_compile $(SRC)
	$(PYTHON) -m unittest discover -s $(TESTS) -v

test: check

lint:
	ruff check $(SRC) $(TESTS)

run:
ifndef DIR
	$(error DIR is not set. Usage: make run DIR=/path/to/php)
endif
	$(PYTHON) $(SRC) $(DIR)

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -name "*.pyc" -delete
	rm -f $(REPORT)
