# Falsify Workbench — every entry point. Thin sugar over `uv` (decision D-1 in
# docs/SPEC.md). No make on your machine? Run the uv command on each line directly.

.PHONY: help setup test demo eval

help:
	@echo "make setup   create .venv (Python 3.12) and install deps      -> uv sync"
	@echo "make test    run the full test suite                          -> uv run pytest -q"
	@echo "make demo    build synthetic warehouse + case 0000-demo-synthetic"
	@echo "make eval    score evals/scenarios/*.yaml (gates analyze-skill edits)"

setup:
	uv sync

test:
	uv run pytest -q

demo:
	uv run python -m seeds.generate

eval:
	uv run python -m evals.run_eval
