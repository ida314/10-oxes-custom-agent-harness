# Career Agent Harness System

Two complementary systems for job-search intelligence and self-improving harness engineering.

> New here? Start with **[docs/ONBOARDING.md](docs/ONBOARDING.md)** for a guided walkthrough of each system.

---

## System 1 — Job-Search Intelligence

Finds entry-level software roles, discovers company signals (articles, events, interviews), and produces ranked, validated, human-approvable recommendations. Nothing is auto-submitted.

```
skills/ats/             ──►  harnesses/job_discovery/    ──►  DB (jobs, articles, events)
skills/company_research/ ──►  harnesses/article_discovery/ ──►  approval_items table
                              harnesses/application_packet/ ──►  ApplicationPacket
                              harnesses/browser_application/ ──►  form fills (dry-run until approved)
                                      │
                              harnesses/validators/          ──►  blocks invalid outputs
```

**Primary entry points:**

| What | How |
|------|-----|
| Company scan | `from harnesses.job_discovery.v0 import run_company_scan` |
| Article scoring | `from harnesses.article_discovery.v0 import score_articles` |
| Application packet | `from harnesses.application_packet.v0 import generate_application_packet` |
| Browser assist | `from harnesses.browser_application.v0 import run_browser_assist` |

**Key directories for System 1:**

| Path | Role |
|------|------|
| `harnesses/job_discovery/` | ATS-first pipeline → `CompanyScanReport` |
| `harnesses/article_discovery/` | Signal classification → `ArticleDiscoveryReport` |
| `harnesses/application_packet/` | Cover letter, tailoring, Q&A, referral |
| `harnesses/browser_application/` | Assisted form filling — dry-run by default |
| `harnesses/validators/` | Pure-Python validators (no LLM) for every output type |
| `skills/ats/` | Greenhouse / Lever / Ashby JSON API connectors |
| `skills/company_research/` | Careers page, engineering blog, events, articles |
| `prompts/` | LLM prompt templates (never inline in Python) |
| `evals/` | Datasets, metrics, and runners for System 1 outputs |

---

## System 2 — Harness Optimizer

Reads raw execution traces from System 1, proposes improved harness candidates, and tracks a Pareto frontier across six objectives. The optimizer never auto-promotes a candidate to production — a human copies the winner to `v1.py`.

```
experiments/runs/  ──►  optimizers/meta_harness_loop.py  ──►  harnesses/*/candidates/
                              │                                       │
                   search_controller.py (Thompson)          experiments/candidates/index.json
                   (beta sampling over metrics)
```

**Primary entry point:**

```bash
python optimizers/meta_harness_loop.py --iterations 5
```

**Key directories for System 2:**

| Path | Role |
|------|------|
| `optimizers/` | Meta-Harness loop + Thompson sampling search controller |
| `skills/meta_harness/` | Proposer skill definition and write-permission spec |
| `harnesses/job_discovery/candidates/` | Proposed harness candidates (never `v*.py`) |
| `experiments/candidates/index.json` | Candidate registry with lineage + Pareto scores |
| `experiments/runs/` | Raw trace files written by System 1, read by the proposer |
| `notes/` | Proposer agent reasoning notes (one file per candidate) |

**Write-access rule:** the optimizer may only write to `harnesses/*/candidates/`, `notes/`, and `skills/meta_harness/`. It never touches production harnesses or eval datasets.

---

## Shared Infrastructure

| Path | Role |
|------|------|
| `db/` | Postgres schema (15 tables), Alembic migrations, Docker Compose |
| `app/tracing/` | `TraceLogger` — creates `experiments/runs/{ts}/` directories |
| `tests/` | 174 tests, no live network, no Docker required |
| `scripts/` | Operational scripts (`seed_companies.py`) |

---

## Quick Start

```bash
# 1. Create virtualenv and install
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

# 2. Start Postgres (only needed for DB-backed runs)
docker-compose up -d

# 3. Configure environment
cp .env.example .env
# Add ANTHROPIC_API_KEY to .env for LLM-backed runs; all code degrades to heuristics without it.

# 4. Run migrations and seed companies
DATABASE_URL=postgresql://career_agent:career_agent@localhost:5432/career_agent \
  alembic upgrade head
DATABASE_URL=postgresql://career_agent:career_agent@localhost:5432/career_agent \
  python scripts/seed_companies.py

# 5. Verify — no Docker or API key needed
pytest tests/ -q   # should print 174 passed

# 6. System 1 — run a company scan
DATABASE_URL=... python -c "
from harnesses.job_discovery.v0 import run_company_scan, HarnessConfig
report = run_company_scan('COMPANY_UUID_HERE', 'profile-01', HarnessConfig())
print(f'Jobs found: {report.jobs_after_dedup}')
"

# 7. System 2 — run the optimizer loop
python optimizers/meta_harness_loop.py --iterations 5
```

---

## Safety Guarantees

- **No auto-submit.** `approval_status` is always `"pending"` until a human explicitly approves.
- **No validator bypass.** Every LLM output passes a pure-Python `is_valid_*()` before being saved.
- **No optimizer access to test data.** `evals/datasets/test/` is never touched by the optimization loop.
- **No fabricated content.** `is_valid_application_packet` rejects altered dates, GPAs, or employer names.

See [docs/DECISIONS.md](docs/DECISIONS.md) for the full reasoning behind each constraint.

---

## Documentation Index

| File | Purpose |
|------|---------|
| [docs/ONBOARDING.md](docs/ONBOARDING.md) | New-developer guide for both systems |
| [docs/PROJECT_BRIEF.md](docs/PROJECT_BRIEF.md) | Product goals and what not to build |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | DB schema, skill library, trace FS, eval runner |
| [docs/BUILD_PLAN.md](docs/BUILD_PLAN.md) | Phase 0–11 deliverables and acceptance criteria |
| [docs/DECISIONS.md](docs/DECISIONS.md) | ADR-style log of architectural decisions |
| [docs/STATE.md](docs/STATE.md) | Current project state and known remaining items |
| [TODO.md](TODO.md) | Actionable phase-by-phase checklist |
