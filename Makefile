# Common tasks for Insurance-Policy-RAG.
#
# Every target is a thin wrapper around one plain command (shown in `make help`),
# so you can run the same thing without make, e.g. on Windows without
# `conda install make`.
#
# Override the interpreter with: make test PYTHON=python3.11

PYTHON ?= python

.DEFAULT_GOAL := help
.PHONY: help setup test lint eval run-app run-api restore-index clean

help: ## Show targets and the command each one runs
	@echo "Targets (plain command in brackets):"
	@echo "  setup          install runtime + dev dependencies  [pip install -r requirements.txt -r requirements-dev.txt]"
	@echo "  test           offline tests, no API key needed    [python -m pytest -q tests/]"
	@echo "  lint           lint the code                       [python -m ruff check .]"
	@echo "  eval           evaluation harness (GEMINI_API_KEY)  [python -m src.evaluate]"
	@echo "  run-app        Streamlit app on :8501               [python -m streamlit run app/streamlit_app.py]"
	@echo "  run-api        FastAPI backend on :8000             [python -m uvicorn api.main:app --reload]"
	@echo "  restore-index  undo local changes to the demo index [git restore app/demo_index]"
	@echo "  clean          remove caches                        [rm -rf .pytest_cache .ruff_cache **/__pycache__]"

setup:
	$(PYTHON) -m pip install -r requirements.txt -r requirements-dev.txt

test:
	$(PYTHON) -m pytest -q tests/

lint:
	$(PYTHON) -m ruff check .

# Extra flags pass through, e.g.: make eval ARGS="--no-cache"
eval:
	$(PYTHON) -m src.evaluate $(ARGS)

run-app:
	$(PYTHON) -m streamlit run app/streamlit_app.py

run-api:
	$(PYTHON) -m uvicorn api.main:app --reload

# ChromaDB rewrites the committed index files when it opens them; run this
# after using the app or the evaluation locally, before committing.
restore-index:
	git restore app/demo_index

clean:
	rm -rf .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
