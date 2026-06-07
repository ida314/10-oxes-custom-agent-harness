# harnesses/

Executable workflow modules that orchestrate skills, call LLMs, validate outputs, and write to Postgres and the trace filesystem.

---

## System 1 — Job-Search Intelligence

| Directory | Entry function | Returns |
|-----------|---------------|---------|
| `job_discovery/` | `run_company_scan(company_id, profile_id, config)` | `CompanyScanReport` |
| `article_discovery/` | `score_articles(articles, profile, config)` | `ArticleDiscoveryReport` |
| `application_packet/` | `generate_application_packet(job_id, profile, config)` | `ApplicationPacketResult` |
| `browser_application/` | `run_browser_assist(packet, job_url, config)` | `BrowserAssistResult` |

Each harness follows the AutoHarness pattern:
1. **Propose** — LLM or heuristic generates output
2. **Validate** — `harnesses/validators/` checks the output in pure Python
3. **Save or route** — valid outputs go to DB; invalid outputs go to human review

Production harnesses are versioned files: `v0.py`, `v1.py`, etc. The current production version is `v0.py` for all domains.

---

## System 2 — Optimizer Candidates

| Directory | Owner | Purpose |
|-----------|-------|---------|
| `job_discovery/candidates/` | Meta-Harness optimizer | Proposed harness files (never auto-promoted) |

The optimizer writes proposed harness code here. A human reviews and copies a candidate to `v1.py` to promote it to production.

---

## validators/

Pure-Python output validators used by all System 1 harnesses. No LLM calls.

| File | What it validates |
|------|------------------|
| `base.py` | `ValidationResult` model + `merge()` |
| `job.py` | Job listings (source URL, entry-level status, safety) |
| `article_signal.py` | Article signals (evidence grounding, source URL) |
| `recommendation.py` | Recommendations (validity, safety) |
| `application_packet.py` | Packets (no fabrication, no altered facts) |
| `browser_action.py` | Browser actions (submit/send gated by approval) |
| `retry.py` | `validate_with_retry()` — retry with feedback, route to human on exhaustion |

See [validators/README.md](validators/README.md) for details.

---

## Harness versioning convention

```
harnesses/{domain}/
  v0.py          ← current production harness
  v1.py          ← (future) promoted from candidates/
  candidates/    ← Meta-Harness optimizer writes here ONLY
```

Never modify `v*.py` files programmatically. Human promotion only.
