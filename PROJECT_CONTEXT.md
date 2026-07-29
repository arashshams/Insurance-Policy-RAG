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
- `EMBED_MODEL = gemini-embedding-001`; `GEN_MODEL = gemini-flash-latest` (both FREE-tier eligible). NOTE: gemini-2.5-flash is retired for new keys and gemini-2.0-flash returns limit 0 (no free generation quota) on this account; the gemini-flash-latest alias has live free-tier generation quota, so GEN_MODEL points there.
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
- Day 5 (calibration, DONE): GEN_MODEL=`gemini-flash-latest` (only free-tier generation model still responding). Pinned `httpx==0.27.2`. Ran NB01 (37 chunks) -> NB02 (index) -> NB03 (real answers) -> full in-scope eval. Results: out-of-scope abstention 100%, in-scope retrieval hit 100%, 7/8 in-scope answered (in_02 abstains BY DESIGN - the annual drug maximum is in the separate Schedule of Benefits, not this policy). Filled `expected_keywords` for ALL in-scope questions in_01-in_08 (no TODOs left).

## Roadmap — remaining

- **Day 5 calibration: COMPLETE.** All in-scope eval questions have ground-truth `expected_keywords`; pipeline validated end-to-end on free tier. (Merged via PR #5; final keyword fills in PR #6.) Optional later tweak: adjust any keyword found too strict/loose on a future eval run - normal tuning, not a redo.
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

1. Read this file. 2. `git checkout new_dev`. 3. Day-5 calibration is DONE. Next actionable step is **Day 6**: refactor the notebook pipeline into a plain `rag_pipeline.py` module (single shared config block) exposing index-building as a callable parameterized by PDF source (NOT hard-wired to the Drive path) so the app can do runtime uploads. If you need to re-run notebooks, apply the Colab env recipe below, remount Drive, then run in order.


## Paused — 2026-07-28 (resume recipe)

Paused for the day at the free-tier DAILY generation cap. Open PR #5 (`new_dev` -> `master`) carries today's changes: GEN_MODEL=gemini-flash-latest, httpx pin, eval-question fixes. **PR #5 is not merged** — merge is the maintainer's call.

Colab env recipe (re-apply after ANY runtime recycle, then Restart session, then remount Drive):
```
numpy==1.26.4  pypdf==4.2.0  tiktoken==0.7.0  langchain-text-splitters==0.2.4
openai==1.14.3  chromadb==0.4.24  tqdm==4.66.4  httpx==0.27.2
```
A runtime recycle wipes BOTH the pip packages AND the Drive mount — reinstall pins, restart, then `drive.mount('/content/drive')`.

Outstanding to finish calibration (needs daily quota reset): run NB03 then NB04 (via `%run` of NB03 in NB04's kernel), record answers for in_04-in_08, fill their `expected_keywords`, commit to `new_dev`.


## Paused — 2026-07-29 (calibration complete)

Day-5 calibration is finished. All eight in-scope eval questions now have `expected_keywords` (committed on `new_dev`). Open **PR #6** (`new_dev` -> `master`) carries the final keyword fills for in_04-in_08; **not merged** (maintainer's call). PR #5 (earlier calibration work) was already merged.

Eval snapshot: out-of-scope abstention 100%, in-scope retrieval hit 100%, in_02 abstains by design (correct guardrail). Model `gemini-flash-latest` on free tier; runs sequential + paced.

Colab gotchas learned this session (re-apply after ANY runtime recycle): the recycle wipes BOTH pip packages AND the Drive mount, and silently reverts numpy to 2.x. Recipe: reinstall pins -> Runtime>Restart session -> `drive.mount('/content/drive', force_remount=True)`. The Drive mount also drops intermittently mid-session; if a path check returns False/empty, just force_remount and retry. The notebooks live at `/content/drive/MyDrive/Insurance-Policy-RAG_Old/Insurance-Policy-RAG/notebooks/`; the data root (chunks.json, chroma, eval/) is the top-level `/content/drive/MyDrive/Insurance-Policy-RAG/`. Chroma collection name: `insurance_policy_cvdb` (37 docs, 3072-dim Gemini embeddings).

To capture eval answers without the fragile whole-file `%run`: load NB03's code cells via `exec` (skipping the build cells and the broken `query_texts` diagnostic cell), then loop `answer_question` over `eval_questions.json['in_scope']` with a short sleep between calls.

Next milestone: **Day 6** — `rag_pipeline.py` refactor (see resume step 3 above).
