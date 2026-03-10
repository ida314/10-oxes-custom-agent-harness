# Architecture Decision Records

## 2026-06-07 — Eval benchmark schema and metric design

### What was decided

Created the initial benchmark suite for the career-intelligence agent under `evals/`.

**Files produced:**
- `evals/datasets/job_tracker_seed.jsonl` — 50 evaluation cases
- `evals/metrics/job_tracker_metrics.py` — 6 scoring functions + CLI

---

### Schema shape

Each JSONL case carries: `id`, `case_type`, `company`, `is_negative`, `negative_reason`, `metric`, `input`, `expected`, `source`.

**Why this shape instead of a flat CSV or separate files per company:**
- JSONL streams without loading the whole set into memory; easy to filter with `jq` or Python.
- `input` and `expected` are typed per `case_type`, so the schema is self-describing rather than having many nullable columns.
- `source.manually_labeled` + `source.url` lets the grader distinguish ground truth derived from live web data versus human annotation — important for staleness auditing.

**Why `is_negative` / `negative_reason` as top-level fields:**
- Precision and recall metrics need to split on this quickly without parsing `expected`.
- Downstream analyses (e.g. "what is the false-positive rate on senior-role rejection?") can `grep negative_reason` without touching metric code.

---

### Metric choices

| Metric | Case type | Rationale |
|---|---|---|
| `job_discovery_recall` | job_discovery (+) | Primary success signal: did the agent find real entry-level roles? |
| `job_discovery_precision` | job_discovery (−) | Catches false positives: senior roles, wrong types surfaced to new grads |
| `article_relevance` | article_discovery | Keeps the intelligence feed signal-to-noise high |
| `fit_score_accuracy` | fit_scoring | Core agent value-add; graded with tolerance bands (not binary) |
| `application_safety_accuracy` | application_safety | Guards against the agent triggering applications to stale/senior roles |
| `deduplication_f1` | deduplication | Pair-level F1 is standard for clustering; preserves partial credit |

**Rejected alternatives:**
- MAP/nDCG for job discovery — over-engineered for a 1–3 result use case; recall + precision captures the same signal more interpretably.
- Exact-match for fit scores — scores are inherently continuous judgments; range-based grading with tolerance bands matches real annotator agreement.
- Per-field breakdown for fit scoring — deferred until we have more labeled data; current `key_matches` / `key_gaps` fields are logged for qualitative review but not scored yet.

---

### Staleness threshold: 90 days

Chosen as a practical upper bound for an open requisition to still be worth applying to. No empirical data backs this yet — treat it as a tunable constant (`STALENESS_THRESHOLD_DAYS` in `job_tracker_metrics.py`). Should be revisited once we have real application outcome data.

---

### Fit score rubric bands

```
1.00  score in [lo, hi]          (within labeled range)
0.70  score within 0.10 of bound (near miss)
0.30  score within 0.20 of bound (partial credit)
0.00  score > 0.20 outside range
```

The 0.10/0.20 bands reflect expected inter-annotator variance on subjective fit judgments. Tighter bands would require human rater agreement studies first.

---

### Source URL policy

- **Live careers-page URLs** (10 cases): used for job_discovery cases where `manually_labeled: false`. The agent is expected to verify by scraping the URL.
- **`url: null, manually_labeled: true`** (40 cases): used for synthetic inputs (fit scoring, safety, deduplication) and article cases where specific article URLs are ephemeral. The labeled class of content is documented in `source.notes`.

Specific job posting URLs (e.g. `careers.google.com/jobs/results/1234567`) were deliberately avoided — they rot within weeks. Root careers-page URLs are stable enough for a seed dataset.

---

### Negative case coverage

20 of 50 cases are negative. Breakdown:
- 5 × `senior_role` (one per company, job_discovery_precision)
- 5 × `stale_role` (one per company, application_safety)
- 5 × `irrelevant_topic` (one per company, article_relevance)
- 5 × `poor_fit` (one per company, fit_score with low expected range)

This 40/60 negative/positive split is intentional: the agent's biggest failure modes in early testing are expected to be false positives (surfacing bad roles) rather than false negatives (missing good ones). Negative coverage is proportionally higher than positive to stress-test precision.

---

### Deduplication semantics

Two postings are duplicates if and only if they share the same underlying `job_id` (same ATS requisition). Different locations for the same title are **not** duplicates — each has a separate application portal. This is encoded in the `notes` field of each deduplication case.

The F1 metric operates on **pairs**, not clusters, which avoids the cluster-labeling ambiguity problem for the current case sizes.

---

### Pass threshold: 0.75

Cases with score ≥ 0.75 are counted as "passed" in the aggregate report. This is a soft threshold — a score of 0.75 corresponds roughly to "correct decision, minor quality gap" across all rubrics. It is not a hard gate; review `by_metric` breakdowns rather than the pass count alone.

---

## 2026-06-07 — Postgres as source of truth

