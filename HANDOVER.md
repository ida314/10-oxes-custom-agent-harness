# Handover Prompt — Career Agent Harness System

_Generated: 2026-06-07_

---

## Copy-paste this into a new Claude Code session:

```
You are continuing work on the career-agent harness system in /home/bouncyelectron/Projects/10-ox.

Before doing anything else, read these four files in order:
1. CLAUDE.md          — project rules and build order
2. docs/STATE.md      — current status (all 11 phases complete, 174/174 tests pass)
3. TODO.md            — all items checked; look here for any new tasks added
4. docs/ARCHITECTURE.md — full technical architecture if you need schema or design details

## Current state summary

All 11 phases of the MVP are complete and tested:

  Phase 0  — Eval benchmark: 50-case seed, search/test split, 15 article signal cases
  Phase 1  — Postgres data layer: 15 SQLModel tables, Alembic migrations, Docker Compose, seed script
  Phase 2  — ATS connectors: Greenhouse, Lever, Ashby + 4 company research skills (all fixture-tested)
  Phase 3  — Job-discovery harness v0: run_company_scan → CompanyScanReport
  Phase 4  — Article scoring harness v0: score_articles → ArticleDiscoveryReport (LLM + heuristic)
  Phase 5  — Trace filesystem: app/tracing/logger.py (TraceLogger)
  Phase 6  — Eval runners: evaluate_job_discovery, evaluate_article_signals, evaluate_application_packet
  Phase 7  — Validators: job, article_signal, recommendation, application_packet, browser_action, retry
  Phase 8  — Meta-Harness loop: bootstrap → evaluate → propose (dry_run stub) → Pareto frontier
  Phase 9  — Thompson sampling search controller
  Phase 10 — Application packet generation: cover letter, tailoring, Q&A, referral, interview prep
  Phase 11 — Browser assistant: dry-run field mapping, screenshots, approval gate enforcement

Test suite: .venv/bin/pytest tests/ → 174/174 PASSED (no live network, no Docker required)

Python environment: .venv/ (Python 3.12, managed by uv)
Run tests: .venv/bin/pytest tests/ -q

## What still needs doing (not blocking MVP, but next-priority work)

Choose one of these to work on next, or ask the user which they want:

### Option A — Wire real LLM proposer into Meta-Harness loop
File: optimizers/meta_harness_loop.py, function _invoke_proposer_agent()
Currently returns False (dry_run stub). Real implementation should:
- Read experiments/candidates/index.json for current best candidate
- Read trace files from 3+ low-scoring runs in experiments/runs/
- Invoke a Claude Code subagent with the skill defined in skills/meta_harness/propose_job_harness.md
- The subagent writes one candidate to harnesses/job_discovery/candidates/{name}.py
- Return True on success
Requires: ANTHROPIC_API_KEY env var

### Option B — Build scripts/run_company_scans.py CLI
This is the "minimal first milestone" command described in docs/PROJECT_BRIEF.md:
  python scripts/run_company_scans.py --company-list target_companies.yaml --profile profiles/user.yaml
It should:
- Load companies from YAML (or DB)
- Load candidate profile from YAML
- Run run_company_scan() for each company (harnesses/job_discovery/v0.py)
- Print a digest: jobs found, recommended actions, article signals
- Write traces to experiments/runs/
- Not require Docker/Postgres if dry_run=True

### Option C — Fix utcnow() deprecation warnings
Replace all datetime.utcnow() calls with datetime.now(timezone.utc) across:
  skills/ats/greenhouse/skill.py, skills/ats/lever/skill.py, skills/ats/ashby/skill.py,
  skills/company_research/find_*.py, harnesses/job_discovery/v0.py,
  harnesses/article_discovery/v0.py, harnesses/application_packet/v0.py,
  harnesses/browser_application/v0.py, optimizers/meta_harness_loop.py,
  evals/runners/*.py, tests/test_db_models.py
Also add: from datetime import timezone at top of each file.
Run pytest after to confirm 174/174 still pass.

### Option D — Add a candidate profile YAML + real company scan end-to-end test
Create: profiles/example.yaml with a realistic candidate profile
Create: target_companies.yaml with 3-5 companies from the seeded list
Then run a real scan against the seeded DB (requires docker-compose up first):
  docker-compose up -d
  DATABASE_URL=postgresql://career_agent:career_agent@localhost:5432/career_agent \
    .venv/bin/alembic upgrade head
  DATABASE_URL=... .venv/bin/python scripts/seed_companies.py
  DATABASE_URL=... .venv/bin/python scripts/run_company_scans.py ...

### Option E — Add fixture tests for find_engineering_blog and find_events skills
These two skills have no dedicated fixture-based tests (only monkeypatched indirectly).
Create: tests/fixtures/engineering_blog/stripe_blog.html
Create: tests/fixtures/events/google_events.html
Add test class TestFindEngineeringBlog and TestFindEvents to tests/test_ats_connectors.py

## Key constraints — never violate these

- Do NOT modify evals/datasets/test/ (held-out test set — never expose to optimizer)
- Do NOT modify evals/metrics/job_tracker_metrics.py (metric definitions are stable)
- Do NOT let optimizers write to harnesses/*/v*.py (production harnesses — humans promote candidates)
- Do NOT add auto-submit anywhere; approval_status must always start as "pending"
- Do NOT skip the validator chain; every LLM output goes through is_valid_*() before acting
- After any meaningful change: update docs/STATE.md and TODO.md

## Architecture quick-reference

Database:       Postgres via docker-compose up (SQLModel + Alembic)
               Models: db/models.py (15 tables)
               Seed:   scripts/seed_companies.py

Skill protocol: skills/base.py — SkillResult, NormalizedJob, Evidence, RunContext
ATS connectors: skills/ats/{greenhouse,lever,ashby}/skill.py
Harnesses:      harnesses/{job_discovery,article_discovery,application_packet,browser_application}/v0.py
Validators:     harnesses/validators/{base,job,article_signal,recommendation,application_packet,browser_action,retry}.py
Trace logger:   app/tracing/logger.py — TraceLogger
Optimizer:      optimizers/meta_harness_loop.py + optimizers/search_controller.py
Eval runners:   evals/runners/{evaluate_job_discovery,evaluate_article_signals,evaluate_application_packet}.py
Prompts:        prompts/article_signal_classify.txt, prompts/cover_letter_draft.txt

LLM:            claude-haiku-4-5-20251001 (cheapest); set ANTHROPIC_API_KEY to enable
                All harnesses degrade gracefully to heuristic mode without API key.
```
