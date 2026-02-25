# Makefile for PHP Code Analyzer

# Use bash for better if/else syntax
SHELL := /bin/bash

.PHONY: all test clean run install

# Default target to run when 'make' is called without arguments
all: test

# Target to run the unit tests
# 'discover' automatically finds tests in the current directory
test:
	@echo "Running unit tests..."
	python3 -m unittest discover -v

# Target to run the analyzer on a given directory
# Example usage: make run DIR=/path/to/your/php/project
run:
	@if [ -z "$(DIR)" ]; then \
		echo "Error: Directory path must be provided."; \
		echo "Usage: make run DIR=<path_to_directory>"; \
		exit 1; \
	fi
	@echo "Running analyzer on directory: $(DIR)..."
	python3 php_analyzer.py $(DIR)

# Target to clean up generated files and directories
clean:
	@echo "Cleaning up generated files..."
	rm -f analysis_report.json
	rm -rf __pycache__
	rm -rf */__pycache__
	rm -rf temp_test_project

# Placeholder for dependency installation
install:
	@echo "Project has no external dependencies to install."

