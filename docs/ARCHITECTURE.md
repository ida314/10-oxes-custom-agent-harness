# Architecture — Career Agent Harness System

## Target Repo Structure

```
career-agent/
  app/
    api/              FastAPI endpoints for dashboard/approval queue
    dashboard/        Daily digest rendering
    workers/          Background job runners
  harnesses/
    job_discovery/
      v0.py           Production harness v0
      v1.py           (future)
      candidates/     Meta-Harness proposed candidates (not production)
    article_discovery/
      v0.py
      candidates/
    job_scoring/
      v0.py
      candidates/
    application_packet/
      v0.py
      candidates/
    browser_application/
      v0.py           Dry-run only until Phase 11 approval gates
    coding_agent/
      v0.py
    validators/
      job.py
      article_signal.py
      recommendation.py
      application_packet.py
      browser_action.py
  skills/
    ats/
      greenhouse/
        skill.py
        metadata.yaml
        tests.py
        examples.json
        eval_history.jsonl
      lever/
      ashby/
    company_research/
      find_engineering_blog/
      find_recent_interviews/
      find_events/
    article_extraction/
      engineering_blog_classifier/
    outreach/
    coding/
    meta_harness/
      propose_job_harness.md     Skill definition for the proposer agent
  evals/
    datasets/
      job_tracker_seed.jsonl     50-case seed (Phase 0 — DONE)
      search/                    Search set (never expose to test)
      test/                      Held-out test set (never expose to optimizer)
      article_signal_seed.jsonl  (Phase 4)
    runners/
      evaluate_job_discovery.py
      evaluate_article_signals.py
      evaluate_application_packet.py
    metrics/
      job_tracker_metrics.py     (Phase 0 — DONE)
  experiments/
    runs/                        Full run directories (one per harness execution)
    candidates/
      index.json                 Candidate registry with scores and lineage
  optimizers/
    meta_harness_loop.py         Main optimization loop
    search_controller.py         Thompson sampling candidate selection
  db/
    models.py
    migrations/
  prompts/                       Prompt templates (no long prompts inline in Python)
  scripts/
    seed_companies.py
    run_company_scans.py
  notes/                         Meta-Harness proposer notes (one file per candidate)
  docker-compose.yml
  pyproject.toml
  README.md
```

---

## Core Principle

```
Hermes / LangChain / local models = execution substrate
Your harness = source of truth, evals, traces, policies, state, approval gates
```

LangGraph is useful for workflow/state machines. LangChain tracing is useful for observability. But product logic, validators, approval gates, and eval scoring live in this repo — not in any framework's internals.

---

## Database Design (Postgres)

Source of truth for all structured state. Do not use loose JSON files for production data.

### Core Tables

