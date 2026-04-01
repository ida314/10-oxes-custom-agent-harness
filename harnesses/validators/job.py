"""
Job and recommendation validators (AutoHarness-style).
Pure Python — no LLM calls. Returns ValidationResult.
"""

from __future__ import annotations

from skills.base import NormalizedJob
from .base import ValidationResult

SENIOR_TITLE_KEYWORDS = {
    "senior", "sr.", "sr ", "staff", "principal", "lead", "director",
    "manager", "head of", "vp ", "vice president", "chief",
}

ENTRY_LEVEL_TITLE_KEYWORDS = {
    "new grad", "university", "campus", "entry", "junior", "associate",
    "intern", "internship", "co-op", "coop", "early career",
}


def is_valid_job(job: NormalizedJob, max_years_required: int = 2) -> ValidationResult:
    """
    A valid job must:
    - Have a non-empty URL and title
    - Have a source_url (evidence of origin)
    - Not be flagged senior-only by title keyword
    """
    codes: list[str] = []

    if not job.url:
        codes.append("missing_url")
    if not job.title:
        codes.append("missing_title")
    if not job.normalized_hash:
        codes.append("missing_hash")

    title_lower = job.title.lower()
    if any(kw in title_lower for kw in SENIOR_TITLE_KEYWORDS) and not any(
        kw in title_lower for kw in ENTRY_LEVEL_TITLE_KEYWORDS
    ):
        codes.append("likely_senior_role")

    return ValidationResult(valid=len(codes) == 0, reason_codes=codes)


def is_safe_to_apply(job: NormalizedJob, staleness_threshold_days: int = 90) -> ValidationResult:
    """
    Safe to apply if:
    - Job was discovered recently (posted_at within threshold)
    - No senior-only flags
    """
    from datetime import datetime, timezone

    codes: list[str] = []

    if job.posted_at is not None:
        now = datetime.now(timezone.utc)
        posted = job.posted_at
        if posted.tzinfo is None:
            from datetime import timezone as tz
            posted = posted.replace(tzinfo=tz.utc)
        days_old = (now - posted).days
        if days_old > staleness_threshold_days:
            codes.append(f"stale_role_days_{days_old}")

    title_lower = job.title.lower()
    if any(kw in title_lower for kw in SENIOR_TITLE_KEYWORDS) and not any(
        kw in title_lower for kw in ENTRY_LEVEL_TITLE_KEYWORDS
    ):
        codes.append("senior_role")

    return ValidationResult(valid=len(codes) == 0, reason_codes=codes)


def entry_level_score(job: NormalizedJob) -> float:
    """
    Heuristic score 0.0–1.0 for how likely this is an entry-level role.
    Uses title keywords only (no LLM). Harness may refine with description text.
    """
    title_lower = job.title.lower()

    if any(kw in title_lower for kw in ENTRY_LEVEL_TITLE_KEYWORDS):
        return 0.9

    if any(kw in title_lower for kw in SENIOR_TITLE_KEYWORDS):
        return 0.05

    # Unlabeled title — assume moderate probability
    return 0.5
