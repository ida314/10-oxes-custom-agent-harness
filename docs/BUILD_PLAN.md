# Build Plan — Career Agent Harness System

## Phase Dependency Map

```
Phase 0 (eval benchmark) ──────┐
Phase 1 (data layer)    ───────┼──► Phase 3 (harness v0) ──► Phase 4 (article scoring)
Phase 2 (connectors)    ───────┘          │
                                          ▼
                               Phase 5 (trace filesystem)
                                          │
                                          ▼
                               Phase 6 (eval runners)
                                          │
                                          ▼
                               Phase 7 (validators)
                                          │
                                          ▼
                               Phase 8 (Meta-Harness loop v0)
                                          │
                                          ▼
                               Phase 9 (tree search)
                                          │
                                          ▼
                               Phase 10 (application packets)
                                          │
                                          ▼
                               Phase 11 (browser assistant)
```

---

## Phase 0 — Eval Benchmark (PARTIALLY DONE)

**Goal:** define what "good" means before writing any agent code.

**Status:** `evals/datasets/job_tracker_seed.jsonl` (50 cases) and `evals/metrics/job_tracker_metrics.py` exist.

**Deliverables:**
- [x] `evals/datasets/job_tracker_seed.jsonl` — 50 eval cases, 5 companies
- [x] `evals/metrics/job_tracker_metrics.py` — 6 scoring functions + CLI
- [ ] `evals/datasets/search/` — search split (first 40 cases)
- [ ] `evals/datasets/test/` — held-out test split (last 10 cases)
- [ ] `evals/datasets/article_signal_seed.jsonl` — article signal cases (needed before Phase 4)

**Acceptance criteria:**
- All 6 metrics compute correctly on sample predictions
- Search/test split defined and documented
- Dataset can be loaded and scored end-to-end via CLI

**Metrics defined:**
- `job_discovery_recall`, `job_discovery_precision`, `article_relevance`
- `fit_score_accuracy`, `application_safety_accuracy`, `deduplication_f1`

---

## Phase 1 — Data Layer

**Goal:** durable, indexed Postgres schema that all later phases write to.

**Prerequisites:** Phase 0 (search/test split needed to design eval_scores table)

**Deliverables:**
- `db/models.py` — SQLModel models for all 15 tables
- `db/migrations/` — Alembic migration history
- `docker-compose.yml` — Postgres + pgAdmin
- `scripts/seed_companies.py` — seed 5 companies (Google, Datadog, Ramp, Jane Street, Stripe)
- `tests/test_db_models.py` — create, update, deduplication tests
- `pyproject.toml` — project metadata + deps

**Tables:**
```
companies, company_sources, jobs, events, articles, people,
applications, application_packets, skills, harness_candidates,
agent_runs, tool_calls, trace_events, eval_scores, approval_items
```

**Key constraints:**
- `jobs.url` UNIQUE
- `jobs.normalized_hash` UNIQUE
- Indexes on: `company_id`, `discovered_at`, `source_type`, `status`, score fields

**Acceptance criteria:**
- `docker-compose up` starts Postgres cleanly
- `alembic upgrade head` applies all migrations with no errors
- `python scripts/seed_companies.py` inserts 5 companies
- All tests pass: create job, update job status, reject duplicate URL, reject duplicate hash
- No agent/LLM code in this phase

**Agent prompt for this phase (copy-paste ready):**
```
Create a new Python repo for a career-agent harness system.

Implement only Phase 1: the data layer.

Stack: Python 3.12, Postgres, SQLAlchemy or SQLModel, Alembic, Pydantic, pytest, Docker Compose.

Create tables: companies, company_sources, jobs, events, articles, people, applications,
application_packets, skills, harness_candidates, agent_runs, tool_calls, trace_events,
eval_scores, approval_items.

Requirements:
- Include Alembic migrations.
- Include created_at/updated_at on all tables.
- Include source URLs and confidence fields where appropriate.
- Include UNIQUE constraints for jobs.url and jobs.normalized_hash.
- Include indexes on company_id, discovered_at, source_type, status, and score fields.
- Include docker-compose.yml for Postgres.
- Include pyproject.toml with SQLModel/SQLAlchemy, Alembic, Pydantic, pytest deps.
- Include scripts/seed_companies.py seeding Google, Datadog, Ramp, Jane Street, Stripe.
- Include tests/test_db_models.py with tests for create, update, and deduplication.
- Do not build agents, browser automation, or LLM calls yet.

Read docs/ARCHITECTURE.md for the full schema spec before implementing.
After implementation, run tests and report which files were created.
```

---

## Phase 2 — Deterministic Source Connectors + Skill Library v0

**Goal:** reliable, tested, non-LLM data ingestion for ATS platforms and company research.

**Prerequisites:** Phase 1 (skills write to DB)

**Deliverables:**
- `skills/ats/greenhouse/` — query_greenhouse_jobs skill
- `skills/ats/lever/` — query_lever_jobs skill
- `skills/ats/ashby/` — query_ashby_jobs skill
- `skills/company_research/find_careers_page/` — generic careers-page fallback
- `skills/company_research/find_engineering_blog/` — blog discovery
- `skills/company_research/find_events/` — event discovery
- `skills/company_research/find_recent_articles/` — article discovery
- `tests/fixtures/` — saved HTTP responses for unit tests
- `tests/test_ats_connectors.py`

