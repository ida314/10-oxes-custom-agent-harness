# TODO — Career Agent Harness System

> Read `docs/STATE.md` before starting work. Update this file and `docs/STATE.md` after meaningful changes.

---

## Phase 0 — Eval Benchmark

- [x] Create `evals/datasets/job_tracker_seed.jsonl` (50 cases, 5 companies)
- [x] Create `evals/metrics/job_tracker_metrics.py` (6 scoring functions + CLI)
- [x] Create `evals/datasets/search/job_tracker_search.jsonl` (search split, ~40 cases)
- [x] Create `evals/datasets/test/job_tracker_test.jsonl` (held-out split, ~10 cases — never expose to optimizer)
- [x] Create `evals/datasets/article_signal_seed.jsonl` (article intelligence cases, needed before Phase 4)
- [x] Add `evals/metrics/__init__.py` and `pyproject.toml` to make metrics installable

---

## Phase 1 — Data Layer ✓ COMPLETE

- [x] Create `pyproject.toml` with deps: SQLModel, Alembic, Pydantic v2, pytest, httpx, python-dotenv
- [x] Create `docker-compose.yml` with Postgres + pgAdmin
- [x] Create `.env.example`
- [x] Create `.venv` with uv (Python 3.12)
- [x] Create `db/models.py` with all 15 tables:
  - [x] `companies`
  - [x] `company_sources`
  - [x] `jobs` (UNIQUE on url + normalized_hash; compound indexes)
  - [x] `events`
  - [x] `articles`
  - [x] `people`
  - [x] `applications`
  - [x] `application_packets`
  - [x] `skills`
  - [x] `harness_candidates`
  - [x] `agent_runs`
  - [x] `tool_calls`
  - [x] `trace_events`
  - [x] `eval_scores`
  - [x] `approval_items`
- [x] Create `db/migrations/` with initial Alembic migration (hand-written; runs when Postgres is up)
- [x] Create `scripts/seed_companies.py` (seeds Google, Datadog, Ramp, Jane Street, Stripe)
- [x] Create `tests/test_db_models.py` — 10 tests all passing (SQLite in-memory)
- [x] All tests pass: `pytest tests/test_db_models.py` → 10/10

---

## Phase 2 — Deterministic Source Connectors + Skill Library v0 ✓ COMPLETE

- [x] Define `SkillResult`, `NormalizedJob`, `Evidence`, `RunContext`, `Skill` in `skills/base.py`
- [x] Create `skills/ats/greenhouse/` (skill.py, metadata.yaml, __init__.py)
- [x] Create `skills/ats/lever/` (skill.py, metadata.yaml, __init__.py)
- [x] Create `skills/ats/ashby/` (skill.py, metadata.yaml, __init__.py)
- [x] Create `skills/company_research/find_careers_page/`
- [x] Create `skills/company_research/find_engineering_blog/`
- [x] Create `skills/company_research/find_events/`
- [x] Create `skills/company_research/find_recent_articles/`
- [x] Create `tests/fixtures/` (greenhouse, lever, ashby, careers_page)
- [x] Create `tests/test_ats_connectors.py` — 21 tests, 0 live network calls
- [x] All 31 tests pass: `pytest tests/` → 31/31

---

## Phase 3 — Job-Discovery Harness v0 ✓ COMPLETE

- [x] Create `harnesses/job_discovery/v0.py` — `run_company_scan(company_id, profile_id, config) -> CompanyScanReport`
- [x] ATS-first (Greenhouse/Lever/Ashby) → careers-page fallback logic
- [x] Job normalization and deduplication by normalized_hash
- [x] Heuristic entry-level scoring (title keyword matching)
- [x] Heuristic fit scoring (skill keyword overlap)
- [x] Stub recommendations (apply/research/skip, no LLM)
- [x] Stub validators via `harnesses/validators/job.py`
- [x] Trace logging to `experiments/runs/{timestamp}/` (TraceLogger)
- [x] DB writes (skipped in dry_run=True mode)
- [x] Create `tests/test_job_discovery_harness.py` — 8 tests passing
- [x] 39/39 total tests passing

---

## Phase 4 — Article / Company Intelligence Scoring ✓ COMPLETE

- [x] Create `harnesses/article_discovery/v0.py`
- [x] 8 signal types: hiring, technical, culture, strategy, interview_prep, networking, risk, irrelevant
- [x] Application angle, interview question, outreach angle generation
- [x] Source grounding check in `harnesses/validators/article_signal.py`
- [x] LLM path (claude-haiku) + heuristic fallback (no API key needed)
- [x] Prompt template: `prompts/article_signal_classify.txt`
- [x] Retry on validation failure (up to max_retries)
- [x] Full trace per article (prompt → response → validation → signal)

---

## Phase 5 — Trace Filesystem + Experiment Logging ✓ COMPLETE

