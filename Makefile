# Common tasks for Insurance-Policy-RAG.
#
# Every target is a thin wrapper around one plain command (shown in `make help`),
# so you can run the same thing without make, e.g. on Windows without
# `conda install make`.
#
# Override the interpreter with: make test PYTHON=python3.11

PYTHON ?= python

.DEFAULT_GOAL := help
.PHONY: help setup test lint eval eval-v1 smoke judge judge-sheet model-check eval-set run-app run-api docker-build docker-run deploy restore-index clean

help: ## Show targets and the command each one runs
	@echo "Targets (plain command in brackets):"
	@echo "  setup          install runtime + dev dependencies  [pip install -r requirements.txt -r requirements-dev.txt]"
	@echo "  test           offline tests, no API key needed    [python -m pytest -q tests/]"
	@echo "  lint           lint the code                       [python -m ruff check .]"
	@echo "  eval           eval set v2 + report (GEMINI_API_KEY) [python -m src.evaluate]"
	@echo "  eval-v1        the older v1 eval set (GEMINI_API_KEY) [python -m src.evaluate --questions notebooks/eval/eval_questions.json]"
	@echo "  smoke          CI smoke eval + gates (GEMINI_API_KEY) [python -m src.evaluate --subset eval/smoke_v2.txt --gates]"
	@echo "  model-check    pinned models still available? newer? [python -m src.model_check]"
	@echo "  judge          LLM-judge cached answers (GEMINI_API_KEY) [python -m src.judge]"
	@echo "  judge-sheet    human scoring sheet for the judge     [python -m src.judge --sheet]"
	@echo "  eval-set       validate eval set, rebuild review    [python -m src.eval_set]"
	@echo "  run-app        Streamlit app on :8501               [python -m streamlit run app/streamlit_app.py]"
	@echo "  run-api        FastAPI backend on :8000             [python -m uvicorn api.main:app --reload]"
	@echo "  docker-build   build the API container               [docker build -t insurance-rag-api .]"
	@echo "  docker-run     run it on :8080 with keys from .env   [docker run --rm -p 8080:8080 --env-file .env insurance-rag-api]"
	@echo "  deploy         deploy the API to Cloud Run (docs/DEPLOY.md; PROJECT=<id> [REGION=us-central1])"
	@echo "  restore-index  undo local changes to the demo index [git restore app/demo_index]"
	@echo "  clean          remove caches                        [rm -rf .pytest_cache .ruff_cache **/__pycache__]"

setup:
	$(PYTHON) -m pip install -r requirements.txt -r requirements-dev.txt

test:
	$(PYTHON) -m pytest -q tests/

lint:
	$(PYTHON) -m ruff check .

# Runs eval set v2 and writes eval/reports/<version>_<date>.md + .json.
# Extra flags pass through, e.g.: make eval ARGS="--no-cache"
eval:
	$(PYTHON) -m src.evaluate $(ARGS)

eval-v1:
	$(PYTHON) -m src.evaluate --questions notebooks/eval/eval_questions.json $(ARGS)

# The 12-question CI smoke eval with its gates (exit 1 if a gate fails).
smoke:
	$(PYTHON) -m src.evaluate --subset eval/smoke_v2.txt --gates $(ARGS)

model-check:
	$(PYTHON) -m src.model_check $(ARGS)

# Judge cached answers with the pinned judge model (resumable, budgeted with
# ARGS="--max-calls N"); then `make eval` puts the scores in the report.
judge:
	$(PYTHON) -m src.judge $(ARGS)

judge-sheet:
	$(PYTHON) -m src.judge --sheet $(ARGS)

# Validate eval/questions_v2.json and regenerate eval/questions_v2_review.md.
eval-set:
	$(PYTHON) -m src.eval_set

run-app:
	$(PYTHON) -m streamlit run app/streamlit_app.py

run-api:
	$(PYTHON) -m uvicorn api.main:app --reload

# API container (PLAN.md M4). .env holds GEMINI_API_KEY=... (never committed).
IMAGE ?= insurance-rag-api
docker-build:
	docker build -t $(IMAGE) .

docker-run:
	docker run --rm -p 8080:8080 --env-file .env $(IMAGE)

# Deploy to Cloud Run from source (see docs/DEPLOY.md for the one-time setup).
REGION ?= us-central1
SERVICE ?= insurance-rag-api
deploy:
	@test -n "$(PROJECT)" || (echo "usage: make deploy PROJECT=<gcp-project-id> [REGION=us-central1]"; exit 2)
	gcloud run deploy $(SERVICE) --source . --project $(PROJECT) --region $(REGION) \
	  --allow-unauthenticated --min-instances 0 --max-instances 1 --memory 1Gi --cpu 1 --timeout 120 \
	  --update-secrets=GEMINI_API_KEY=gemini-api-key:latest,INSURANCE_RAG_API_TOKEN=insurance-rag-api-token:latest

# ChromaDB rewrites the committed index files when it opens them; run this
# after using the app or the evaluation locally, before committing.
restore-index:
	git restore app/demo_index

clean:
	rm -rf .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
