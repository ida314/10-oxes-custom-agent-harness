"""
Recommendation validators (pure Python, no LLM).

propose_recommendation() → is_valid_recommendation() → route or act
"""

from __future__ import annotations
from .base import ValidationResult


def is_valid_recommendation(rec: dict, profile: dict) -> ValidationResult:
    """
    Valid recommendations must:
    - Cite at least one source URL
    - Not recommend applying to senior-only roles (entry_level_score < 0.3)
    - Not claim skills absent from candidate profile
    - Not recommend external outreach without approval
    - Not duplicate an existing application
    """
    codes: list[str] = []

    sources = rec.get("sources", [])
    if not sources:
        codes.append("missing_source_citation")

    action = rec.get("action", "")
    el_score = rec.get("entry_level_score", 1.0)
    if action == "apply" and el_score < 0.3:
        codes.append("senior_only_role")

    claimed_skills = rec.get("claimed_skills", [])
    profile_skills_lower = {s.lower() for s in profile.get("skills", [])}
    fabricated = [s for s in claimed_skills if s.lower() not in profile_skills_lower]
    if fabricated:
        codes.append(f"skills_not_in_profile:{','.join(fabricated[:3])}")

    if action in ("outreach", "referral_request"):
        if rec.get("approval_status") != "approved":
            codes.append("external_action_without_approval")

    if rec.get("duplicate_application"):
        codes.append("duplicate_application")

    return ValidationResult(valid=len(codes) == 0, reason_codes=codes)


def is_safe_application_recommendation(rec: dict) -> ValidationResult:
    """
    Safe application recommendations must:
    - Have at least one source
    - Have source_count > 0
    - Not contain unsupported claims
    - Have referral_check_completed if action == apply
    """
    codes: list[str] = []

    if rec.get("source_count", 0) == 0:
        codes.append("no_sources")

    if rec.get("unsupported_claims"):
        codes.append("contains_unsupported_claims")

    if rec.get("action") == "apply" and not rec.get("referral_check_completed", True):
        codes.append("referral_check_incomplete")

    return ValidationResult(valid=len(codes) == 0, reason_codes=codes)
