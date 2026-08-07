# Project Context & Handoff — Insurance-Policy-RAG

> Working notes so development can resume cleanly after a break or a closed tab.
> Last updated: 2026-08-07. All development happens on the `new_dev` branch.

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
- Day 6 (refactor, DONE): consolidated the pipeline into `src/rag_pipeline.py` — env-overridable config (dev-persistent vs app-ephemeral), Gemini client factory + embed_query/embed_texts, dual-mode `build_index_from_pdf` (path or bytes; in-memory for shipped app), and `retrieve_top_k`/`answer_question` (0.37 threshold, IDK short-circuit, get_client for generation). Sanity-checked in Colab: 37 chunks, in-scope answered with citations, out-of-scope abstains with 0 hits.
- Day 7 (documentation, DONE): rewrote the README grounded in this file (purpose, scope, architecture, config table, two runtime modes, pipeline interface, repo layout, getting-started + programmatic usage, sample-policy note, eval results, responsible-AI, roadmap); added an architecture/workflow diagram (`img/architecture.svg`) embedded on the README front page; added Contributions + License sections; added an MIT `LICENSE` file. All committed to `new_dev`; opened PR #8 (`new_dev` -> `master`).
- Day 8 (Streamlit MVP, DONE): built `app/streamlit_app.py` (thin UI over `src/rag_pipeline.py`) in incremental commits on `new_dev` — scaffolding+config, requirements, bundled-policy demo mode (loads a pre-built on-disk Chroma index, no startup embedding), per-session in-memory upload mode (persists nothing), set_page_config ordering + guarded `st.secrets` (clean local run), and UX polish (API-key guard/hint, empty-query guard, clearer abstention, how-it-works). Committed the pre-built demo index at `app/demo_index/` (SAMPLE FlexCare). Local Python 3.11 build produced 38 chunks vs 37 on Colab — environment-sensitive by ~1 chunk (tokenizer/PDF-extractor versions), same on-spec settings (cl100k_base/800/128); both valid.
- Day 9 (FastAPI backend, DONE): added `api/main.py` exposing `POST /ask` and `GET /health` over `src/rag_pipeline.py` (loads the bundled demo index once at startup, returns grounded page-cited answers with an `abstained` flag). Added `api/README.md` (endpoints, run, config, free-tier deploy). Repointed the Streamlit app to optionally answer demo questions via the API over HTTP when `INSURANCE_RAG_API_URL` is set (falls back to the in-process pipeline otherwise; upload mode stays in-process). Added fastapi/uvicorn/requests to requirements. All incremental commits on `new_dev`.

## Roadmap — remaining

