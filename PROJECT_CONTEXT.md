# Project Context & Handoff — Insurance-Policy-RAG

> Working notes so development can resume cleanly after a break or a closed tab.
> Last updated: 2026-07-27. All development happens on the `new_dev` branch.

## What this project is

A Retrieval-Augmented Generation (RAG) question-answering system over a single insurance policy PDF.
A user asks a natural-language question; the system retrieves the most relevant policy passages,
answers **only** from those passages with citations, and explicitly abstains ("I don't know") when
the policy does not cover the question. Built with Gemini embeddings + ChromaDB + a Gemini chat model.

## Sample policy used for calibration

A published, SAMPLE-watermarked **Manulife FlexCare (medical) contract**, 32 pages, is used as the
working policy for calibration. NB01 ingestion produces **37 chunks** from this document. The real
policy PDF is never committed (privacy).

## Repository layout (key paths)

- `notebooks/01_document_ingestion.ipynb` — PDF ingest + chunking. Source of truth = 37 chunks (`chunks.json`).
- `notebooks/02_embeddings_and_indexing.ipynb` — builds the persistent Chroma index.
- `notebooks/03_insurance_policy_rag.ipynb` — retrieval + guardrailed answer generation.
- `notebooks/04_evaluation.ipynb` — Day-5 evaluation harness.
- `notebooks/eval/eval_questions.json` — evaluation question set (8 in-scope, 4 out-of-scope).
- `notebooks/assets/` — documentation images extracted out of NB03.
- `data/documents/` — where the policy PDF lives locally (NOT committed, for privacy).

## Key configuration (must stay consistent across notebooks)

- `PROJECT_ROOT` = `/content/drive/MyDrive/Insurance-Policy-RAG` (overridable via `INSURANCE_RAG_ROOT`).
- Chroma index at `PROJECT_ROOT/chroma`; collection name `insurance_policy_cvdb`.
- `EMBED_MODEL = gemini-embedding-001`; `GEN_MODEL = gemini-2.0-flash` (both FREE-tier eligible). NOTE: gemini-2.5-flash was retired for new keys, so GEN_MODEL was moved to gemini-2.0-flash.
- `K_DEFAULT = 4`; `DISTANCE_THRESHOLD = 0.37` (cosine distance; lower = more similar). Calibrated via a retrieval sweep — see Day-5 notes below.
- Retrieval short-circuits to `IDK_ANSWER = "I don't know"` when nothing passes the threshold.

## Pipeline interfaces (targeted by the eval harness / future app)

- `retrieve_top_k(query, k=K_DEFAULT, threshold=DISTANCE_THRESHOLD)` -> list of `{id, text, metadata, score}`.
- `answer_question(question, k=K_DEFAULT, model_name=GEN_MODEL)` -> `(answer_text, pages, retrieved)`; returns `(IDK_ANSWER, [], [])` on empty retrieval.

## Progress — done

- Day 1–2: embeddings + Chroma index (`chunks.json` as source of truth).
- Day 3: reconciled NB03 with shared pipeline; extracted doc images to `assets/`; removed a stray nbstripout install cell; dropped langchain/langchain-core from NB01 (kept langchain-text-splitters); aligned requirements.txt.
- Day 4: hardened retrieval/generation — DISTANCE_THRESHOLD filtering, IDK short-circuit, rate-limit backoff.
- Day 5: evaluation harness (`04_evaluation.ipynb`) + question set (`eval/eval_questions.json`). Metrics: out-of-scope abstention rate (guardrail), in-scope retrieval hit rate, in-scope answer-keyword rate. Free-tier-safe (sequential + paced + cached); privacy-safe (no real policy facts committed).
- Day 5 (calibration, partial): aligned eval questions to the Manulife sample policy and expanded to 8 in-scope + 4 out-of-scope. Fixed NB03 (removed dead LangChain imports — project does not use LangChain; set GEN_MODEL=gemini-2.0-flash). Ran a retrieval-only sweep over all 12 questions: in-scope distances ~0.25–0.34, out-of-scope ~0.40–0.50, so DISTANCE_THRESHOLD was set to 0.37.

## Roadmap — remaining

- **Day 5 calibration (BLOCKED on generation quota):** the Gemini generation quota on the current key is `limit: 0`, so answer generation (demo query + NB04) cannot run yet. Embeddings/retrieval work fine. ACTION: provision a key with generation quota at aistudio.google.com, then run NB03 then NB04 in one session; read each in-scope answer and fill `expected_keywords` in `eval_questions.json` (replace "TODO"); delete `eval/eval_results.json`; re-run. Re-check DISTANCE_THRESHOLD if chunking or the embedding model changes.
- Day 6: consolidate shared config (single PROJECT_ROOT/settings block) AND refactor the notebook logic into a plain module `rag_pipeline.py`. Design requirement: expose index-building as a callable (e.g. `build_index_from_pdf(pdf) -> collection`) parameterized by PDF source — NOT hard-wired to the Drive path — so the app can do runtime uploads.
- Day 7: README + documentation (include the eval results as the quality story).
- Day 8: Streamlit MVP app (imports `rag_pipeline.py`), deployed free on Streamlit Community Cloud. Supports two modes: bundled-policy demo, and user-upload (runtime, per-session temp index — not Drive).
- Day 9: FastAPI backend exposing `POST /ask` (JSON) over the same `rag_pipeline.py`; repoint Streamlit to call the API over HTTP. Deploy on a free-tier host (verify current limits: HF Spaces / Render / Fly.io).

## Standing decisions & constraints

- All dev on `new_dev`; merge to `master` via PR at milestones (keeps the contribution graph current — the graph only counts commits on the default branch).
- Keep the whole project within the Gemini free tier. Note: on the free tier, content may be used to improve Google's products — fine for a sample policy, worth noting for real data.
- Privacy: the real policy PDF is intentionally NOT in the repo. Do not paste/commit real policy contents; keep committed eval keywords generic if a figure feels sensitive.
- App uploads should happen at runtime in the app (per-session temp index), not via a Drive folder.
- NB03/NB04 debugging is done in a Drive clone; remember to mirror any fixes back to the committed notebooks on `new_dev`.

## How to resume

1. Read this file. 2. `git checkout new_dev` (all work lives here). 3. Next actionable step is finishing the Day-5 calibration once a generation-capable key is available, then Day 6 (refactor to `rag_pipeline.py`). Commit new work to `new_dev` and open a PR to `master` when a milestone is done.
