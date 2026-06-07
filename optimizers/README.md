# optimizers/

**System 2.** Meta-Harness optimization loop and Thompson sampling search controller.

---

## Files

### `meta_harness_loop.py`
Main optimization loop. Implements the Meta-Harness paper's core cycle:

```
1. Bootstrap — ensure at least one candidate exists
2. Evaluate  — run current candidates against search split
3. Propose   — proposer agent writes one new candidate
4. Validate  — static interface check (must expose run_company_scan)
5. Score     — eval on search split
6. Register  — add to candidates/index.json with parent_id lineage
7. Pareto    — update frontier across 6 objectives
8. Repeat
```

```bash
# Dry-run (stub proposer, no API key needed)
python optimizers/meta_harness_loop.py --iterations 5

# With real LLM proposer
ANTHROPIC_API_KEY=sk-... python optimizers/meta_harness_loop.py --iterations 5
```

### `search_controller.py`
Thompson sampling over the candidate population. Selects which parent candidate to mutate next, balancing exploitation of high-scorers with exploration of less-tried branches.

```python
from optimizers.search_controller import SearchController, select_candidate_thompson

controller = SearchController()
next_parent = select_candidate_thompson(controller.population)
```

---

## Pareto objectives

The frontier tracks 6 objectives simultaneously:

| Metric | Direction | Weight |
|--------|-----------|--------|
| `job_recall` | maximize | +0.25 |
| `job_precision` | maximize | +0.20 |
| `entry_level_accuracy` | maximize | +0.20 |
| `recommendation_acceptability` | maximize | +0.20 |
| `unsafe_action_rate` | minimize | −0.30 |
| `context_tokens` | minimize | −0.05 |

---

## Candidate registry

`experiments/candidates/index.json` is the live registry of all candidates with their scores, lineage, and Pareto status. Never edit this file manually — it is maintained by the loop.

---

## Promoting a candidate to production

The optimizer never promotes automatically. When a candidate consistently outperforms `v0.py`:

1. Review the diff between the candidate and `harnesses/job_discovery/v0.py`
2. Run `pytest tests/ -q` to verify no regressions
3. Copy the candidate to `harnesses/job_discovery/v1.py`
4. Update `docs/STATE.md` and `TODO.md`

---

## Write-access rule

The loop enforces this programmatically:

```
ALLOWED:   harnesses/*/candidates/{name}.py
           notes/{name}.md
           skills/meta_harness/

FORBIDDEN: evals/
           db/
           harnesses/*/v*.py
           experiments/*/test/
```
