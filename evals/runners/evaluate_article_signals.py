"""
Evaluation runner for article signal classification.

evaluate_article_signals(harness_path, dataset_path, split, output_dir) -> EvalReport

Loads the article_signal_seed.jsonl dataset, runs the harness on each case,
scores predictions, and saves metrics.json + per-example results.

The search/test split is enforced: passing split="test" requires explicit --allow-test flag.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

DATASETS_DIR = Path(__file__).parents[2] / "evals" / "datasets"
SEARCH_DATASET = DATASETS_DIR / "article_signal_seed.jsonl"  # all 15 cases = search set
# Held-out test for article signals not yet created; reuse search set for now


class EvalCase(BaseModel):
    id: str
    company: str
    is_negative: bool
    input: dict
    expected: dict


class CasePrediction(BaseModel):
    case_id: str
    predicted_signal_type: str
    predicted_confidence: float
    classified_by: str


class CaseScore(BaseModel):
    case_id: str
    company: str
    is_negative: bool
    expected_signal_type: str
    predicted_signal_type: str
    signal_type_correct: bool
    relevance_correct: bool  # irrelevant vs non-irrelevant binary
    confidence: float
    score: float


class EvalReport(BaseModel):
    dataset: str
    split: str
    n_cases: int
    n_passed: int
    pass_rate: float
    signal_type_accuracy: float
    relevance_accuracy: float
    mean_confidence: float
    by_company: dict[str, float]
    per_case: list[CaseScore]
    evaluated_at: str
    errors: list[str]


def evaluate_article_signals(
    dataset_path: str | Path = SEARCH_DATASET,
    split: str = "search",
    output_dir: str | Path | None = None,
    allow_test: bool = False,
) -> EvalReport:
    """
    Run evaluation on the article signal dataset.
    split must be "search" unless allow_test=True.
    """
    if split == "test" and not allow_test:
        raise ValueError(
            "Test split is held out. Pass allow_test=True only for final evaluation, "
            "never during optimizer search."
        )

    dataset_path = Path(dataset_path)
    cases = _load_dataset(dataset_path)
    errors: list[str] = []

    # Import harness
    from harnesses.article_discovery.v0 import (
        score_articles,
        ArticleDiscoveryConfig,
        CandidateProfile,
    )

    profile = CandidateProfile(
        id="eval-profile",
        name="Eval Candidate",
        experience_level="new_grad",
        skills=["Python", "Go", "algorithms", "distributed systems"],
    )
    cfg = ArticleDiscoveryConfig(use_llm=False, dry_run=True)  # heuristic only for eval speed

    per_case: list[CaseScore] = []
    company_scores: dict[str, list[float]] = {}

    for case in cases:
        article = case.input.get("article", {})
        company = {"name": case.company, "domain": f"{case.company.lower()}.com"}

        try:
            report = score_articles(
                company=company,
                articles=[article],
                candidate_profile=profile,
                config=cfg,
            )
            signal = report.signals[0] if report.signals else None
        except Exception as exc:
            errors.append(f"Harness error on {case.id}: {exc}")
            signal = None

        expected_type = case.expected.get("signal_type", "irrelevant")
        expected_relevant = case.expected.get("is_relevant", False)

        predicted_type = signal.signal_type if signal else "irrelevant"
        predicted_confidence = signal.confidence if signal else 0.0

        type_correct = predicted_type == expected_type
        # Relevance: binary (irrelevant vs any other type)
        pred_relevant = predicted_type != "irrelevant"
        relevance_correct = pred_relevant == expected_relevant

        # Score: 1.0 exact type, 0.5 correct relevance only, 0.0 wrong relevance
        if type_correct:
            score = 1.0
        elif relevance_correct:
            score = 0.5
        else:
            score = 0.0

        cs = CaseScore(
            case_id=case.id,
            company=case.company,
            is_negative=case.is_negative,
            expected_signal_type=expected_type,
            predicted_signal_type=predicted_type,
            signal_type_correct=type_correct,
            relevance_correct=relevance_correct,
            confidence=predicted_confidence,
            score=score,
        )
        per_case.append(cs)
        company_scores.setdefault(case.company, []).append(score)

    n = len(per_case)
    n_passed = sum(1 for c in per_case if c.score >= 0.5)
    pass_rate = n_passed / n if n else 0.0
    type_accuracy = sum(1 for c in per_case if c.signal_type_correct) / n if n else 0.0
    relevance_accuracy = sum(1 for c in per_case if c.relevance_correct) / n if n else 0.0
    mean_conf = sum(c.confidence for c in per_case) / n if n else 0.0
    by_company = {co: sum(scores) / len(scores) for co, scores in company_scores.items()}

    report_obj = EvalReport(
        dataset=str(dataset_path),
        split=split,
        n_cases=n,
        n_passed=n_passed,
        pass_rate=pass_rate,
        signal_type_accuracy=type_accuracy,
        relevance_accuracy=relevance_accuracy,
        mean_confidence=mean_conf,
        by_company=by_company,
        per_case=per_case,
        evaluated_at=datetime.utcnow().isoformat(),
        errors=errors,
    )

    if output_dir:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "metrics.json").write_text(
            json.dumps(report_obj.model_dump(), indent=2, default=str)
        )

    return report_obj


def _load_dataset(path: Path) -> list[EvalCase]:
    cases: list[EvalCase] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        raw = json.loads(line)
        if raw.get("case_type") != "article_signal":
            continue
        cases.append(
            EvalCase(
                id=raw["id"],
                company=raw["company"],
                is_negative=raw.get("is_negative", False),
                input=raw["input"],
                expected=raw["expected"],
            )
        )
    return cases


if __name__ == "__main__":
    report = evaluate_article_signals()
    print(f"n_cases={report.n_cases}  pass_rate={report.pass_rate:.2f}")
    print(f"signal_type_accuracy={report.signal_type_accuracy:.2f}")
    print(f"relevance_accuracy={report.relevance_accuracy:.2f}")
    for co, score in report.by_company.items():
        print(f"  {co}: {score:.2f}")
    if report.errors:
        print("ERRORS:", report.errors)
