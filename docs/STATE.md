# Project State

_Last updated: 2026-06-07_

## Status: ALL PHASES COMPLETE (MVP) + Documentation restructure

```
pytest tests/ → 174/174 PASSED
```

---

## What Was Built

### Test Coverage by Phase

| Phase | Description | Tests |
|-------|-------------|-------|
| 0 | Eval benchmark (seed, search/test split, article signal dataset) | — |
| 1 | Postgres data layer (15 tables, migrations, seed script) | 10 |
| 2 | ATS connectors + skill library (Greenhouse, Lever, Ashby, company research) | 21 |
| 3 | Job-discovery harness v0 (ATS-first, dedup, scoring, trace) | 8 |
| 4 | Article/intelligence scoring harness v0 (LLM + heuristic) | 15 |
| 5 | Trace filesystem (TraceLogger, sequential files, failures dir) | 8 |
| 6 | Eval runners (job discovery, article signals, test-split gating) | 15 |
| 7 | AutoHarness validators (job, article, recommendation, packet, browser, retry) | 53 |
| 8 | Meta-Harness optimizer loop v0 (bootstrap, evaluate, Pareto frontier) | 21 |
| 9 | Thompson sampling search controller (Beta distribution, exploration) | 21 |
| 10 | Application packet generation (cover letter, tailoring, Q&A, referral, prep) | 20 |
| 11 | Browser assistant with approval gates (dry-run, field mapping, screenshot) | 18 |

---

## Complete File Structure

```
skills/
  base.py                           SkillResult, NormalizedJob, Evidence, RunContext, Skill
  ats/  greenhouse, lever, ashby    ATS connectors + fixtures
  company_research/                 careers page, blog, events, recent articles
  meta_harness/propose_job_harness.md

harnesses/
  validators/
    base.py                         ValidationResult + merge()
    job.py                          is_valid_job, is_safe_to_apply, entry_level_score
    article_signal.py               is_valid_article_signal
    recommendation.py               is_valid_recommendation, is_safe_application_recommendation
    application_packet.py           is_valid_application_packet
    browser_action.py               is_allowed_browser_action, is_safe_page_state
    retry.py                        validate_with_retry
  job_discovery/v0.py               run_company_scan → CompanyScanReport
  job_discovery/candidates/         Meta-Harness candidate storage
  article_discovery/v0.py           score_articles → ArticleDiscoveryReport
  application_packet/v0.py         generate_application_packet → ApplicationPacketResult
  browser_application/v0.py        run_browser_assist → BrowserAssistResult

app/tracing/logger.py               TraceLogger (shared)

optimizers/
  meta_harness_loop.py              Bootstrap → evaluate → propose → Pareto
  search_controller.py              Thompson sampling + SearchController

experiments/
  candidates/index.json             Live candidate registry
  runs/                             Auto-created trace directories

evals/
  datasets/  seed(50), search(40), test(10-Stripe), article_signal(15)
  metrics/   job_tracker_metrics.py + __init__.py
  runners/   evaluate_job_discovery.py, evaluate_article_signals.py, evaluate_application_packet.py

prompts/
  article_signal_classify.txt
  cover_letter_draft.txt

db/  models.py(15 tables), migrations/, alembic.ini
scripts/  seed_companies.py
tests/  8 test files, 174 tests, fixtures/
notes/       Meta-Harness proposer notes
```

---

## To Run the MVP

```bash
# 1. Start Postgres
docker-compose up -d

# 2. Set env
cp .env.example .env

# 3. Run migrations and seed
DATABASE_URL=postgresql://career_agent:career_agent@localhost:5432/career_agent \
  .venv/bin/alembic upgrade head
DATABASE_URL=... .venv/bin/python scripts/seed_companies.py

# 4. Run a company scan (dry_run, no LLM needed)
DATABASE_URL=... .venv/bin/python -c "
from harnesses.job_discovery.v0 import run_company_scan, HarnessConfig, CandidateProfile
cfg = HarnessConfig(dry_run=False)
report = run_company_scan('COMPANY_ID', 'profile-01', cfg)
print(f'Jobs: {report.jobs_after_dedup}, Recommended: {sum(1 for s in report.scored_jobs if s.recommendation==\"apply\")}')
"

# 5. Run the eval suite
.venv/bin/pytest tests/ -q

# 6. Run Meta-Harness optimization loop (dry_run, no LLM)
.venv/bin/python optimizers/meta_harness_loop.py --iterations 5

# 7. With LLM (requires ANTHROPIC_API_KEY):
ANTHROPIC_API_KEY=sk-... .venv/bin/python ...
```

---

## Documentation restructure (2026-06-07)

Added README.md files at every level of the directory tree to make the System 1 / System 2 boundary explicit for new developers:

- `README.md` — root project overview with two-system architecture, quick-start, and docs index
- `docs/ONBOARDING.md` — guided developer onboarding for both systems
- `harnesses/README.md` — harness directory overview, System 1 vs System 2 ownership, versioning convention
- `harnesses/validators/README.md` — validator per-file reference
- `harnesses/job_discovery/README.md` — pipeline steps and output schema
- `harnesses/article_discovery/README.md` — signal types and LLM/heuristic modes
- `harnesses/application_packet/README.md` — safety guarantees and approval flow
- `harnesses/browser_application/README.md` — auto-allowed vs approval-required actions
- `skills/README.md` — skill protocol, lifecycle, and directory map
- `skills/ats/README.md` — connector usage, fixtures, and how to add a new ATS
- `skills/company_research/README.md` — per-skill descriptions
- `skills/meta_harness/README.md` — proposer skill and write-permission spec
- `optimizers/README.md` — loop design, Pareto objectives, and promotion procedure
- `evals/README.md` — dataset layout, search/test split rule, metric reference
- `db/README.md` — table ownership by system, key constraints, migration commands
- `app/README.md` — TraceLogger API and trace directory layout
- `tests/README.md` — test file → system mapping, fixture conventions
- `prompts/README.md` — template variable reference

No Python code was changed. All 174 tests continue to pass.

---

## Known Remaining Items (not blocking MVP)

1. `utcnow()` deprecation — replace with `datetime.now(UTC)` in a cleanup pass
2. Meta-Harness real proposer (`dry_run=False`) — requires Agent SDK integration
3. `find_engineering_blog` and `find_events` skills have no dedicated fixture tests
4. Playwright for live browser automation — install with `uv pip install playwright && playwright install chromium`
5. Inter-annotator agreement study for fit_score rubric bands
6. `evals/datasets/test/article_signal_test.jsonl` — article signal held-out test split not yet created
7. Full `scripts/run_company_scans.py` CLI wrapper not yet built