**Decision:** Use Postgres from Phase 1. Do not start with loose JSON files for structured application state.

**Rationale:**
- Deduplication constraints (`UNIQUE` on `jobs.url` and `jobs.normalized_hash`) are hard to enforce correctly in flat files without coordination overhead.
- Multi-table joins (job + company + application + approval_item) are the natural query pattern for recommendation generation.
- The Meta-Harness loop needs reliable scalar history (eval_scores table) to power Thompson sampling.
- JSON files are appropriate only for eval datasets and raw execution traces, where schema flexibility matters more than relational integrity.

**What this means:** `db/models.py` and `db/migrations/` must be the first non-eval code written. No production data writes go to loose files.

---

## 2026-06-07 — Filesystem traces for raw execution history

**Decision:** Store every harness execution in a full directory under `experiments/runs/`, with verbatim prompts, model outputs, tool calls, and raw evidence.

**Rationale:**
- Meta-Harness's key design insight is that the proposer needs raw traces, not summaries, to diagnose failures. A compressed summary can hide the exact error that caused a false positive or missed job.
- The proposer agent uses `grep`, `cat`, and file search on the trace directory — standard tools that work on any directory tree without special infrastructure.
- Postgres stores scalar metrics and summary rows for fast querying; the filesystem stores raw artifacts for debugging.

**What this means:** do not skip or compress trace writes for performance. Every run creates a complete directory. Disk space is cheaper than debugging time.

---

## 2026-06-07 — LLMs propose; code validates; evals decide; humans approve external actions

**Decision:** No LLM output reaches a user, database, or external system without passing a typed Python validator first. No external action (submit, send, upload) happens without a human-approved `ApprovalItem`.

**Rationale:**
- AutoHarness showed that even capable LLMs take illegal actions when given unrestricted agency. The fix is an external verifiable control layer — not better prompting alone.
- Validators are pure Python: fast, deterministic, auditable, testable. LLM-based verification is slower and introduces circular failure modes.
- Human approval gates prevent the largest class of hard-to-reverse mistakes (submitted applications, sent messages, created accounts).

**What this means:** every `propose_*()` function must have a matching `is_valid_*()` validator. The validator must pass before the output is saved or acted on. Invalid outputs route to human review, not retry loops.

---

## 2026-06-07 — Start with deterministic connectors before agents

**Decision:** Phase 2 builds deterministic HTTP/scraping connectors for Greenhouse, Lever, Ashby, and generic careers pages. LLM calls are used only for ambiguous cases (Phase 3+), not for basic data ingestion.

**Rationale:**
- Most ATS platforms (Greenhouse, Lever, Ashby) have stable JSON APIs or predictable HTML. An LLM is not needed to read them.
- Deterministic connectors are easier to test (saved fixtures), faster, cheaper, and more reliable than LLM-based parsing for structured data.
- When connectors fail, you know exactly why. When LLMs fail on the same task, you get a different failure each time.
- This matches AutoHarness's principle of using learned/LLM logic only where deterministic code cannot handle the task.

**What this means:** no LLM calls in Phase 2. HTTP + BeautifulSoup/httpx first. LLM fallback only when structured parsing fails, and that fallback must be logged and scored.

---

## 2026-06-07 — No auto-apply / browser submission before validators and approval gates exist

**Decision:** Browser automation (Phase 11) is blocked until application packet generation (Phase 10) and all validators (Phase 7) are complete and passing tests.

**Rationale:**
- Auto-submission without validated content means the agent can submit fabricated experience, stale applications, wrong-fit roles, or duplicate applications.
- Each of these is hard to reverse (application already submitted) and potentially harmful to the user's candidacy.
- Building the approval gate infrastructure first means browser automation inherits correct safety behavior from day one rather than bolting it on afterward.

**What this means:** any PR that adds browser form submission, file upload, or account creation code is blocked until `approval_items` table, `ApprovalItem` model, and `is_allowed_browser_action` validator all exist and have passing tests.

---

## 2026-06-07 — Meta-Harness optimizer write access restricted to candidate files

**Decision:** The Meta-Harness proposer agent is given write access only to `harnesses/*/candidates/`, `notes/`, and `skills/meta_harness/`. It cannot modify eval datasets, eval metrics, DB models, or production harnesses (`v*.py` files).

**Rationale:**
- Giving the optimizer write access to evals would allow it to overfit to the eval set by modifying the grader — a classic adversarial optimization failure.
- Giving it write access to production harnesses would allow it to bypass validators or approval gates.
- Restricting to `candidates/` creates a clean separation: the optimizer proposes; a human promotes to production by copying the candidate to a versioned production file.
- This matches Meta-Harness's own experimental setup, where the proposer wrote single-file harness candidates into a controlled evaluation loop.

**What this means:** `optimizers/meta_harness_loop.py` must enforce write permissions programmatically (not just by convention). Any harness candidate that passes eval is promoted to production by a human, not by the optimizer itself.
