.PHONY: all help test test-claude test-codex test-gemini lint lint-claude clean clean-claude clean-codex clean-gemini

all: test

help:
	@echo "Targets:"
	@echo "  make test           Run unit tests for all implementations"
	@echo "  make lint           Run lint (claude/ only; requires ruff)"
	@echo "  make clean          Remove caches / generated reports"
	@echo
	@echo "Individual:"
	@echo "  make test-claude | test-codex | test-gemini"
	@echo "  make clean-claude | clean-codex | clean-gemini"

test: test-claude test-codex test-gemini

test-claude:
	$(MAKE) -C claude test

test-codex:
	$(MAKE) -C codex test

test-gemini:
	$(MAKE) -C gemini test

lint: lint-claude

lint-claude:
	@command -v ruff >/dev/null 2>&1 || { echo "ruff not found. Install with: python3 -m pip install ruff" >&2; exit 2; }
	$(MAKE) -C claude lint

clean: clean-claude clean-codex clean-gemini

clean-claude:
	$(MAKE) -C claude clean

clean-codex:
	$(MAKE) -C codex clean

clean-gemini:
	$(MAKE) -C gemini clean