**Each skill must have:** `skill.py`, `metadata.yaml`, `tests.py`, `examples.json`, `eval_history.jsonl`

**Acceptance criteria:**
- Each skill returns a typed `SkillResult`
- Each result includes source URLs and timestamps
- Jobs are normalized: title, location, description, URL, source_type, discovered_at
- No browser automation used if HTTP parsing succeeds
- Unit tests pass with saved fixtures (no live network calls)
- Each skill has at least 3 tests

---

## Phase 3 — Job-Discovery Harness v0

**Goal:** first end-to-end company scan with validators and trace logging.

**Prerequisites:** Phases 1 + 2

**Deliverables:**
- `harnesses/job_discovery/v0.py` — exposes `run_company_scan(company_id, profile_id, config) -> CompanyScanReport`
- `tests/test_job_discovery_harness.py`

**Harness must:**
1. Load company and candidate profile from DB
2. Run ATS skills first; fall back to careers page and web research if confidence is low
3. Normalize and deduplicate jobs
4. Discover articles, engineering posts, interviews, events
5. Score jobs for entry-level fit and candidate fit
6. Generate recommendations via LLM
7. Validate recommendations with pure Python validators
8. Save all evidence: prompts, model outputs, tool calls, scores
9. Write to Postgres and trace filesystem

**Acceptance criteria:**
- `run_company_scan` runs end-to-end on seeded companies
- Validators reject invalid recommendations (missing source, senior-only, absent skill claims)
- Full trace written to `experiments/runs/{timestamp}/`
- All DB writes succeed

---

## Phase 4 — Article / Company Intelligence Scoring

**Goal:** classify and score company signals for actionable application advice.

**Prerequisites:** Phase 3 (harness scaffolding exists)

**Deliverables:**
- `harnesses/article_discovery/v0.py`
- `evals/datasets/article_signal_seed.jsonl`

**Signal types:** `hiring_signal`, `technical_signal`, `culture_signal`, `strategy_signal`, `interview_prep_signal`, `networking_signal`, `risk_signal`, `irrelevant`

**For each non-irrelevant signal, produce:**
- concise summary
- why it matters for this candidate
- application angle
- outreach angle
- interview question
- confidence
- source evidence

**Acceptance criteria:**
- Correctly classifies held-out article examples
- Never invents claims not in source text
- Full trace saved (retrieved text → selected snippets → prompt → output → validation)
- Scores above random baseline on `article_signal_seed.jsonl`

---

## Phase 5 — Trace Filesystem + Experiment Logging

**Goal:** full raw execution history that enables the Meta-Harness proposer to diagnose failures.

**Prerequisites:** Phase 3 (harness produces traces)

**Deliverables:**
- `app/tracing/` — trace logger module
- `experiments/runs/` — directory structure (auto-created per run)
- `tests/test_trace_logger.py`

**Each run directory:**
```
experiments/runs/{ISO_TIMESTAMP}_{harness}_{version}/
  config.json, harness.py, input.json, output.json, metrics.json
  traces/000_tool_call.json, 001_prompt.txt, 002_model_output.txt, ...
  artifacts/raw_pages/, screenshots/, normalized_jobs.json
  failures/false_positives.json, missed_jobs.json, bad_recommendations.json
```

**Postgres summary rows:** `agent_runs`, `trace_events`, `eval_scores`

**Acceptance criteria:**
- Every harness run auto-creates a complete trace directory
- All prompts, model outputs, tool calls stored verbatim
- Proposer agent can `grep` traces without needing special tooling
- Test confirms trace completeness after a mock harness run

---

## Phase 6 — Evaluation Runners

**Goal:** reproducible metric computation over harness candidates, with search/test isolation.

**Prerequisites:** Phases 0 + 5

**Deliverables:**
- `evals/runners/evaluate_job_discovery.py`
- `evals/runners/evaluate_article_signals.py`
- `evals/runners/evaluate_application_packet.py`

**Each runner must:**
- Load a candidate harness by file path
- Run on JSONL dataset (search or test split)
- Capture full traces
- Compute scalar metrics
- Save `metrics.json` and per-example results
- Never expose test-split metrics during optimization loop

**Metrics:**
```
job_recall, job_precision, entry_level_accuracy, duplicate_rate,
article_signal_precision, recommendation_acceptability, unsafe_action_rate,
context_tokens, runtime_seconds
```

**Acceptance criteria:**
- Runner produces identical metrics on the same input twice
- Search/test split boundary is enforced (test-set eval only callable explicitly)
- Metrics written to `eval_scores` table

---

## Phase 7 — AutoHarness-Style Validators

**Goal:** pure Python validators that catch bad outputs before they reach the user or external systems.

**Prerequisites:** Phase 3 (harness uses validators)

**Deliverables:**
- `harnesses/validators/job.py`
- `harnesses/validators/article_signal.py`
- `harnesses/validators/recommendation.py`
- `harnesses/validators/application_packet.py`
- `harnesses/validators/browser_action.py`
- `tests/test_validators.py`

