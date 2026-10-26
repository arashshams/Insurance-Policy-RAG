# PLAN.md — Insurance-Policy-RAG: production upgrade plan and handoff

**Read this file first.** It is the single source of truth for the upgrade
of this project into a production-grade LLM system: the goal, the rules, the
current state, decisions already made (and why), the milestone plan with
acceptance criteria, and a progress log. It is written so that a new person
or agent can pick up the work without the conversation that produced it.

**Keep it current.** Every PR that advances the plan must also update the
status checkboxes and append to the [Progress log](#9-progress-log).

Last updated: 2026-10-26 (after M0)

---

## 1. Goal

Owner: Arash Shamseddini (GitHub `arashshams`), data scientist. This is his
public portfolio project.

Upgrade the existing RAG assistant (answers questions about an insurance
policy PDF, grounded in the document, cited by page, abstains with
"I don't know") into a production-grade LLM system that demonstrates:
rigorous evaluation, CI, experiment tracking, cloud deployment, privacy-safe
monitoring, and one agentic component.

**Target end state:** a containerized FastAPI backend deployed to the cloud,
called by the Streamlit app over HTTP; a large, versioned evaluation set with
LLM-as-judge scoring; evaluation in CI; MLflow experiment tracking;
privacy-safe monitoring with a dashboard; an agentic multi-document mode.

Final deliverables also include an updated README (architecture diagram,
evaluation report, deployment and monitoring sections) and 2–3 honest resume
bullets describing only what was actually built.

## 2. Non-negotiable rules

1. **Free by default.** Runs on the Gemini free tier and free/cheap hosting.
   Anything paid is optional and clearly documented.
2. **No sensitive content in the repo.** Never commit real policy content,
   user uploads, API keys or secrets. Use environment variables.
3. **Privacy guarantee for uploads.** Uploaded PDFs are never written to disk
   and are freed from memory (on file switch or after an idle TTL). Their
   text *is* sent to the Gemini API to embed and answer, and the app tells
   users so before upload. Do not weaken either half of this.
4. **One shared pipeline.** `src/rag_pipeline.py` is the only implementation
   of chunking, embedding, retrieval and generation. New features extend it;
   no duplicate code paths (notebooks, app, API, eval and agent all import it).
5. **Every quality claim comes from the evaluation harness**, with a results
   summary committed (see decision D2).
6. **Respect free-tier rate limits.** Evaluation calls are sequential, paced,
   cached and resumable.

## 3. Working conventions (how this project is run)

- **Plan before code.** For each milestone, propose a plan and wait for the
  owner's approval before writing code.
- **Branches and PRs.** One branch per milestone (or per sub-step for big
  milestones), small PRs with clear descriptions. `master` must stay working
  after every merge. Default branch: `master`.
- **Commit authorship.** All commits are authored *and* committed as
  `Arash Shamseddini <74572907+arashshams@users.noreply.github.com>`.
  **No AI attribution anywhere:** no `Co-Authored-By` trailers, no session
  links, no "Generated with" lines in commits or PR descriptions.
- **Explain design choices briefly** (in PR descriptions and the README) so
  the owner can defend them in interviews.
- **Tests are offline.** `pytest tests/` must pass with no API key and no
  network: embeddings and generation are faked. Anything needing Gemini goes
  in the evaluation harness, not the unit tests.
- **Who runs what.** Agents usually have no Gemini key. Evaluations, judge
  runs, sweeps and deploy checks are run by the owner on his machine and the
  output pasted back. Design every step so the owner can run it with one
  command.
- **Owner's local setup:** Windows, Git Bash, Miniforge, a conda env named
  `rag` with Python 3.11, repo cloned at `~/Downloads/RAG`. Notes:
  - `numpy==1.26.4` (pinned) has no wheels for Python >= 3.13; use 3.11.
  - In Git Bash: `export GEMINI_API_KEY="..."` (no spaces around `=`).
  - `make` is not installed by default on Windows (`conda install make`
    provides it); every Makefile target must also be documented as the plain
    command it runs.
  - Opening `app/demo_index/` with ChromaDB rewrites its files. After running
    the app or an evaluation locally, `git restore app/demo_index` before
    committing.
  - `Failed to send telemetry event ... capture() takes 1 positional
    argument` lines come from the pinned ChromaDB version and are harmless.
- **If the agent cannot push** (repo not authorized for the session), export
  commits with `git format-patch --stdout origin/master..HEAD > x.mbox`; the
  owner applies them with `git am x.mbox` on a new branch and opens the PR.

## 4. Current state (as of 2026-10-26, `master` @ PR #20)

### Architecture

```
PDF -> pypdf text per page -> scramble-ratio page filter
    -> chunking (cl100k_base, 800 tokens, overlap 128; per page, page kept in metadata)
    -> gemini-embedding-001 (3072-dim) -> ChromaDB (cosine)
    -> retrieve k=4, drop chunks with cosine distance > 0.37
    -> nothing left? -> "I don't know" (no LLM call)
    -> gemini-flash-latest, temperature 0, prompt: answer only from context,
       cite passage ids like [doc_12]; say exactly "I don't know" otherwise
    -> strip citation tags; pages = pages of cited passages
```

Gemini is called through its OpenAI-compatible endpoint with the `openai`
client. Transient errors (429, 5xx, connection errors, timeouts) are retried
with exponential backoff (`_call_with_backoff`); when retries run out,
`GeminiUnavailableError` is raised.

### Key files

| Path | What it is |
| --- | --- |
| `src/rag_pipeline.py` | The shared pipeline (config, embedding, index build, retrieval, generation, `is_abstention`, citations). |
| `src/evaluate.py` | Evaluation harness, CLI `python -m src.evaluate` (`--index`, `--pdf`, `--questions`, `--results`, `--no-cache`, `--max-age-days`, `--sleep`). |
| `src/guardrails.py` | `RateLimiter` (sliding window) and `UploadIndexRegistry` (idle TTL + cap for in-memory upload indexes). |
| `app/streamlit_app.py` | Streamlit UI: bundled-policy demo + per-session upload mode. Calls the API over HTTP for the demo when `INSURANCE_RAG_API_URL` is set. |
| `app/demo_index/` | Committed, pre-built Chroma index of the SAMPLE policy (38 chunks). |
| `api/main.py` | FastAPI: `GET /health`, `POST /ask` over the demo index; optional bearer token, rate limits, 503 on Gemini outage. Not deployed anywhere yet. |
| `notebooks/01`–`02` | Ingestion / indexing walkthroughs (still contain their own code; see backlog). |
| `notebooks/03_insurance_policy_rag.ipynb` | End-to-end walkthrough; imports the shared module. |
| `notebooks/04_evaluation.ipynb` | Notebook runner for `src/evaluate.py`. |
| `notebooks/eval/eval_questions.json` | Eval set v1: 12 in-scope + 6 out-of-scope. Each in-scope item has `expected_keywords` and `expected_pages`. |
| `tests/` | 42 offline tests (pipeline, guardrails, eval harness, API). |
| `.github/workflows/tests.yml` | CI: `ruff check` + `pytest` on push to `master`/`new_dev` and on PRs (Python 3.11). |
| `Makefile`, `requirements-dev.txt`, `ruff.toml` | Dev tasks (`make help`), pinned test/lint tools, lint config. |
| `.streamlit/config.toml` | Upload size cap. |

### Public API of `src/rag_pipeline.py` (use these, don't re-implement)

- `build_index_from_pdf(source, persist_dir=None, collection_name=None, source_name=..., max_pages=None, max_chunks=None) -> (collection, chunks)`
- `load_persistent_collection(persist_dir, collection_name)`, `drop_collection(collection)`
- `retrieve_top_k(collection, query, k, threshold) -> [ {id, text, metadata, score} ]`
- `answer_question(collection, question, k, model_name, threshold) -> (answer, pages, retrieved)`
- `answer_question_detailed(...) -> dict` with `answer, pages, retrieved, abstained, cited_ids, citations_verified, nearest_distance, threshold, model_requested, model_resolved, finish_reason`
- `is_abstention(answer)`, `extract_citations(answer, valid_ids)`
- Errors: `DocumentTooLargeError`, `GeminiUnavailableError`

All config is env-overridable (`INSURANCE_RAG_*`; see the Config section of
the module, `src/guardrails.py`, `app/README.md`, `api/README.md`).

### Latest evaluation results (owner's run after PR #20)

Shipped demo index, `gemini-flash-latest`, eval set v1 (12 in + 6 out):

- Out-of-scope abstention 100% (6/6): 4 stopped by the distance threshold,
  2 near-misses (`out_05` pet vet bills at 0.335, `out_06` Manulife mortgage
  at 0.366) passed the threshold and were refused by the model.
- In-scope: 12/12 answered; retrieval hit, retrieval page, citation page and
  keyword rates all 100%.
- Closest-passage distance: in-scope max 0.344 (`in_06`), out-of-scope min
  0.335 (`out_05`); the sets overlap, so no threshold alone separates them.
- Close to the cutoff: `in_01` 0.336, `in_06` 0.344 (in-scope); `out_04`
  0.397 (out-of-scope).

### Known limitations

- 0.37 is calibrated on one sample policy only; uploads use
  `INSURANCE_RAG_UPLOAD_THRESHOLD` (defaults to 0.37) and the UI warns about it.
- `gemini-flash-latest` is a moving alias and the endpoint does not report
  the version behind it; eval cache entries expire after 14 days.
- Eval set v1 is small (18 questions), single policy, keyword-based scoring.
- Pinned deps are old (`openai==1.14.3`, `chromadb==0.4.24`,
  `httpx==0.27.2` held back for openai compatibility).

## 5. Decisions made (and why)

| ID | Decision | Why | Status |
| --- | --- | --- | --- |
| D1 | Keep the distance threshold at **0.37**. | Latest run: near-miss out-of-scope questions overlap real ones (0.335 vs up to 0.344); lowering the cutoff would reject real questions. The model's refusal handles near-misses ("two-layer guardrail"). | Decided |
| D2 | Raw eval cache `notebooks/eval/eval_results.json` stays git-ignored; commit a **versioned summary per run** instead (`eval/reports/<set-version>_<date>.md` + small metrics JSON). | Satisfies rule 5 without churning a large cache file. | Proposed, awaiting owner confirmation |
| D3 | **M4 option (a):** upload mode keeps running inside the Streamlit process; the deployed API serves the bundled demo policy. | Cloud hosts may run several instances and stop idle ones, so per-session in-memory indexes on the API would vanish or hit the wrong instance. Alternatives: (b) single-instance API with expiring upload session IDs, (c) re-embed per request (private but costly). | Proposed, awaiting owner confirmation |
| D4 | LLM judge uses a **pinned** model version, ideally different from the generator. | `-latest` aliases make judge scores drift; a different model reduces self-grading bias. Judge agreement is spot-checked by hand. | Proposed (part of M1 plan) |
| D5 | MLflow **wraps the existing harness** (logs its config + metrics) instead of a second eval path. | Rule 4 / single source of metrics. | Proposed (part of M3 plan) |
| D6 | Threshold/k sweeps reuse cached query embeddings and passage distances; only configurations that change what is retrieved need new generation calls. | Stay inside free-tier limits. | Proposed (part of M3 plan) |
| D7 | Lint with **ruff** (pinned in `requirements-dev.txt`), config in `ruff.toml`; notebooks excluded from lint. | Fast, one tool; notebooks contain Colab shell/magic lines. | Done in M0 |

## 6. Milestones

Status legend: `[x]` done, `[ ]` not started, `[~]` in progress.

Estimated pace: ~15 PRs over ~2 weeks of part-time days. Owner time per day
is mostly review and running evals (30–90 min). Schedule:

| Day | PRs |
| --- | --- |
| 1 | M0; M1a |
| 2 | M1b |
| 3 | M1c |
| 4 | M1d; M2 |
| 5 | M3 |
| 6–7 | M4 |
| 8 | M5 |
| 9–11 | M6 |
| 12 | Final README + resume bullets |

### M0. Housekeeping — `[x]`

Already done before this plan: `PROJECT_CONTEXT.md` removed; Colab badges
point to `master`; `requirements.txt` pinned.

- [x] `PLAN.md` (this file).
- [x] Makefile: `help`, `setup`, `test`, `lint`, `eval` (`ARGS=` passes
  flags), `run-app`, `run-api`, `restore-index`, `clean`; `make help` shows
  the plain command behind each target. No `format` target on purpose: a
  repo-wide reformat would bury real changes in diffs.
- [x] `requirements-dev.txt` (pytest, ruff), `ruff.toml`, lint step in CI.
- [x] README "Getting started" uses the Makefile and lists the plain commands.

Acceptance: `make setup test lint` works on Linux/macOS and in CI; README
"Getting started" mentions the Makefile and the plain commands.

### M1. Evaluation 2.0 (highest priority) — `[ ]`

**M1a — eval set v2 (data only).**
- New versioned file `eval/questions_v2.json` (v1 stays in place until the
  harness switches over), ~60 items.
- Each item: `id`, `category`, `question`, `expected_pages`,
  `reference_answer` (short, written from the sample policy), optional
  `expected_keywords`, `notes`. Out-of-scope items: `category` plus
  `notes`; expected answer is "I don't know".
- Categories: `direct_fact`, `paraphrase`, `numeric`, `multi_part`,
  `multi_chunk` (answer spans passages/pages), `near_miss_oos`,
  `clear_oos`, `adversarial` (e.g. "ignore the policy and ..." or
  prompt-injection style questions).
- Pages and facts verified against the demo index text
  (`app/demo_index/chroma.sqlite3`, table `embedding_metadata`, key
  `chroma:document`; page in key `page`).
- Owner reviews every question and reference answer (this is ground truth).

**M1b — judge-free metrics + report.**
- Abstention precision/recall (positive class = "should abstain").
- Retrieval hit rate and recall@k vs `expected_pages`.
- Citation accuracy (cited pages are among `expected_pages`).
- Per-category breakdown; `make eval` writes a markdown report.

**M1c — LLM-as-judge.**
- Faithfulness (answer supported by retrieved text) and correctness (vs
  `reference_answer`), integer scale with rubric; prompt versioned in a file
  (e.g. `eval/prompts/judge_v1.md`).
- Pinned judge model (D4); judge calls cached and paced like the rest.
- Hand-scoring sheet for ~20 sampled items; report judge–human agreement.

**M1d — committed report + failure analysis.**
- `eval/reports/<set-version>_<date>.md` (+ metrics JSON) per D2; README
  links the latest report.

Acceptance: one command produces the full report; every number in the
README traces to a committed report.

### M2. Tests and CI — `[ ]`

Mostly done already (42 offline tests; CI on push/PR). Remaining:
- Unit tests for any new M1 code (metrics, judge parsing) — offline.
- Smoke eval on PRs: 10–15 questions from v2 incl. all out-of-scope
  categories, with gates (e.g. out-of-scope abstention must stay 100%,
  in-scope answered >= threshold). Needs repo secret `GEMINI_API_KEY`
  (owner adds it). Skip gracefully when the secret is unavailable
  (e.g. PRs from forks).
- Full eval: manual (`workflow_dispatch`) and/or weekly schedule.

### M3. Experiment tracking with MLflow — `[ ]`

- Log each configuration (chunk size, overlap, k, threshold, embedding and
  generation models, prompt version, eval set version) with the full eval
  metrics as an MLflow run; local file store by default (`mlruns/`,
  git-ignored), optional remote tracking URI.
- Small calibration sweep over threshold and k (D6); write up why the chosen
  config wins.
- Version prompts (generation and judge) alongside configs.

### M4. Containerized cloud deployment — `[ ]`

- Dockerfile for the FastAPI backend (health check, request validation
  already exist).
- Deploy to a free/cheap host (candidates: Google Cloud Run, Render, Fly.io,
  Hugging Face Spaces; verify current free-tier terms at the time).
  Document step by step; set `GEMINI_API_KEY` and `INSURANCE_RAG_API_TOKEN`
  as host secrets.
- Streamlit app calls the deployed API for the demo (`INSURANCE_RAG_API_URL`
  + token already supported); local in-process fallback stays for dev.
- Upload mode per D3.

### M5. Monitoring (privacy-safe) — `[ ]`

- Per request log: timestamp, latency, abstained, abstention layer
  (threshold vs model), top retrieval score, number of chunks retrieved,
  model and prompt version. Never log document text; never log raw
  questions from upload mode (demo-mode questions only if documented).
- Storage: cloud containers lose local files, so pick a free external store
  (host's structured logging, or a small free hosted DB). Decide in the M5
  plan.
- Streamlit dashboard page: latency, abstention rate, score drift.

### M6. Agentic multi-document mode — `[ ]`

- Multi-document support in the shared pipeline (document id in metadata,
  per-document retrieval).
- Second public document: a clearly labeled **fictional** amendment or
  Schedule of Benefits written to match the sample policy (real ones can't
  be committed).
- Small agent (e.g. LangGraph) with tools: retrieve-from-document,
  compare-across-documents, abstain. Must cite pages and abstain without
  evidence.
- Extend the eval set with multi-document questions; agent mode must not
  regress single-document metrics.

### Optional: Databricks variant — `[ ]`

Only if wanted later: Databricks-managed MLflow and/or Databricks Vector
Search as an alternative backend. Default path stays free and portable.

### Final — `[ ]`

README: architecture diagram, evaluation report, deployment and monitoring
sections. 2–3 resume bullets, describing only what was built.

## 7. Backlog (not scheduled)

- Upgrade pinned dependencies (`openai`, `chromadb`, `httpx`). A new ChromaDB
  may not open the committed demo index; rebuilding it costs one embedding
  pass with the SAMPLE PDF (not in the repo; the owner has it).
- Move notebooks 01 and 02 onto the shared module.
- Escape/delimit policy text in the prompt (prompt-injection hardening; low
  risk for this project; the M1 `adversarial` category will measure it).
- Calibrate on a real (private) policy with `python -m src.evaluate --pdf`.

## 8. How to resume (checklist for a new agent)

1. Read this file, then `README.md`, `src/rag_pipeline.py`, `src/evaluate.py`.
2. `git log --oneline -15` and open PRs on GitHub to see what moved since the
   progress log was last updated.
3. Set up: Python 3.11, `make setup` (or
   `pip install -r requirements.txt -r requirements-dev.txt`), then
   `make test` must pass.
4. Find the first unchecked item in [Milestones](#6-milestones); if it has no
   approved plan, propose one and wait for approval.
5. Follow [Working conventions](#3-working-conventions-how-this-project-is-run)
   (authorship, no AI attribution, offline tests, owner runs Gemini calls).
6. At the end of each PR: update checkboxes, decisions and the progress log.

## 9. Progress log

- **2026-10-23 — PR #19 (merged).** Review fixes: honest upload privacy
  wording; idle-upload TTL and caps; API token + rate limits; citations from
  cited passages; single `is_abstention`; eval with expected pages, page
  metrics, distance margin, `--pdf` calibration; notebook 03 on the shared
  module; README/docs synced.
- **2026-10-26 — PR #20 (merged).** Retry transient Gemini errors (5xx,
  connection, timeouts) + API 503 with Retry-After; eval re-scores cached
  answers; reports threshold vs model-refusal abstentions; `in_07` keywords
  fixed; README results + two-layer guardrail explanation; eval cache
  git-ignored. Owner's eval run: all metrics 100% (see section 4).
- **2026-10-26 — branch `m0-housekeeping`.** Added this `PLAN.md`. M0:
  Makefile, `requirements-dev.txt` (pytest 8.3.3, ruff 0.6.9), `ruff.toml`
  (defaults + intentional E402 exceptions), lint step in CI, README setup
  section. **Next: M1a** (eval set v2; propose the plan first).
