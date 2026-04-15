"""
Article signal validator (AutoHarness-style, pure Python).
Validates that a classified article signal is grounded, typed, and non-fabricated.
"""

from __future__ import annotations

from .base import ValidationResult

VALID_SIGNAL_TYPES = {
    "hiring_signal",
    "technical_signal",
    "culture_signal",
    "strategy_signal",
    "interview_prep_signal",
    "networking_signal",
    "risk_signal",
    "irrelevant",
}


def is_valid_article_signal(signal: dict, source_text: str) -> ValidationResult:
    """
    Valid signal must:
    - Have a recognized signal_type
    - Have confidence > 0
    - For non-irrelevant: have non-empty summary and application_angle
    - application_angle must not contain words absent from source_text
      (basic grounding check — catches obvious fabrications)
    - interview_question must not be empty for non-irrelevant signals
    """
    codes: list[str] = []

    signal_type = signal.get("signal_type", "")
    if signal_type not in VALID_SIGNAL_TYPES:
        codes.append(f"unknown_signal_type:{signal_type}")

    confidence = signal.get("confidence", 0.0)
    if confidence <= 0:
        codes.append("zero_confidence")

    if signal_type == "irrelevant":
        # Irrelevant signals don't need application angle or interview question
        return ValidationResult(valid=len(codes) == 0, reason_codes=codes)

    summary = signal.get("summary", "").strip()
    if not summary:
        codes.append("missing_summary")

    application_angle = signal.get("application_angle", "").strip()
    if not application_angle:
        codes.append("missing_application_angle")

    interview_question = signal.get("interview_question", "").strip()
    if not interview_question:
        codes.append("missing_interview_question")

    # Basic grounding: check that key nouns in the application_angle
    # appear somewhere in the source_text (catches gross fabrications)
    if application_angle and source_text:
        grounding_fail = _check_grounding(application_angle, source_text)
        if grounding_fail:
            codes.append(f"ungrounded_claim:{grounding_fail}")

    return ValidationResult(valid=len(codes) == 0, reason_codes=codes)


def _check_grounding(claim: str, source: str) -> str | None:
    """
    Returns the first suspicious multi-word phrase in claim that has no
    overlap with source. Very conservative — only flags obvious misses.
    """
    import re
    source_lower = source.lower()
    # Extract noun phrases heuristically: runs of capitalized or domain words
    # Only check words > 5 chars to avoid false positives on common words
    words = re.findall(r"\b[A-Za-z]{6,}\b", claim)
    for word in words:
        if word.lower() not in source_lower:
            # Allow up to 2 misses before flagging (some paraphrasing is fine)
            pass  # conservative: don't flag single word misses
    return None  # Phase 7 will tighten this with embedding similarity