**Each validator returns:**
```python
class ValidationResult(BaseModel):
    valid: bool
    reason_codes: list[str]
    details: str | None
```

**Retry wrapper pattern:**
1. Call model → parse → validate
2. If invalid: retry with validation errors appended to prompt
3. After `max_retries`: route to human review

**Acceptance criteria:**
- All validators pass positive/negative test cases
- `is_valid_application_packet` rejects fabricated experience, changed dates, missing sources
- `is_allowed_browser_action` rejects submit/send without approval
- Validators are pure Python (no LLM calls)

---

## Phase 8 — Meta-Harness Optimizer Loop v0

**Goal:** first working self-improvement loop that proposes, evaluates, and tracks harness candidates.

**Prerequisites:** Phases 5 + 6 + 7 (traces, runners, validators all exist)

**Deliverables:**
- `optimizers/meta_harness_loop.py`
- `skills/meta_harness/propose_job_harness.md`
- `harnesses/job_discovery/candidates/` (populated by loop)
- `experiments/candidates/index.json`

**Loop:**
```
1. Evaluate current harnesses on search set
2. Store traces
3. Proposer agent inspects experiments/runs/
4. Proposer writes one candidate to harnesses/job_discovery/candidates/
5. Validate interface (static)
6. Run eval on search set
7. Add to population with lineage
8. Update Pareto frontier
9. Repeat
```

**Proposer restrictions:** writes only to `harnesses/*/candidates/`, `notes/`, `skills/meta_harness/`.

**Acceptance criteria:**
- Loop runs 5 iterations without crashing
- Each iteration produces a candidate with valid interface
- Pareto frontier updates correctly
- All candidates have lineage (parent_id)

---

## Phase 9 — AutoHarness Tree Search

**Goal:** systematic candidate selection using Thompson sampling.

**Prerequisites:** Phase 8

**Deliverables:**
- `optimizers/search_controller.py`
- Updated `experiments/candidates/index.json`

**Candidate selection:**
```python
score = weighted_sum({
    "job_recall": 0.25, "job_precision": 0.20,
    "entry_level_accuracy": 0.20, "recommendation_acceptability": 0.20,
    "unsafe_action_rate": -0.30, "context_tokens": -0.05,
})
sampled_value = beta_sample(successes + 1, failures + 1)
```

**Acceptance criteria:**
- Thompson sampling selects high-performing candidates more often over 20+ iterations
- Parent-child lineage fully tracked
- Pareto frontier maintained over 6 objectives

---

## Phase 10 — Application Packet Generation

**Goal:** validated, human-approved packet generation. No auto-submit.

**Prerequisites:** Phase 7 (validators) + Phase 3 (job discovery)

**Deliverables:**
- `harnesses/application_packet/v0.py`
- `harnesses/validators/application_packet.py`

**Outputs:** resume tailoring suggestions, cover letter draft, short-answer drafts, referral request draft, interview prep notes, validation report

**Acceptance criteria:**
- Validator rejects fabricated experience
- Every tailored claim maps to a candidate_profile field
- Every company-specific claim maps to a source URL
- All packets create an `ApprovalItem` row; none auto-submit

---

## Phase 11 — Browser Assistant

**Goal:** assisted (not autonomous) browser form filling with hard approval gates.

**Prerequisites:** Phase 10

**Deliverables:**
- `harnesses/browser_application/v0.py`
- `harnesses/validators/browser_action.py`

**Automatically allowed:** open page, read fields, classify fields, draft values, fill local form draft, screenshot

**Requires approval:** create account, upload resume, send message, submit application, click final submit

**Acceptance criteria:**
- Dry-run mode produces screenshot and field-mapping report without submitting
- `is_allowed_browser_action` blocks submit/send without `approval_status == "approved"`
- Approval handoff creates `ApprovalItem` row

---

## 6-Week Implementation Plan

### Week 1 — Data + Eval Foundation
- Complete Phase 0 remaining items (search/test split, article signal dataset)
- Complete Phase 1 (Postgres schema, migrations, seed, tests)
- No agents yet

### Week 2 — Connectors + Skill Library v0
- Complete Phase 2 (Greenhouse, Lever, Ashby, careers page, blog, events)
- Skill metadata format established
- Unit tests with fixtures

### Week 3 — Job Discovery Harness v0 + Trace Logging
- Complete Phase 3 (company scan harness)
- Complete Phase 5 (trace filesystem)
- First end-to-end run on seeded companies

### Week 4 — Eval Runners + Meta-Harness Loop v0
- Complete Phase 6 (eval runners, search/test isolation)
- Complete Phase 7 (validators)
- Complete Phase 8 (first 5 harness candidates via optimizer)
- Pareto frontier tracking

### Week 5 — Article Intelligence + Skill Creation Loop
- Complete Phase 4 (article/event scoring)
- Skill proposal loop: failure classifier → skill proposal → activation policy

### Week 6 — Application Packet Generation
- Complete Phase 10 (packet generation, truthfulness validator, approval queue)
- Browser automation (Phase 11) is Week 7+
