"""
job_tracker_metrics.py

Evaluation metrics for the career-intelligence agent benchmark suite.

Metric functions: score_X(prediction, expected) -> float in [0, 1]
Use score_case(case, prediction) to dispatch a single case.
Use evaluate_jsonl(dataset, predictions) for batch evaluation.

Grading rubrics are embedded in each function's docstring.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Global thresholds (override via env or caller if needed)
# ---------------------------------------------------------------------------

STALENESS_THRESHOLD_DAYS: int = 90

# Fit score tolerance bands
FIT_SCORE_NEAR_TOLERANCE: float = 0.10    # within 0.10 of range → 0.70 credit
FIT_SCORE_PARTIAL_TOLERANCE: float = 0.20 # within 0.20 of range → 0.30 credit

ENTRY_LEVEL_TAGS: frozenset[str] = frozenset(
    {"entry_level", "new_grad", "intern", "junior", "associate"}
)


# ---------------------------------------------------------------------------
# 1. Job Discovery — Recall
#    Positive cases: agent SHOULD surface ≥ N entry-level roles.
# ---------------------------------------------------------------------------

def score_job_discovery_recall(prediction: dict, expected: dict) -> float:
    """
    Rubric
    ------
    1.00  ≥ min_roles_found roles found; all entry-level; all match title patterns
    0.75  ≥ min_roles_found roles found; entry-level but some miss title patterns
    0.50  < min_roles_found but at least one valid entry-level role found
    0.25  Roles found but none are entry-level or none match required patterns
    0.00  No roles found at all

    prediction keys
    ---------------
    roles_found : list[{title, level, required_experience_years, url, posted_date}]

    expected keys
    -------------
    min_roles_found                    : int   (default 1)
    role_title_must_match_any          : list[str]
    must_not_require_years_experience_above : int (default 2)
    """
    roles: list[dict] = prediction.get("roles_found", [])
    if not roles:
        return 0.0

    min_req: int = expected.get("min_roles_found", 1)
    title_patterns: list[str] = [
        p.lower() for p in expected.get("role_title_must_match_any", [])
    ]
    max_years: int = expected.get("must_not_require_years_experience_above", 2)

    def _is_entry_level(r: dict) -> bool:
        level_ok = r.get("level", "").lower() in ENTRY_LEVEL_TAGS
        years_ok = r.get("required_experience_years", 0) <= max_years
        return level_ok and years_ok

    def _title_matches(r: dict) -> bool:
        if not title_patterns:
            return True
        title = r.get("title", "").lower()
        return any(p in title for p in title_patterns)

    entry_roles = [r for r in roles if _is_entry_level(r)]
    matching_roles = [r for r in entry_roles if _title_matches(r)]

    if len(matching_roles) >= min_req:
        all_entry = len(entry_roles) == len(roles)
        return 1.0 if all_entry else 0.75
    if len(entry_roles) >= min_req:
        return 0.75
    if entry_roles:
        return 0.50
    if roles:
        return 0.25
    return 0.0


# ---------------------------------------------------------------------------
# 2. Job Discovery — Precision
#    Negative cases: agent must NOT surface senior / stale / off-type roles.
# ---------------------------------------------------------------------------

def score_job_discovery_precision(prediction: dict, expected: dict) -> float:
    """
    Rubric
    ------
    1.00  Correctly rejected; rejection_reason matches expected
    0.50  Correctly rejected; wrong or missing rejection_reason
    0.00  Role surfaced when it should have been rejected

    prediction keys
    ---------------
    should_surface_role : bool
    rejection_reason    : str | None  ("senior_role" | "stale_role" | "wrong_type")

    expected keys
    -------------
    should_surface_role : bool  (always False for negative cases)
    rejection_reason    : str
    """
    exp_surface: bool = expected.get("should_surface_role", False)
    pred_surface: bool = prediction.get("should_surface_role", True)

    if pred_surface != exp_surface:
        return 0.0

    if exp_surface:
        return 1.0  # Both say "surface" — precision filter not triggered

    exp_reason: str | None = expected.get("rejection_reason")
    pred_reason: str | None = prediction.get("rejection_reason")
    if exp_reason and pred_reason and exp_reason == pred_reason:
        return 1.0
    return 0.5


# ---------------------------------------------------------------------------
# 3. Article Discovery — Relevance
#    Classify whether an article is useful company intelligence for job seekers.
# ---------------------------------------------------------------------------

def score_article_relevance(prediction: dict, expected: dict) -> float:
    """
    Rubric
    ------
    1.00  Correct classification (relevant/irrelevant); confidence ≥ 0.50
    0.50  Correct classification; confidence < 0.50
    0.00  Wrong classification

    Relevant articles for job seekers include: hiring announcements, engineering
    culture posts, product launches (signal of growth), layoffs, tech stack info.
    Irrelevant: stock price, executive lifestyle, generic industry reports,
    regulatory filings unrelated to headcount.

    prediction keys
    ---------------
    is_relevant      : bool
    relevance_score  : float  (0–1 confidence)
    topics           : list[str]  (optional, informational)

    expected keys
    -------------
    is_relevant     : bool
    relevant_topics : list[str]  (optional, for qualitative review)
    """
    exp_relevant: bool = expected.get("is_relevant", True)
    pred_relevant: bool | None = prediction.get("is_relevant")

    if pred_relevant is None:
        return 0.0
    if pred_relevant != exp_relevant:
        return 0.0

    confidence: float = prediction.get(
        "relevance_score", prediction.get("confidence", 0.7)
    )
    return 1.0 if confidence >= 0.50 else 0.50


# ---------------------------------------------------------------------------
# 4. Fit Scoring — Accuracy
#    Agent scores how well a candidate matches a specific posting.
# ---------------------------------------------------------------------------

def score_fit_accuracy(prediction: dict, expected: dict) -> float:
    """
    Rubric
    ------
    1.00  fit_score falls within expected [lo, hi]
    0.70  fit_score within 0.10 of range boundary (near miss)
    0.30  fit_score within 0.20 of range boundary (partial credit)
    0.00  fit_score > 0.20 outside range, or prediction missing

    fit_score is a float in [0, 1]:
      0.0–0.39  Do not apply (significant gaps)
      0.40–0.64 Borderline (apply with caveats)
      0.65–0.84 Good fit
      0.85–1.00 Strong fit

    prediction keys
    ---------------
    fit_score       : float
    key_matches     : list[str]
    key_gaps        : list[str]
    recommendation  : "apply" | "borderline" | "skip"

    expected keys
    -------------
    fit_score_range : [float, float]
    recommendation  : str
    """
    fit_score: float | None = prediction.get("fit_score")
    if fit_score is None:
        return 0.0

    lo, hi = expected.get("fit_score_range", [0.0, 1.0])
    if lo <= fit_score <= hi:
        return 1.0

    distance = min(abs(fit_score - lo), abs(fit_score - hi))
    if distance <= FIT_SCORE_NEAR_TOLERANCE:
        return 0.70
    if distance <= FIT_SCORE_PARTIAL_TOLERANCE:
        return 0.30
    return 0.0


# ---------------------------------------------------------------------------
# 5. Application Safety — Accuracy
#    Agent determines whether a posting is safe to act on.
# ---------------------------------------------------------------------------

def score_application_safety(prediction: dict, expected: dict) -> float:
    """
    Rubric
    ------
    1.00  Correct safe/unsafe decision AND correct rejection_reason (if unsafe)
    0.50  Correct decision; missing or wrong rejection_reason
    0.00  Wrong decision (applied to stale/senior, or blocked a fresh/valid role)

    Unsafe conditions:
      "stale_role"      — posted > STALENESS_THRESHOLD_DAYS (90) days ago
      "senior_role"     — requires seniority above entry-level
      "duplicate"       — role already tracked or applied to
      "closed_role"     — listing explicitly marked closed

    prediction keys
    ---------------
    is_safe_to_apply : bool
    rejection_reason : str | None
    confidence       : float  (optional)

    expected keys
    -------------
    is_safe_to_apply : bool
    rejection_reason : str | None
    """
    exp_safe: bool | None = expected.get("is_safe_to_apply")
    pred_safe: bool | None = prediction.get("is_safe_to_apply")

    if exp_safe is None or pred_safe is None:
        return 0.0
    if exp_safe != pred_safe:
        return 0.0
    if exp_safe:
        return 1.0  # Both agree it's safe — no rejection reason needed

    exp_reason: str | None = expected.get("rejection_reason")
    pred_reason: str | None = prediction.get("rejection_reason")
    if exp_reason and pred_reason and exp_reason == pred_reason:
        return 1.0
    return 0.5


# ---------------------------------------------------------------------------
# 6. Deduplication — F1
#    Agent identifies duplicate job postings across sources.
# ---------------------------------------------------------------------------

def score_deduplication_f1(prediction: dict, expected: dict) -> float:
    """
    Rubric
    ------
    1.00  All duplicate pairs correctly identified; zero false positives (F1 = 1)
    0.5x  Partial identification; proportional to F1 score
    0.00  No correct pairs / all false positives

    A "duplicate" is two postings representing the same open position (e.g.,
    same role cross-posted on Lever + company careers page, or the same listing
    reposted after expiry). Different locations for the same role title are NOT
    duplicates unless the application portal is identical.

    prediction keys
    ---------------
    duplicate_groups : list[list[str]]  (each inner list = one cluster of dupes)

    expected keys
    -------------
    duplicate_groups : list[list[str]]
    """
    def _to_pairs(groups: list[list[str]]) -> set[tuple[str, str]]:
        pairs: set[tuple[str, str]] = set()
        for g in groups:
            s = sorted(g)
            for i in range(len(s)):
                for j in range(i + 1, len(s)):
                    pairs.add((s[i], s[j]))
        return pairs

    exp_pairs = _to_pairs(expected.get("duplicate_groups", []))
    pred_pairs = _to_pairs(prediction.get("duplicate_groups", []))

    if not exp_pairs and not pred_pairs:
        return 1.0
    if not exp_pairs:
        return 0.0  # Predicted duplicates where none exist

    tp = len(exp_pairs & pred_pairs)
    precision = tp / len(pred_pairs) if pred_pairs else 0.0
    recall = tp / len(exp_pairs)

    if precision + recall == 0.0:
        return 0.0
    return round(2 * precision * recall / (precision + recall), 4)


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

METRIC_DISPATCH: dict[str, Any] = {
    "job_discovery_recall":      score_job_discovery_recall,
    "job_discovery_precision":   score_job_discovery_precision,
    "article_relevance":         score_article_relevance,
    "fit_score_accuracy":        score_fit_accuracy,
    "application_safety_accuracy": score_application_safety,
    "deduplication_f1":          score_deduplication_f1,
}


def score_case(case: dict, prediction: dict) -> dict[str, Any]:
    """Score one benchmark case against an agent prediction. Returns scored result dict."""
    metric_key = case["metric"]
    fn = METRIC_DISPATCH.get(metric_key)
    if fn is None:
        raise ValueError(f"Unknown metric: {metric_key!r}")
    raw_score = fn(prediction, case["expected"])
    return {
        "id": case["id"],
        "case_type": case["case_type"],
        "company": case["company"],
        "metric": metric_key,
        "is_negative": case.get("is_negative", False),
        "score": round(raw_score, 4),
        "passed": raw_score >= 0.75,
    }


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def aggregate(scored_results: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Roll up per-case scores into per-metric, per-company, and overall averages.

    Returns
    -------
    {
        "overall"    : float,
        "by_metric"  : {metric_name: avg_score},
        "by_company" : {company: avg_score},
        "n_cases"    : int,
        "n_passed"   : int,   # score >= 0.75
        "pass_rate"  : float,
    }
    """
    by_metric: dict[str, list[float]] = {}
    by_company: dict[str, list[float]] = {}

    for r in scored_results:
        by_metric.setdefault(r["metric"], []).append(r["score"])
        by_company.setdefault(r["company"], []).append(r["score"])

    def _avg(lst: list[float]) -> float:
        return round(sum(lst) / len(lst), 4) if lst else 0.0

    all_scores = [r["score"] for r in scored_results]
    n_passed = sum(1 for s in all_scores if s >= 0.75)

    return {
        "overall":    _avg(all_scores),
        "by_metric":  {m: _avg(s) for m, s in sorted(by_metric.items())},
        "by_company": {c: _avg(s) for c, s in sorted(by_company.items())},
        "n_cases":    len(scored_results),
        "n_passed":   n_passed,
        "pass_rate":  round(n_passed / len(scored_results), 4) if scored_results else 0.0,
    }


