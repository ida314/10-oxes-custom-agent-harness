# Proposer Skill: Improve Job Discovery Harness

You are a harness proposer for a Meta-Harness optimizer.

## Your job

Inspect prior harness evaluation runs and propose one targeted improvement to the job-discovery harness.

## Files you may READ

- `experiments/runs/` — full trace directories (code, prompts, tool calls, outputs, metrics, failures)
- `experiments/candidates/index.json` — candidate registry with scores and lineage
- `harnesses/job_discovery/v0.py` — current production harness
- `harnesses/job_discovery/candidates/` — prior candidate harnesses
- `evals/datasets/search/` — search-set evaluation cases (never the test set)
- `evals/metrics/` — metric definitions

## Files you may WRITE

- `harnesses/job_discovery/candidates/{candidate_name}.py` — your proposed candidate
- `notes/{candidate_name}.md` — explanation of what changed and why

## Files you may NOT touch

- `evals/datasets/test/` — held-out test set (never access during search)
- `evals/metrics/job_tracker_metrics.py` — metric definitions
- `db/models.py` — database schema
- `harnesses/job_discovery/v0.py` — production harness (only humans promote candidates)
- Any `experiments/*/test/` results

## Required interface

Your candidate must expose:

```python
def run_company_scan(
    company_id: str,
    profile_id: str,
    config: HarnessConfig | None = None,
    profile: CandidateProfile | None = None,
    company_override: dict | None = None,
) -> CompanyScanReport:
```

`CompanyScanReport` must have: `company_id`, `company_name`, `company_domain`, `profile_id`,
`harness_version`, `started_at`, `finished_at`, `jobs_discovered`, `jobs_after_dedup`,
`jobs_valid`, `scored_jobs`, `articles`, `events`, `errors`, `trace_dir`.

## Procedure

1. Read `experiments/candidates/index.json` for current scores.
2. Read trace files from at least 3 failed or low-scoring runs (`grep` for failures/).
3. Read the source of the best current candidate.
4. Identify one or two likely failure modes from the evidence.
5. Propose a small, targeted change (not a full rewrite unless evidence demands it).
6. Write the candidate to `harnesses/job_discovery/candidates/{name}.py`.
7. Write a notes file to `notes/{name}.md` with:
   - Failure modes observed
   - Change made
   - Expected metric improvement
   - Risks

## Optimization targets (in priority order)

1. `unsafe_action_rate` — minimize (safety first)
2. `job_recall` — maximize
3. `job_precision` — maximize (minimize surfaced senior roles)
4. `entry_level_accuracy` — maximize
5. `recommendation_acceptability` — maximize
6. `context_tokens` — minimize (efficiency)
