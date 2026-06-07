# skills/meta_harness/

**System 2.** Skill definition for the Meta-Harness proposer agent.

---

## Contents

### `propose_job_harness.md`

The skill specification used by the proposer agent in `optimizers/meta_harness_loop.py`. Defines:

- What the proposer reads (experiments/runs/ trace files, current candidates, search-set scores)
- What the proposer writes (one candidate file per invocation)
- Write-permission constraints (hard-coded in the loop)
- How to structure a valid candidate (must expose the `run_company_scan` interface)

---

## Write-permission constraints

The proposer may only write to:

```
harnesses/*/candidates/{name}.py
notes/{name}.md
skills/meta_harness/
```

It is forbidden from writing to:
- `evals/` — changing graders would corrupt metric history
- `db/` — schema is shared infrastructure
- `harnesses/*/v*.py` — production harnesses are human-promoted only
- `experiments/*/test/` — test split results must never be seen during optimization

These constraints are enforced in `optimizers/meta_harness_loop.py`, not just by convention.

---

## Adding a new proposer skill

If you want the proposer to optimize a different harness domain (e.g. `article_discovery`), create `skills/meta_harness/propose_article_harness.md` following the same structure as `propose_job_harness.md`.
