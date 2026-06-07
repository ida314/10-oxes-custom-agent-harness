# Developer Onboarding Guide

This project has two systems. Read System 1 first — System 2 only makes sense once you understand what it's optimizing.

---

## 0. Orientation (5 minutes)

```
README.md              ← start here: project overview + quick-start
docs/PROJECT_BRIEF.md  ← why each system exists and what it must NOT do
docs/STATE.md          ← what's built, what's next, known issues
docs/DECISIONS.md      ← why every major decision was made
```

Run the tests before touching anything:

```bash
cd /path/to/10-ox
source .venv/bin/activate
pytest tests/ -q   # 174 passed — no Docker, no API key required
```

---

## 1. System 1 — Job-Search Intelligence

### What it does

Given a list of target companies and a candidate profile, System 1:
1. Queries ATS platforms (Greenhouse, Lever, Ashby) for open roles
2. Falls back to scraping company careers pages
3. Discovers articles, blog posts, events as intelligence signals
4. Scores jobs for entry-level fit and candidate fit
5. Classifies signals by type (hiring, technical, culture, strategy, etc.)
6. Generates ranked recommendations + an application packet draft
7. Writes everything to Postgres and a trace directory
8. Creates `ApprovalItem` rows for any action that requires human sign-off

### Data flow

```
CandidateProfile + Company
         │
         ▼
  skills/ats/*         ──── query Greenhouse/Lever/Ashby JSON APIs
  skills/company_research/*  ─── scrape careers page, blog, events, articles
         │
         ▼
  harnesses/job_discovery/v0.py   ─── normalize, deduplicate, score, recommend
  harnesses/article_discovery/v0.py ─ classify signal type + application angle
         │
         ▼
  harnesses/validators/*  ─── pure-Python gate (reject invalid before saving)
         │
         ▼
  Postgres (db/models.py)  +  experiments/runs/{ts}/  (raw traces)
         │
         ▼
  harnesses/application_packet/v0.py  ─── cover letter, tailoring, Q&A
  harnesses/browser_application/v0.py ─── field mapping (dry-run until approved)
```

### Key source files

| File | Entry function | Returns |
|------|---------------|---------|
| `harnesses/job_discovery/v0.py` | `run_company_scan(company_id, profile_id, config)` | `CompanyScanReport` |
| `harnesses/article_discovery/v0.py` | `score_articles(articles, profile, config)` | `ArticleDiscoveryReport` |
| `harnesses/application_packet/v0.py` | `generate_application_packet(job_id, profile, config)` | `ApplicationPacketResult` |
| `harnesses/browser_application/v0.py` | `run_browser_assist(packet, job_url, config)` | `BrowserAssistResult` |
| `harnesses/validators/retry.py` | `validate_with_retry(fn, validator, max_retries)` | validated output or human-review item |

### Validators — read these first

Every LLM output passes through a pure-Python validator before being saved. The validators live in `harnesses/validators/` and never call an LLM.

| Validator | What it blocks |
|-----------|---------------|
| `job.py` | jobs missing a source URL, senior-only roles |
| `article_signal.py` | signals without grounded evidence |
| `recommendation.py` | recommendations for inaccessible or stale roles |
| `application_packet.py` | fabricated experience, altered dates/GPAs |
| `browser_action.py` | submit/send/upload without `approval_status == "approved"` |

### Skill library

Skills in `skills/` are self-contained, fixture-tested packages. Each has `skill.py`, `metadata.yaml`, `tests.py`, `examples.json`, and `eval_history.jsonl`.

```
skills/
  base.py                   — SkillResult, NormalizedJob, Evidence, Skill protocol
  ats/
    greenhouse/             — query Greenhouse JSON board API
    lever/                  — query Lever API
    ashby/                  — query Ashby API
  company_research/
    find_careers_page/      — HTML scrape fallback
    find_engineering_blog/  — blog discovery
    find_events/            — hackathon/conference discovery
    find_recent_articles/   — news/interview discovery
```

### Trying it out

```bash
# Without Docker/Postgres — heuristic mode only
python -c "
from harnesses.job_discovery.v0 import run_company_scan, HarnessConfig, CandidateProfile
cfg = HarnessConfig(dry_run=True)
report = run_company_scan('test-company-id', 'profile-01', cfg)
print(report)
"

# With Postgres — full mode
docker-compose up -d
DATABASE_URL=postgresql://career_agent:career_agent@localhost:5432/career_agent \
  alembic upgrade head
DATABASE_URL=... python scripts/seed_companies.py
# Then use a real company UUID from the seeded DB
```

### Evals for System 1

```bash
# Job discovery eval (search split only — never use split="test" during development)
python evals/runners/evaluate_job_discovery.py

# Article signal eval
python evals/runners/evaluate_article_signals.py

# Application packet eval
python evals/runners/evaluate_application_packet.py
```

Datasets live in `evals/datasets/`. The `test/` split is held-out — never used during development or optimization.

---

## 2. System 2 — Harness Optimizer

### What it does

System 2 reads the raw execution traces that System 1 writes, proposes improved harness code, evaluates candidates on the search split, and maintains a Pareto frontier across six objectives.

It never modifies production harnesses (`v*.py`) or eval datasets.

### The optimization loop