- **Day 5 calibration: COMPLETE.** All in-scope eval questions have ground-truth `expected_keywords`; pipeline validated end-to-end on free tier. (Merged via PR #5; final keyword fills in PR #6.) Optional later tweak: adjust any keyword found too strict/loose on a future eval run - normal tuning, not a redo.
- **Day 6: COMPLETE.** Notebook logic refactored into a single importable module `src/rag_pipeline.py` (4 sections: config, client+embeddings, dual-mode index builder, retrieval+generation). Index-building exposed as `build_index_from_pdf(source, persist_dir=None)` — accepts a path OR uploaded bytes, NOT hard-wired to Drive. Two runtime modes: dev-persistent (on-disk Chroma + optional chunks.json) and app-ephemeral (in-memory, nothing persisted). All calibrated values preserved; verified end-to-end on free tier. (Carried in PR to `master`.)
- **Day 7: COMPLETE.** High-quality README + documentation delivered (eval results carried as the quality story), architecture diagram embedded, Contributions/License sections, and an MIT `LICENSE` file. Carried in PR #8 (`new_dev` -> `master`).
- **Day 8: COMPLETE.** Streamlit MVP (`app/streamlit_app.py`) importing `rag_pipeline.py`, with two modes: bundled-policy demo (pre-built on-disk index at `app/demo_index/`, no startup embedding) and user-upload (per-session in-memory index, persists nothing). Deploy docs at `app/README.md`. Ready for Streamlit Community Cloud (entry point `app/streamlit_app.py`, `GEMINI_API_KEY` in Secrets). All on `new_dev`.
- **Day 9: COMPLETE.** FastAPI backend (`api/main.py`) exposing `POST /ask` + `GET /health` over `rag_pipeline.py`; Streamlit can call it over HTTP via `INSURANCE_RAG_API_URL` (optional, backward-compatible). Docs in `api/README.md`. Actual free-tier deployment (HF Spaces / Render / Fly.io) is a user-side follow-up (account/hosting step). All on `new_dev`.

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
numpy==1.26.4 pypdf==4.2.0 tiktoken==0.7.0 langchain-text-splitters==0.2.4
openai==1.14.3 chromadb==0.4.24 tqdm==4.66.4 httpx==0.27.2
```
A runtime recycle wipes BOTH the pip packages AND the Drive mount — reinstall pins, restart, then `drive.mount('/content/drive')`.

Outstanding to finish calibration (needs daily quota reset): run NB03 then NB04 (via `%run` of NB03 in NB04's kernel), record answers for in_04-in_08, fill their `expected_keywords`, commit to `new_dev`.

## Paused — 2026-07-29 (calibration complete)

Day-5 calibration is finished. All eight in-scope eval questions now have `expected_keywords` (committed on `new_dev`). Open **PR #6** (`new_dev` -> `master`) carries the final keyword fills for in_04-in_08; **not merged** (maintainer's call). PR #5 (earlier calibration work) was already merged.

Eval snapshot: out-of-scope abstention 100%, in-scope retrieval hit 100%, in_02 abstains by design (correct guardrail). Model `gemini-flash-latest` on free tier; runs sequential + paced.

Colab gotchas learned this session (re-apply after ANY runtime recycle): the recycle wipes BOTH pip packages AND the Drive mount, and silently reverts numpy to 2.x. Recipe: reinstall pins -> Runtime>Restart session -> `drive.mount('/content/drive', force_remount=True)`. The Drive mount also drops intermittently mid-session; if a path check returns False/empty, just force_remount and retry. The notebooks live at `/content/drive/MyDrive/Insurance-Policy-RAG_Old/Insurance-Policy-RAG/notebooks/`; the data root (chunks.json, chroma, eval/) is the top-level `/content/drive/MyDrive/Insurance-Policy-RAG/`. Chroma collection name: `insurance_policy_cvdb` (37 docs, 3072-dim Gemini embeddings).

To capture eval answers without the fragile whole-file `%run`: load NB03's code cells via `exec` (skipping the build cells and the broken `query_texts` diagnostic cell), then loop `answer_question` over `eval_questions.json['in_scope']` with a short sleep between calls.

Next milestone: **Day 6** — `rag_pipeline.py` refactor (see resume step 3 above).

## Paused — 2026-07-30 (Day 6 complete)

Day-6 refactor is DONE and committed to `new_dev` in four incremental commits (config, client+embeddings, index builder, retrieval+generation). `src/rag_pipeline.py` is now a self-contained, importable module (~457 lines) with no hard `google.colab` dependency (lazy secret fallback) and no hard Drive path (env-overridable).

Architecture confirmed this session: DEV mode builds a persistent on-disk Chroma index (+ optional dev-only chunks.json); SHIPPED APP mode embeds the user-uploaded PDF straight into an in-memory (ephemeral) Chroma collection and persists NOTHING to disk (privacy + no reason to store a stranger's document). Same code path via `build_index_from_pdf(source, persist_dir=...)`.

Sanity-checked end-to-end in Colab against the sample policy: 37 chunks (matches calibration), in-scope query answered with page citations (top distance ~0.336), out-of-scope query returns "I don't know" with 0 hits via the pre-LLM short-circuit. Calibrated values all intact (chunking cl100k_base/800/128, cosine space, 0.37 threshold, temperature 0.0).

Open PR (`new_dev` -> `master`) carries the Day-6 module + this context update; **not merged** (maintainer's call). Next up: Day 7 (README/documentation, using the eval results as the quality story).

## Paused — 2026-08-04 (Day 7 complete)

Day-7 documentation is DONE and committed to `new_dev`. The README was rewritten from this PROJECT_CONTEXT to a high-quality state: project purpose and scope (what it does / does not do), architecture overview + a configuration table, the two runtime modes (dev-persistent vs app-ephemeral), the pipeline interface (`retrieve_top_k` / `answer_question`), repository layout, getting-started + programmatic-use snippets, the sample-policy calibration note, the evaluation results (out-of-scope abstention 100%, in-scope retrieval hit 100%, 7/8 in-scope answered — the one non-answer correct by design), responsible-AI notes, and the roadmap.

A schematic workflow diagram was created at `img/architecture.svg` (PDF -> chunking -> Gemini embeddings -> ChromaDB -> thresholded retrieval -> guardrailed answer generation) and embedded on the README front page. Contributions and License sections were added to the README (plain headings, matching the style of other repos in the profile), and a real MIT `LICENSE` file was added ("Copyright (c) 2026 Arash Shamseddini") so the README license link resolves.

Privacy preserved throughout: no real policy contents committed; the real policy PDF stays out of the repo; all numbers reference the published SAMPLE-watermarked stand-in only.

Open **PR #8** (`new_dev` -> `master`) carries all Day-7 changes (README, `img/architecture.svg`, `LICENSE`); **not merged** (maintainer's call). Next up: Day 8 (Streamlit MVP app importing `rag_pipeline.py`, deployed on Streamlit Community Cloud, with bundled-policy demo + per-session user-upload modes).

## Paused — 2026-08-06 (Day 8 complete)

Day-8 Streamlit MVP is DONE and committed to `new_dev` in incremental commits. `app/streamlit_app.py` is a thin UI over `src/rag_pipeline.py` with two modes: (1) bundled-policy demo that loads a pre-built on-disk Chroma index from `app/demo_index/` with no embedding calls at startup (free-tier friendly), and (2) user-upload that builds a per-session in-memory (ephemeral) index and persists nothing (privacy). Commit sequence: scaffolding+config -> requirements -> demo mode -> upload mode -> set_page_config ordering fix -> guarded `st.secrets` (no "No secrets files found" spam on local runs) -> UX polish (API-key guard/hint, empty-query guard, clearer "I don't know" abstention, "how it works" expander) -> deploy docs (`app/README.md`) -> this context update.

Demo index: the pre-built index is committed at `app/demo_index/` (a `chroma.sqlite3` + a UUID-named subfolder), built from the published SAMPLE-watermarked Manulife FlexCare PDF. NOTE ON CHUNK COUNT: the local Python 3.11 build produced **38** chunks, vs **37** on the original Colab calibration. Settings are identical and on-spec (cl100k_base / 800 / 128, cosine, 0.37 threshold); the ±1 difference is environment-sensitive (tiktoken / PDF-extractor versions). Both are valid — 38 is the current on-disk demo index. Verified end-to-end: demo mode loads the committed index and returns page-cited answers; "Demo index not found" no longer appears.

Environment notes learned this session: on a fresh local env, run notebooks with the `insurance-rag` kernel (register via `python -m ipykernel install --user --name insurance-rag`), not `base`, or imports like `openai` fail. On Windows, Chroma keeps the demo-index `.bin` files open while the app or a notebook kernel is alive; stop the app and shut the kernel down before any `git` op that touches `app/demo_index/` (rebase/checkout), or unlink fails and the working tree files get locked. `policy.pdf` and the scratch `runner.ipynb` are gitignored — never commit either; only the SAMPLE-watermarked policy and its derived index belong in the repo.

Next up: Day 9 — FastAPI backend exposing `POST /ask` (JSON) over the same `rag_pipeline.py`, then repoint Streamlit to call the API over HTTP. Deploy on a free-tier host (verify current limits: HF Spaces / Render / Fly.io).


## Paused — 2026-08-07 (Day 9 complete)

Day-9 FastAPI backend is DONE and committed to `new_dev` in incremental commits: requirements (fastapi/uvicorn/requests) -> `api/main.py` -> `api/README.md` -> Streamlit API-mode repoint -> this context update.

Backend (`api/main.py`): a thin ASGI app over `src/rag_pipeline.py`. `GET /health` reports service/index/API-key status without calling the LLM. `POST /ask` takes `{question, k?}` and returns `{answer, pages, abstained, retrieved}`, where `abstained` is true on the IDK short-circuit. The bundled demo index (`app/demo_index/`) is opened ONCE at process start and reused; requests persist nothing. Missing key -> HTTP 503; missing index -> HTTP 503; pipeline error -> HTTP 502. `DEMO_INDEX_DIR` overrides the index path. Run: `uvicorn api.main:app --reload`; interactive docs at `/docs`.

Streamlit repoint: when `INSURANCE_RAG_API_URL` is set, demo mode POSTs to `{url}/ask` (via `requests`) and normalizes the reply back to the in-process `(answer, pages, retrieved)` shape, so the UI is identical either way. When unset, the app is byte-for-byte the old behavior (opens the local demo index). Upload mode ALWAYS runs in-process (the API only serves the bundled demo policy). The key requirement is relaxed in API mode since the key lives on the server.

Not done yet (user-side): actual deployment of the backend to a free-tier host and pointing the Streamlit app at it. Both are account/hosting actions. Backend and app both verified to import/start locally; end-to-end HTTP path exercised via `/docs` / curl is recommended before deploying.

Roadmap status: Days 1-9 COMPLETE. This was the last planned build day; remaining work is deployment + any polish/tuning.
