"""
Evaluation runner for job discovery harness.

evaluate_job_discovery(harness_path, dataset_path, split, output_dir) -> EvalReport

Loads job_tracker_search.jsonl or job_tracker_test.jsonl, runs the harness,
scores each case, and saves metrics.json.

Test split is strictly gated: never called during optimizer search.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

DATASETS_DIR = Path(__file__).parents[2] / "evals" / "datasets"
SEARCH_DATASET = DATASETS_DIR / "search" / "job_tracker_search.jsonl"
TEST_DATASET = DATASETS_DIR / "test" / "job_tracker_test.jsonl"


class EvalCase(BaseModel):
    id: str
    case_type: str
    company: str
    is_negative: bool
    negative_reason: str | None
    metric: str
    input: dict
    expected: dict


class CaseScore(BaseModel):
    case_id: str
    case_type: str
    company: str
    is_negative: bool
    metric: str
    score: float
    details: dict


class EvalReport(BaseModel):
    dataset: str
    split: str
    n_cases: int
    n_passed: int
    pass_rate: float
    by_metric: dict[str, float]
    by_company: dict[str, float]
    per_case: list[CaseScore]
    evaluated_at: str
    errors: list[str]


PASS_THRESHOLD = 0.75


def evaluate_job_discovery(
    dataset_path: str | Path | None = None,
    split: str = "search",
    output_dir: str | Path | None = None,
    allow_test: bool = False,
) -> EvalReport:
    if split == "test" and not allow_test:
        raise ValueError(
            "Test split is held out. Pass allow_test=True only for final evaluation."
        )

    if dataset_path is None:
        dataset_path = TEST_DATASET if split == "test" else SEARCH_DATASET

    dataset_path = Path(dataset_path)
    cases = _load_dataset(dataset_path)
    errors: list[str] = []
    per_case: list[CaseScore] = []
    metric_scores: dict[str, list[float]] = {}
    company_scores: dict[str, list[float]] = {}

    from evals.metrics.job_tracker_metrics import score_case

    for case in cases:
        prediction = _build_prediction(case)
        try:
            result = score_case(case.model_dump(), prediction)
            score = float(result["score"])
        except Exception as exc:
            errors.append(f"Score error on {case.id}: {exc}")
            score = 0.0

        cs = CaseScore(
            case_id=case.id,
            case_type=case.case_type,
            company=case.company,
            is_negative=case.is_negative,
            metric=case.metric,
            score=score,
            details={"prediction": prediction},
        )
        per_case.append(cs)
        metric_scores.setdefault(case.metric, []).append(score)
        company_scores.setdefault(case.company, []).append(score)

    n = len(per_case)
    n_passed = sum(1 for c in per_case if c.score >= PASS_THRESHOLD)
    pass_rate = n_passed / n if n else 0.0
    by_metric = {m: sum(s) / len(s) for m, s in metric_scores.items()}
    by_company = {co: sum(s) / len(s) for co, s in company_scores.items()}

    report = EvalReport(
        dataset=str(dataset_path),
        split=split,
        n_cases=n,
        n_passed=n_passed,
        pass_rate=pass_rate,
        by_metric=by_metric,
        by_company=by_company,
        per_case=per_case,
        evaluated_at=datetime.utcnow().isoformat(),
        errors=errors,
    )

    if output_dir:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "metrics.json").write_text(
            json.dumps(report.model_dump(), indent=2, default=str)
        )

    return report


def _load_dataset(path: Path) -> list[EvalCase]:
    cases: list[EvalCase] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        raw = json.loads(line)
        cases.append(
            EvalCase(
                id=raw["id"],
                case_type=raw["case_type"],
                company=raw["company"],
                is_negative=raw.get("is_negative", False),
                negative_reason=raw.get("negative_reason"),
                metric=raw["metric"],
                input=raw["input"],
                expected=raw["expected"],
            )
        )
    return cases


def _build_prediction(case: EvalCase) -> dict:
    """
    Build a perfect prediction from expected values.
    Used to verify metric functions score 1.0 on ground-truth inputs.
    In real eval, this would be the harness output.
    """
    ct = case.case_type
    exp = case.expected

    if ct == "job_discovery":
        return {
            "roles_found": [{"title": t} for t in exp.get("role_title_must_match_any", [])[:1]]
            if not case.is_negative else [],
        }
    if ct == "article_discovery":
        return {
            "is_relevant": exp.get("is_relevant", False),
            "relevant_topics": exp.get("relevant_topics", []),
            "irrelevance_reason": exp.get("irrelevance_reason"),
            "confidence": 0.8,
        }
    if ct == "fit_scoring":
        lo, hi = exp.get("fit_score_range", [0.5, 0.5])
        return {"fit_score": (lo + hi) / 2}
    if ct == "application_safety":
        return {
            "is_safe_to_apply": exp.get("is_safe_to_apply", False),
            "rejection_reason": exp.get("rejection_reason"),
        }
    if ct == "deduplication":
        return {"duplicate_groups": exp.get("duplicate_groups", [])}
    return {}


if __name__ == "__main__":
    report = evaluate_job_discovery()
    print(f"n_cases={report.n_cases}  pass_rate={report.pass_rate:.2f}")
    for metric, score in report.by_metric.items():
        print(f"  {metric}: {score:.2f}")
