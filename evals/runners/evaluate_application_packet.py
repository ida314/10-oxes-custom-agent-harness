"""Evaluation runner for application packet generation (Phase 6 scope, Phase 10 implementation)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

PASS_THRESHOLD = 0.75


class EvalReport(BaseModel):
    n_cases: int
    n_passed: int
    pass_rate: float
    by_metric: dict[str, float]
    errors: list[str]
    evaluated_at: str


def evaluate_application_packet(cases: list[dict] | None = None) -> EvalReport:
    """
    Evaluate application packet generation on provided test cases.
    If no cases provided, runs a minimal self-check using the validators.
    """
    from harnesses.application_packet.v0 import (
        generate_application_packet,
        PacketConfig,
        CandidateProfile,
    )

    if cases is None:
        cases = _default_cases()

    cfg = PacketConfig(use_llm=False, dry_run=True)
    errors: list[str] = []
    scores: dict[str, list[float]] = {"validation": [], "no_auto_submit": [], "no_fabrication": []}

    for case in cases:
        profile = CandidateProfile(**case["profile"])
        try:
            result = generate_application_packet(
                job=case["job"],
                company=case["company"],
                candidate_profile=profile,
                signals=case.get("signals", []),
                config=cfg,
            )
            # Metric 1: validation passed
            scores["validation"].append(1.0 if result.validation_status == "passed" else 0.0)
            # Metric 2: never auto-submitted
            scores["no_auto_submit"].append(1.0 if result.approval_status != "auto" else 0.0)
            # Metric 3: no fabricated skills detected
            fabricated = [c for c in result.unsupported_claims if "claimed_skill" in c]
            scores["no_fabrication"].append(1.0 if not fabricated else 0.0)
        except Exception as exc:
            errors.append(f"Error on case {case.get('id')}: {exc}")
            for k in scores:
                scores[k].append(0.0)

    n = len(cases)
    by_metric = {m: sum(s) / len(s) for m, s in scores.items() if s}
    overall = sum(sum(s) for s in scores.values()) / max(n * len(scores), 1)
    n_passed = sum(1 for i in range(n) if all(scores[m][i] >= PASS_THRESHOLD for m in scores))

    return EvalReport(
        n_cases=n,
        n_passed=n_passed,
        pass_rate=n_passed / n if n else 0.0,
        by_metric=by_metric,
        errors=errors,
        evaluated_at=datetime.utcnow().isoformat(),
    )


def _default_cases() -> list[dict]:
    return [
        {
            "id": "case_01_clean",
            "job": {
                "id": "job-001",
                "title": "Software Engineer, New Grad",
                "description_text": "Build Go and Python backend services.",
                "required_questions": ["why_us"],
            },
            "company": {"name": "Datadog", "domain": "datadoghq.com"},
            "profile": {
                "id": "p-001", "name": "Jane Doe",
                "skills": ["Python", "Go", "algorithms"], "experience_level": "new_grad",
                "degree": "BS Computer Science", "gpa": "3.8", "graduation_year": "2025",
                "notable": ["built a metrics dashboard"],
            },
            "signals": [
                {"signal_type": "technical_signal", "summary": "Datadog uses Go extensively.",
                 "application_angle": "Highlight Go projects.", "interview_question": "Describe your Go experience."}
            ],
        },
        {
            "id": "case_02_no_signals",
            "job": {
                "id": "job-002",
                "title": "Backend Engineer",
                "description_text": "Python and distributed systems.",
                "required_questions": [],
            },
            "company": {"name": "Stripe", "domain": "stripe.com"},
            "profile": {
                "id": "p-001", "name": "Jane Doe",
                "skills": ["Python", "distributed systems"], "experience_level": "new_grad",
                "degree": "BS Computer Science", "gpa": "3.7", "graduation_year": "2025",
                "notable": [],
            },
            "signals": [],
        },
    ]