```python
class Company(SQLModel, table=True):
    id: UUID
    name: str
    domain: str
    ats_type: str | None          # greenhouse | lever | ashby | custom | unknown
    careers_url: str | None
    priority: int                 # 1 = highest
    notes: str | None
    created_at: datetime
    updated_at: datetime

class CompanySource(SQLModel, table=True):
    id: UUID
    company_id: UUID              # FK → companies
    source_type: str              # careers_page | engineering_blog | linkedin | glassdoor
    url: str
    last_fetched_at: datetime | None
    confidence: float

class Job(SQLModel, table=True):
    id: UUID
    company_id: UUID
    title: str
    url: str                      # UNIQUE
    location: str | None
    description_text: str
    source_type: str
    discovered_at: datetime
    posted_at: datetime | None
    normalized_hash: str          # UNIQUE — deduplication key
    entry_level_score: float | None
    fit_score: float | None
    status: str                   # new | reviewed | applied | rejected | stale

class Article(SQLModel, table=True):
    id: UUID
    company_id: UUID
    title: str
    url: str
    source_type: str              # engineering_blog | company_blog | news | interview
    published_at: datetime | None
    discovered_at: datetime
    summary: str
    relevance_score: float
    signal_type: str              # hiring_signal | technical_signal | culture_signal | ...
    application_angle: str
    interview_questions: list[str]  # JSON column

class Event(SQLModel, table=True):
    id: UUID
    company_id: UUID
    title: str
    url: str | None
    event_date: datetime | None
    discovered_at: datetime
    event_type: str               # hackathon | info_session | conference | career_fair
    relevance_score: float

class Person(SQLModel, table=True):
    id: UUID
    company_id: UUID
    name: str
    role: str | None
    linkedin_url: str | None
    connection_type: str | None   # alumni | mutual_connection | recruiter | hiring_manager

class Application(SQLModel, table=True):
    id: UUID
    job_id: UUID
    status: str                   # draft | submitted | interviewing | rejected | offer
    submitted_at: datetime | None
    packet_id: UUID | None

class ApplicationPacket(SQLModel, table=True):
    id: UUID
    job_id: UUID
    resume_variant_id: UUID | None
    cover_letter: str | None
    short_answers: dict            # JSON column
    referral_message: str | None
    interview_notes: list[str]     # JSON column
    unsupported_claims: list[str]  # JSON column — must be empty before approval
    validation_status: str         # pending | passed | failed
    approval_status: str           # pending | approved | rejected

class HarnessCandidate(SQLModel, table=True):
    id: UUID
    domain: str                   # job_discovery | article_discovery | job_scoring | ...
    name: str
    version: str
    parent_id: UUID | None        # lineage tracking
    file_path: str
    created_at: datetime
    search_scores: dict            # JSON — scores on search set only
    notes: str | None
    status: str                   # experimental | active | deprecated | rejected

class AgentRun(SQLModel, table=True):
    id: UUID
    harness_candidate_id: UUID | None
    run_type: str                 # company_scan | article_discovery | eval | optimization
    started_at: datetime
    finished_at: datetime | None
    status: str                   # running | completed | failed
    company_id: UUID | None
    profile_id: UUID | None
    trace_dir: str                # path to experiments/runs/{...}/
    summary_metrics: dict          # JSON

class ToolCall(SQLModel, table=True):
    id: UUID
    agent_run_id: UUID
    tool_name: str
    input_data: dict               # JSON
    output_data: dict              # JSON
    started_at: datetime
    duration_ms: int
    success: bool
    error: str | None

class TraceEvent(SQLModel, table=True):
    id: UUID
    agent_run_id: UUID
    sequence: int
    event_type: str               # prompt | model_output | tool_call | validator | parser_result
    payload: dict                  # JSON — full content
    timestamp: datetime

class EvalScore(SQLModel, table=True):
    id: UUID
    harness_candidate_id: UUID
    dataset_split: str            # search | test
    metric: str
    score: float
    n_cases: int
    evaluated_at: datetime
    run_id: UUID | None

class ApprovalItem(SQLModel, table=True):
    id: UUID
    item_type: str                # recommendation | application_packet | browser_action | outreach
    item_id: UUID
    created_at: datetime
    status: str                   # pending | approved | rejected
    reviewed_at: datetime | None
    reviewer_notes: str | None
```

**Key constraints:**
- `jobs.url` UNIQUE
- `jobs.normalized_hash` UNIQUE
- Indexes on: `company_id`, `discovered_at`, `source_type`, `status`, `score` fields, `agent_run_id`

---

## Skill Library Design

Skills are executable packages, not prompt snippets.

```
skills/{domain}/{skill_name}/
  skill.py          — implements Skill protocol
  metadata.yaml     — name, version, inputs, outputs, allowed_tools, failure_modes, eval_metrics
  tests.py          — at least 3 tests using saved fixtures
  examples.json     — 3–5 example input/output pairs
  eval_history.jsonl — one JSON row per eval run (date, metrics, dataset_version)
```

**Skill interface:**
```python
class SkillResult(BaseModel):
    success: bool
    items: list[Any]
    evidence: list[Evidence]
    confidence: float
    errors: list[str]

class Skill(Protocol):
    name: str
    version: str
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]

    def run(self, input: BaseModel, context: RunContext) -> SkillResult: ...
```

**Skill lifecycle:**
1. Agent notices repeated pattern or failure mode.
2. Agent proposes new skill (tests and metadata required).
3. Skill runs on eval examples.
4. If metrics improve: mark `active`. Otherwise: keep `experimental` or `rejected`.

**Metadata schema:**
```yaml
name: query_greenhouse_jobs
version: 0.1.0
domain: ats
status: experimental   # experimental | active | deprecated
inputs:
  - company_name
  - board_token
outputs:
  - normalized_jobs
allowed_tools:
  - http_get
failure_modes:
  - invalid board token
  - changed schema
  - duplicate jobs
eval_metrics:
  - recall
  - parse_success
  - duplicate_rate
```

---

## Harness Design

A harness is a stateful Python module that controls:
- which skills/sources to query and in what order
- fallback logic (deterministic → LLM-assisted)
- context management (what to show the model, at what cost)
- deduplication and normalization
- scoring and ranking
- validator calls
- trace logging
- output to Postgres + filesystem

**Harness interface (job discovery):**
```python
def run_company_scan(
    company_id: UUID,
    profile_id: UUID,
    config: HarnessConfig | None = None,
) -> CompanyScanReport:
    ...
```

**AutoHarness pattern applied:**
```python
# Proposal
recommendation = propose_recommendation(company, jobs, articles, profile)

# Validation (pure Python, not LLM)
if not is_valid_recommendation(recommendation, profile):
    log_validation_failure(recommendation)
    route_to_human_review(recommendation)
    return

# Only reach here if valid
save_recommendation(recommendation)
create_approval_item(recommendation)
```

---

