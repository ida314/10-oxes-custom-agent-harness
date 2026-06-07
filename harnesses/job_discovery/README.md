# harnesses/job_discovery/

**System 1.** ATS-first job discovery pipeline for a single company.

---

## Entry point

```python
from harnesses.job_discovery.v0 import run_company_scan, HarnessConfig, CandidateProfile

config = HarnessConfig(dry_run=True)   # dry_run=True skips DB writes
report = run_company_scan(company_id, profile_id, config)
# report: CompanyScanReport
```

## Pipeline steps

1. Load company + profile from DB (or use defaults in `dry_run=True`)
2. Try ATS connectors in order: Greenhouse → Lever → Ashby
3. Fall back to `find_careers_page` if ATS confidence is low
4. Normalize and deduplicate by `normalized_hash`
5. Score jobs: `entry_level_score` (title heuristic) + `fit_score` (skill overlap)
6. Run `find_recent_articles` and `find_events` for signal discovery
7. Generate recommendations (LLM or heuristic stub)
8. Validate recommendations with `harnesses/validators/recommendation.py`
9. Write to Postgres + `experiments/runs/{ts}/` trace directory

## Files

| File | Purpose |
|------|---------|
| `v0.py` | Production harness — do not edit programmatically |
| `candidates/` | Meta-Harness optimizer writes proposed improvements here |

## Outputs

`CompanyScanReport` contains:
- `jobs_found` / `jobs_after_dedup` counts
- `scored_jobs: list[ScoredJob]` — each with `entry_level_score`, `fit_score`, `recommendation`
- `articles: list[ArticleSignal]`
- `events: list[Event]`
- `trace_dir: Path` — location of the full trace for this run
