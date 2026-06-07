# evals/

**Shared infrastructure (used by both systems).** Benchmark datasets, scoring functions, and evaluation runners.

---

## Directory structure

```
evals/
  datasets/
    job_tracker_seed.jsonl       ← 50 hand-labeled cases (all companies)
    search/
      job_tracker_search.jsonl   ← 40-case search split (optimizer may use)
    test/
      job_tracker_test.jsonl     ← 10-case held-out test split (NEVER expose to optimizer)
    article_signal_seed.jsonl    ← 15 article signal cases
  metrics/
    job_tracker_metrics.py       ← 6 scoring functions + CLI
    __init__.py
  runners/
    evaluate_job_discovery.py
    evaluate_article_signals.py
    evaluate_application_packet.py
    __init__.py
```

---

## The search/test split rule

**This is a hard constraint — never violate it.**

| Split | Who may use it |
|-------|---------------|
| `search/` | Optimizer loop, development, debugging |
| `test/` | Manual evaluation only — call with `allow_test=True` explicitly |

The test split exists to measure generalization. If the optimizer ever sees test scores during search, the Pareto frontier is meaningless.

---

## Metrics (`metrics/job_tracker_metrics.py`)

| Metric | Case type | What it measures |
|--------|-----------|-----------------|
| `job_discovery_recall` | job_discovery (+) | Did the agent find real entry-level roles? |
| `job_discovery_precision` | job_discovery (−) | Did it avoid false positives (senior, wrong type)? |
| `article_relevance` | article_discovery | Signal-to-noise in the intelligence feed |
| `fit_score_accuracy` | fit_scoring | Graded with tolerance bands (not binary) |
| `application_safety_accuracy` | application_safety | Guards against stale/senior role recommendations |
| `deduplication_f1` | deduplication | Pair-level F1 |

```bash
# Score predictions against the seed dataset
python -m evals.metrics.job_tracker_metrics --predictions predictions.jsonl
```

---

## Runners

```bash
# Job discovery eval (search split)
python evals/runners/evaluate_job_discovery.py

# Article signals eval
python evals/runners/evaluate_article_signals.py

# Application packet eval
python evals/runners/evaluate_application_packet.py
```

Each runner:
- Loads a harness by file path
- Runs on the JSONL dataset (search split by default)
- Captures full traces
- Computes scalar metrics
- Saves `metrics.json`
- Writes summary rows to the `eval_scores` DB table

---

## Adding new eval cases

Add cases to `evals/datasets/job_tracker_seed.jsonl` following the existing schema (`id`, `case_type`, `company`, `is_negative`, `metric`, `input`, `expected`, `source`). Re-run the search/test split script to redistribute cases. Never add to the test split directly.
