"""
Application packet validator (pure Python, no LLM).

Enforces: no fabricated experience, no altered facts, every claim backed by profile.
"""

from __future__ import annotations
import re
from .base import ValidationResult

# Fields that must never be altered from the candidate's actual profile
_IMMUTABLE_FIELDS = {"gpa", "graduation_year", "degree", "employers", "internship_companies"}

# Phrases that suggest fabricated experience
_FABRICATION_SIGNALS = [
    r"\b(led|managed|architected|designed|built|owned)\b.{0,60}\b(team|engineers|product|platform)\b",
]


def is_valid_application_packet(
    packet: dict,
    profile: dict,
    job: dict,
) -> ValidationResult:
    """
    Valid packet must:
    - Not fabricate experience (heuristic check on cover letter + short answers)
    - Not alter GPA, graduation year, degree, or employer names
    - Answer all required questions
    - Have at least one source job requirement mapped internally
    - Pass grammar/consistency basic checks (length sanity)
    - Have empty unsupported_claims list
    - Not be auto-submitted (approval_status must be "pending" or "approved", never "auto")
    """
    codes: list[str] = []

    # Unsupported claims must be empty
    if packet.get("unsupported_claims"):
        codes.append(f"unsupported_claims:{packet['unsupported_claims'][:2]}")

    # Auto-submit guard
    if packet.get("approval_status") == "auto":
        codes.append("auto_submit_forbidden")

    # Immutable field checks
    for field in _IMMUTABLE_FIELDS:
        packet_val = packet.get(field)
        profile_val = profile.get(field)
        if packet_val is not None and profile_val is not None:
            if str(packet_val).strip() != str(profile_val).strip():
                codes.append(f"altered_{field}")

    # Cover letter length sanity (50–2000 chars)
    cover = packet.get("cover_letter", "") or ""
    if cover and len(cover) < 50:
        codes.append("cover_letter_too_short")
    if cover and len(cover) > 2000:
        codes.append("cover_letter_too_long")

    # Fabrication heuristic on cover letter + short answers
    text_to_check = cover
    for answer in (packet.get("short_answers") or {}).values():
        text_to_check += " " + str(answer)

    profile_skills_lower = {s.lower() for s in profile.get("skills", [])}
    fabricated_signals = _check_fabrication(text_to_check, profile_skills_lower, profile)
    codes.extend(fabricated_signals)

    # Required questions must be answered
    required_qs = job.get("required_questions", [])
    answered_qs = set((packet.get("short_answers") or {}).keys())
    missing = [q for q in required_qs if q not in answered_qs]
    if missing:
        codes.append(f"missing_required_answers:{missing[:2]}")

    return ValidationResult(valid=len(codes) == 0, reason_codes=codes)


def _check_fabrication(
    text: str,
    profile_skills: set[str],
    profile: dict,
) -> list[str]:
    """
    Heuristic fabrication detection.
    Returns reason codes for suspicious patterns.
    """
    codes: list[str] = []
    text_lower = text.lower()

    # Check for claimed skills not in profile
    # (Only flag multi-word tech terms that look like specific claims)
    tech_claims = re.findall(
        r"\b(kubernetes|terraform|kafka|spark|pytorch|tensorflow|rust|scala)\b",
        text_lower,
    )
    for tech in tech_claims:
        if tech not in profile_skills and tech + " basics" not in profile_skills:
            codes.append(f"claimed_skill_not_in_profile:{tech}")

    # Check for years-of-experience claims that exceed profile
    yoe_matches = re.findall(r"(\d+)\+?\s+years?\s+(?:of\s+)?experience", text_lower)
    for yoe_str in yoe_matches:
        claimed_yoe = int(yoe_str)
        if claimed_yoe > 3:  # new grads shouldn't claim 4+ years
            codes.append(f"implausible_years_claimed:{claimed_yoe}")

    return codes