```
experiments/runs/  (traces from System 1)
         │
         ▼
optimizers/meta_harness_loop.py
  1. Evaluate current candidates on search set
  2. Store traces
  3. Proposer reads prior runs + failures
  4. Proposer writes one candidate → harnesses/job_discovery/candidates/{name}.py
  5. Static interface check
  6. Eval on search set
  7. Add to population with parent_id lineage
  8. Update Pareto frontier in experiments/candidates/index.json
  9. Repeat
         │
         ▼
optimizers/search_controller.py  (Thompson sampling — selects which parent to mutate next)
```

### Key source files

| File | What it does |
|------|-------------|
| `optimizers/meta_harness_loop.py` | Main loop: bootstrap → eval → propose → update frontier |
| `optimizers/search_controller.py` | `SearchController` + `select_candidate_thompson()` |
| `skills/meta_harness/propose_job_harness.md` | Proposer agent skill definition + write-permission spec |
| `experiments/candidates/index.json` | Live candidate registry (all candidates + scores) |
| `harnesses/job_discovery/candidates/` | Proposed harness files (humans promote winners) |
| `notes/` | Proposer reasoning notes (one `.md` per candidate) |

### Running the loop

```bash
# Dry-run (no LLM, generates stub candidates)
python optimizers/meta_harness_loop.py --iterations 5

# With real LLM proposer (requires ANTHROPIC_API_KEY)
ANTHROPIC_API_KEY=sk-... python optimizers/meta_harness_loop.py --iterations 5
```

### Promoting a candidate to production

The optimizer never does this automatically. When a candidate consistently scores above the current production harness on the search set, a human:
1. Reviews the diff between the candidate and `v0.py`
2. Runs `pytest tests/` to verify it doesn't regress
3. Copies the candidate to `harnesses/job_discovery/v1.py`
4. Updates `docs/STATE.md` and `TODO.md`

### Write access constraints

The proposer agent is constrained at the code level:

```
ALLOWED:
  harnesses/*/candidates/{name}.py
  notes/{name}.md
  skills/meta_harness/

FORBIDDEN (hard-coded check):
  evals/                         ← changing this would make scores meaningless
  db/                            ← schema is shared infrastructure
  harnesses/*/v*.py              ← production harnesses — humans only
  experiments/*/test/            ← test split results
```

---

## 3. Shared Infrastructure

### Database (`db/`)

All structured state lives in Postgres. Never use loose JSON files for production data.

```bash
# Start DB
docker-compose up -d

# Apply migrations
DATABASE_URL=... alembic upgrade head

# Seed companies
DATABASE_URL=... python scripts/seed_companies.py
```

See `db/models.py` for all 15 table definitions. Key tables:
- `jobs`, `companies`, `company_sources` — System 1 data
- `agent_runs`, `tool_calls`, `trace_events` — System 1 instrumentation
- `harness_candidates`, `eval_scores` — System 2 state
- `approval_items` — human review queue (both systems)

### Trace filesystem (`app/tracing/`, `experiments/runs/`)

Every harness run auto-creates a directory:

```
experiments/runs/{ISO_TIMESTAMP}_{harness}_{version}/
  000_config.json
  001_skill_greenhouse.json   ← verbatim tool call input/output
  002_prompt_score_jobs.txt   ← verbatim LLM prompt
  003_model_output.txt        ← verbatim LLM response
  004_validator_result.json
  output.json
  failures/
    false_positives.json
    missed_jobs.json
```

Import and use: `from app.tracing.logger import TraceLogger`.

The proposer agent reads these directories with `grep` and file reads — verbatim content, no summaries.

### Tests (`tests/`)

```bash
pytest tests/ -q           # full suite, 174 tests
pytest tests/test_validators.py -v   # validators only (53 tests)
pytest tests/test_meta_harness.py    # System 2 tests (21 tests)
```

Tests use SQLite in-memory (not Postgres) and saved HTTP fixtures (not live network). No Docker, no API key needed.

---

## 4. Common Gotchas

**"Why isn't my LLM call working?"**
All harnesses degrade to heuristic mode when `ANTHROPIC_API_KEY` is not set. Set the key in `.env` or export it.

**"Why did the validator reject my output?"**
Check the `ValidationResult.reason_codes` and `details` fields. The validator will tell you exactly what rule was violated.

**"Can I bypass the validator for testing?"**
No. Route to `validate_with_retry()` with `max_retries=1` instead. Bypassing validators is forbidden by the project constraints.

**"Why can't I write directly to `harnesses/job_discovery/v1.py`?"**
That's a production harness. The optimizer writes only to `candidates/`. You (the human) promote candidates by copying + reviewing them.

**"Where do I add a new company?"**
Add it to the `scripts/seed_companies.py` seed script and re-run it against your local DB.

---

## 5. Contribution Checklist

Before opening a PR:
- [ ] `pytest tests/ -q` — 174 tests pass
- [ ] If adding a new skill: `skill.py`, `metadata.yaml`, `tests.py`, `examples.json`, `eval_history.jsonl` all present
- [ ] If changing a harness: updated `docs/STATE.md` and `TODO.md`
- [ ] No new `datetime.utcnow()` calls — use `datetime.now(timezone.utc)` instead
- [ ] No inline long prompts in Python — use `prompts/` templates
- [ ] No auto-submit code — `approval_status` must always start as `"pending"`