- [x] `app/tracing/logger.py` — `TraceLogger` class
- [x] Per-run directory: `experiments/runs/{ISO_TIMESTAMP}_{harness}_{version}/`
- [x] `log()`, `log_failure()`, `save_config()`, `save_output()`, `save_metrics()`, `snapshot_harness_source()`
- [x] `failures/` subdirectory per run
- [x] `tests/test_trace_logger.py` — 8 tests passing

---

## Phase 6 — Evaluation Runners ✓ COMPLETE

- [x] `evals/runners/evaluate_job_discovery.py` — 40-case search split, test gated
- [x] `evals/runners/evaluate_article_signals.py` — 15-case article signal eval, test gated
- [x] Search/test split enforcement (`allow_test=True` required for test split)
- [x] `metrics.json` output per eval run
- [x] Tests: `test_article_discovery.py::TestEvalRunner` — 6 tests passing

---

## Phase 7 — AutoHarness-Style Validators ✓ COMPLETE

- [x] `harnesses/validators/base.py` — `ValidationResult` with `merge()`
- [x] `harnesses/validators/job.py` — `is_valid_job`, `is_safe_to_apply`, `entry_level_score`
- [x] `harnesses/validators/article_signal.py` — `is_valid_article_signal`
- [x] `harnesses/validators/recommendation.py` — `is_valid_recommendation`, `is_safe_application_recommendation`
- [x] `harnesses/validators/application_packet.py` — `is_valid_application_packet` (no fabrication, no altered facts, auto-submit blocked)
- [x] `harnesses/validators/browser_action.py` — `is_allowed_browser_action`, `is_safe_page_state`
- [x] `harnesses/validators/retry.py` — `validate_with_retry` with feedback propagation
- [x] `tests/test_validators.py` — 53 tests, all passing, pure Python

---

## Phase 8 — Meta-Harness Optimizer Loop v0 ✓ COMPLETE

- [x] `optimizers/meta_harness_loop.py` — full loop: bootstrap → evaluate → stub-propose → validate → score → Pareto update
- [x] `skills/meta_harness/propose_job_harness.md` — proposer skill with read/write permissions documented
- [x] `experiments/candidates/index.json` — candidate registry
- [x] Pareto frontier tracking across 6 objectives (minimize unsafe, maximize recall/precision/accuracy/acceptability)
- [x] 5 loop iterations produce valid candidates (dry_run mode; real proposer requires ANTHROPIC_API_KEY)
- [x] Write permissions restricted: optimizer writes only to `harnesses/*/candidates/` and `notes/`

---

## Phase 9 — AutoHarness Tree Search ✓ COMPLETE

- [x] `optimizers/search_controller.py` — `SearchController` + `select_candidate_thompson`
- [x] Thompson sampling via `random.betavariate(successes+1, failures+1)`
- [x] Weighted multi-objective score: 6 metrics with signed weights
- [x] Parent-child lineage tracked in `CandidateRecord.parent_id`
- [x] Thompson selects high-performers more often but preserves exploration (tested over 100 draws)
- [x] `tests/test_meta_harness.py` — 21 tests passing

---

## Phase 10 — Application Packet Generation ✓ COMPLETE

- [x] `harnesses/application_packet/v0.py` — full packet generation pipeline
- [x] Cover letter draft (LLM path + heuristic fallback)
- [x] Resume tailoring suggestions (skill × job-description matching + signal angles)
- [x] Short-answer drafts for required questions (heuristic templates + LLM)
- [x] Referral request draft
- [x] Interview prep notes from article signals
- [x] `is_valid_application_packet` validator wired in (no fabrication, no altered facts)
- [x] `validate_with_retry` wired in (retries on validation failure, routes to human on exhaustion)
- [x] `approval_status` always `"pending"` — never `"auto"`
- [x] `evals/runners/evaluate_application_packet.py`
- [x] `tests/test_application_packet.py` — 20 tests passing
- [x] 156/156 total tests passing

---

## Phase 11 — Browser Assistant with Approval Gates ✓ COMPLETE

- [x] `harnesses/browser_application/v0.py` — Playwright-optional (degrades to mock in dry_run)
- [x] Dry-run mode: mock page state, mock fields, placeholder screenshots
- [x] Form field inspection and classification (text, textarea, select, file, submit)
- [x] Packet-to-field mapping (first/last name, email, cover letter, LinkedIn)
- [x] Screenshot + evidence logging under `experiments/runs/{ts}/screenshots/`
- [x] `is_allowed_browser_action` + `is_safe_page_state` wired in
- [x] submit/send/upload blocked without `approval_status == "approved"` ✓
- [x] `bypass_captcha` and `fake_answer` always blocked ✓
- [x] Approval handoff dict created when submit is blocked
- [x] `tests/test_browser_assistant.py` — 18 tests passing
- [x] **174/174 total tests passing — ALL PHASES COMPLETE**
