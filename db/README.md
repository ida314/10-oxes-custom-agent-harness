# db/

**Shared infrastructure.** Postgres schema, Alembic migrations, and table definitions.

Postgres is the source of truth for all structured state. Never use loose JSON files for production data.

---

## Quick start

```bash
# Start Postgres
docker-compose up -d

# Apply all migrations
DATABASE_URL=postgresql://career_agent:career_agent@localhost:5432/career_agent \
  alembic upgrade head

# Seed 5 target companies
DATABASE_URL=... python scripts/seed_companies.py
```

---

## Tables

### System 1 — Job-Search Intelligence

| Table | Purpose |
|-------|---------|
| `companies` | Target company registry |
| `company_sources` | Per-company source URLs (careers page, blog, LinkedIn) |
| `jobs` | Discovered job postings — UNIQUE on `url` and `normalized_hash` |
| `articles` | Discovered articles/blog posts with signal type + application angle |
| `events` | Hackathons, info sessions, career fairs |
| `people` | Contacts at target companies |
| `applications` | Application tracking (draft → submitted → outcome) |
| `application_packets` | Generated packets — `approval_status` always starts `"pending"` |
| `approval_items` | Human review queue for any external action |

### System 2 — Harness Optimizer

| Table | Purpose |
|-------|---------|
| `harness_candidates` | Candidate registry with lineage (`parent_id`) and search-set scores |
| `eval_scores` | Per-run metric values (search split only during optimization) |

### Shared instrumentation

| Table | Purpose |
|-------|---------|
| `agent_runs` | One row per harness execution, pointing to `trace_dir` |
| `tool_calls` | Verbatim tool call input/output for every run |
| `trace_events` | Sequence of events (prompt, output, validator, parser) per run |
| `skills` | Skill registry with status and version |

---

## Key constraints

- `jobs.url` — UNIQUE
- `jobs.normalized_hash` — UNIQUE (content-based deduplication)
- `application_packets.approval_status` — always `"pending"` until human approval
- All tables have `created_at` / `updated_at`
- Indexes on: `company_id`, `discovered_at`, `source_type`, `status`, score fields

---

## Files

| File | Purpose |
|------|---------|
| `models.py` | SQLModel definitions for all 15 tables |
| `migrations/` | Alembic migration history |
| `migrations/versions/fa4ed156d801_initial_schema.py` | Full initial schema migration |

---

## Running migrations

```bash
# Create a new migration after changing models.py
alembic revision --autogenerate -m "describe_the_change"

# Apply all pending migrations
alembic upgrade head

# Roll back one migration
alembic downgrade -1
```