## Trace Filesystem Design

Every harness evaluation creates a directory:

```
experiments/runs/{ISO_TIMESTAMP}_{harness_name}_{version}/
  config.json                   — harness config, model, thresholds
  harness.py                    — snapshot of harness source at run time
  input.json                    — input parameters
  output.json                   — final report/output
  metrics.json                  — scalar metrics for this run
  traces/
    000_tool_call_greenhouse.json
    001_prompt_score_jobs.txt
    002_model_output_score_jobs.txt
    003_parser_result.json
    004_validator_result.json
    ...
  artifacts/
    raw_pages/                  — fetched HTML/JSON
    screenshots/                — browser screenshots (Phase 11)
    normalized_jobs.json
    recommendations.json
  failures/
    false_positives.json
    missed_jobs.json
    bad_recommendations.json
```

**Design rationale:** the proposer agent uses `grep`, `cat`, and file search on this directory tree. Summaries only would hide the failure modes that matter most.

---

## Evaluation Runner Design

```python
def evaluate_job_discovery_harness(
    harness_path: str,
    eval_dataset: str,          # path to .jsonl
    split: str,                 # "search" | "test"
    output_dir: str,
) -> EvalReport:
    for case in load_dataset(eval_dataset, split=split):
        result = run_harness_on_case(harness_path, case)
        score = score_case(case, result)
        save_trace(case, result, score)
    return aggregate_metrics(scores)
```

**Metrics implemented (Phase 0 partial, Phases 3–7 full):**
- `job_recall`, `job_precision`, `entry_level_accuracy`, `duplicate_rate`
- `article_signal_precision`, `recommendation_acceptability`, `unsafe_action_rate`
- `context_tokens`, `runtime_seconds`
- `truthfulness_score`, `specificity_score`, `source_grounding_score` (Phase 10)
- `tests_passed`, `task_success`, `regression_count`, `diff_size` (coding agent)

**Search/test split rule:** the optimizer reads only `search` split scores. `test` split scores are computed manually to measure generalization. Never expose `test` scores during optimization.

---

## Meta-Harness Optimizer Design

**Loop:**
```
1. Evaluate current harnesses on search set → metrics + traces
2. Store full traces to experiments/runs/
3. Proposer agent inspects prior runs (code + traces + scores + failures)
4. Proposer writes one new harness candidate to harnesses/{domain}/candidates/
5. Validate candidate interface (static check)
6. Run eval on search set
7. Add candidate to population with lineage
8. Update Pareto frontier
9. Repeat
```

**Candidate selection (Phase 9):** Thompson sampling over metric history.
```python
sampled_value = beta_sample(successes + 1, failures + 1)
```

**Pareto frontier:** multi-objective over:
- `job_recall` (maximize)
- `job_precision` (maximize)
- `entry_level_accuracy` (maximize)
- `recommendation_acceptability` (maximize)
- `unsafe_action_rate` (minimize)
- `context_tokens` (minimize)

**Proposer write permissions (hard constraint):**
```
ALLOWED:  harnesses/*/candidates/{name}.py
          notes/{name}.md
          skills/meta_harness/
FORBIDDEN: evals/
           db/
           harnesses/*/v*.py   (production harnesses)
           experiments/*/test/ (test split results)
```

---

## Human Approval Gates

All external actions require approval. Gate is enforced in code, not by convention.

| Action | Gate |
|---|---|
| View job listing | No gate |
| Save job to DB | No gate |
| Generate recommendation | No gate — but validator must pass first |
| Generate application packet | No gate — but validator must pass first |
| Fill form draft (local only) | No gate |
| Submit application | `approval_status == "approved"` REQUIRED |
| Upload resume | `approval_status == "approved"` REQUIRED |
| Send outreach message | `approval_status == "approved"` REQUIRED |
| Create ATS account | `approval_status == "approved"` REQUIRED |

```python
def is_allowed_browser_action(action, page_state, approval_status):
    if action.type in ["submit", "send_message", "upload_resume", "create_account"]:
        return approval_status == "approved"
    if action.type in ["bypass_captcha", "fake_answer"]:
        return False  # never
    return True
```

---

## LangChain / LangGraph Role

Use LangGraph for workflow/state machines if it adds clarity. Do not use it as source of truth.

**Good use:** structured graph execution for `CompanyScanGraph`, `ApplicationPacketGraph`, `HarnessOptimizationGraph`.

**Not the source of truth:** LangChain memory, LangChain callbacks, LangChain eval frameworks. Real memory is Postgres + trace filesystem.

**Example graph skeleton:**
```
load_company
→ run_ats_connectors
→ fallback_web_search (conditional)
→ normalize_dedupe
→ score_jobs
→ discover_articles_events
→ score_signals
→ generate_recommendations
→ validate_recommendations
→ save_report
→ approval_queue
```