# ---------------------------------------------------------------------------
# Batch evaluation helpers
# ---------------------------------------------------------------------------

def evaluate_jsonl(
    dataset_path: str | Path,
    predictions_path: str | Path,
) -> dict[str, Any]:
    """
    Load dataset JSONL and predictions JSONL, score every case, return full report.

    Predictions file format (one JSON object per line):
        {"id": "<case_id>", "prediction": {<metric-specific fields>}}

    Missing predictions receive score 0.0.
    """
    cases: dict[str, dict] = {}
    with open(dataset_path) as fh:
        for line in fh:
            line = line.strip()
            if line:
                case = json.loads(line)
                cases[case["id"]] = case

    preds: dict[str, dict] = {}
    with open(predictions_path) as fh:
        for line in fh:
            line = line.strip()
            if line:
                obj = json.loads(line)
                preds[obj["id"]] = obj.get("prediction", {})

    results = []
    for case_id, case in cases.items():
        pred = preds.get(case_id, {})
        results.append(score_case(case, pred))

    return {"results": results, "aggregate": aggregate(results)}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3:
        print("Usage: python job_tracker_metrics.py <dataset.jsonl> <predictions.jsonl>")
        sys.exit(1)

    report = evaluate_jsonl(sys.argv[1], sys.argv[2])
    agg = report["aggregate"]

    print("\n=== Job Tracker Benchmark Results ===")
    print(
        f"Overall: {agg['overall']:.3f}  "
        f"({agg['n_passed']}/{agg['n_cases']} passed @ ≥0.75, "
        f"pass_rate={agg['pass_rate']:.1%})"
    )
    print("\nBy metric:")
    for metric, score in agg["by_metric"].items():
        bar = "█" * int(score * 20)
        print(f"  {metric:<38} {score:.3f}  {bar}")
    print("\nBy company:")
    for company, score in agg["by_company"].items():
        bar = "█" * int(score * 20)
        print(f"  {company:<20} {score:.3f}  {bar}")
    print()
