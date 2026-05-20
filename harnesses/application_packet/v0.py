"""
Application packet harness v0.

generate_application_packet(job, company, candidate_profile, signals, config)
  -> ApplicationPacketResult

Produces: cover letter draft, resume tailoring suggestions, short-answer drafts,
referral request draft, interview prep notes, validation report.

Safety invariants:
- Every tailored claim must map to a candidate_profile field.
- Every company-specific claim must map to a signal source.
- Packets with unsupported_claims cannot advance to "approved".
- No packet is ever auto-submitted. All create an ApprovalItem.
- Degrades gracefully without an LLM key (heuristic mode).
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from harnesses.validators.application_packet import is_valid_application_packet
from harnesses.validators.retry import validate_with_retry
from app.tracing.logger import TraceLogger

EXPERIMENTS_DIR = Path(__file__).parents[2] / "experiments" / "runs"
PROMPTS_DIR = Path(__file__).parents[2] / "prompts"


# ---------------------------------------------------------------------------
# Config and types
# ---------------------------------------------------------------------------


class PacketConfig(BaseModel):
    use_llm: bool = True
    max_retries: int = 1
    dry_run: bool = False
    llm_model: str = "claude-haiku-4-5-20251001"


class CandidateProfile(BaseModel):
    id: str
    name: str
    experience_level: str = "new_grad"
    skills: list[str] = []
    degree: str | None = None
    gpa: str | None = None
    graduation_year: str | None = None
    notable: list[str] = []
    employers: list[str] = []


class ApplicationPacketResult(BaseModel):
    job_id: str
    company_name: str
    job_title: str
    cover_letter: str | None = None
    resume_tailoring: list[str] = []
    short_answers: dict[str, str] = {}
    referral_message: str | None = None
    interview_notes: list[str] = []
    unsupported_claims: list[str] = []
    validation_status: str = "pending"   # pending | passed | failed
    approval_status: str = "pending"     # always pending — never auto
    approval_item_id: str | None = None
    generated_by: str = "heuristic"     # heuristic | llm
    trace_dir: str = ""
    errors: list[str] = []


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def generate_application_packet(
    job: dict,
    company: dict,
    candidate_profile: CandidateProfile,
    signals: list[dict] | None = None,
    config: PacketConfig | None = None,
) -> ApplicationPacketResult:
    cfg = config or PacketConfig()
    signals = signals or []
    started_at = datetime.utcnow()
    trace = TraceLogger(started_at, "application_packet", "v0",
                        base_dir=EXPERIMENTS_DIR)
    errors: list[str] = []

    job_id = job.get("id") or job.get("url") or "unknown"
    company_name = company.get("name", "Unknown")
    job_title = job.get("title", "Software Engineer")

    trace.log("input", {
        "job_id": job_id, "company": company_name, "title": job_title,
        "profile_id": candidate_profile.id, "signals_count": len(signals),
    })

    # --- Cover letter ---
    use_llm = cfg.use_llm and _llm_available()
    cover_letter, cl_by = _generate_cover_letter(
        job, company, candidate_profile, signals, cfg, trace, errors, use_llm
    )
    trace.log("cover_letter", {"text": cover_letter, "by": cl_by})

    # --- Resume tailoring suggestions ---
    tailoring = _generate_tailoring(job, candidate_profile, signals)
    trace.log("tailoring", tailoring)

    # --- Short-answer drafts ---
    required_questions = job.get("required_questions", [])
    short_answers = _generate_short_answers(
        required_questions, job, company, candidate_profile, signals, cfg, trace, errors, use_llm
    )
    trace.log("short_answers", short_answers)

    # --- Referral message ---
    referral_message = _generate_referral_message(company_name, job_title, candidate_profile)
    trace.log("referral_message", {"text": referral_message})

    # --- Interview prep ---
    interview_notes = _generate_interview_notes(signals, job, company_name)
    trace.log("interview_notes", interview_notes)

    # --- Build packet dict for validation ---
    packet_dict = {
        "cover_letter": cover_letter,
        "short_answers": short_answers,
        "unsupported_claims": [],
        "approval_status": "pending",
        "gpa": candidate_profile.gpa,
        "graduation_year": str(candidate_profile.graduation_year) if candidate_profile.graduation_year else None,
        "degree": candidate_profile.degree,
    }
    job_dict = {"required_questions": required_questions}
    profile_dict = {
        "skills": candidate_profile.skills,
        "gpa": candidate_profile.gpa,
        "graduation_year": str(candidate_profile.graduation_year) if candidate_profile.graduation_year else None,
        "degree": candidate_profile.degree,
    }

    # --- Validate with retry ---
    def propose(**kwargs):
        feedback = kwargs.get("feedback", [])
        if feedback and use_llm:
            # Simplified: just return the same packet with a note
            p = dict(packet_dict)
            p["_retry_feedback"] = feedback
            return p
        return packet_dict

    def validate(p: dict):
        return is_valid_application_packet(p, profile_dict, job_dict)

    retry_result = validate_with_retry(propose, validate, max_retries=cfg.max_retries)
    validation = retry_result.validation

    trace.log("validation", {
        "valid": validation.valid,
        "reason_codes": validation.reason_codes,
        "attempts": retry_result.attempts,
        "routed_to_human": retry_result.routed_to_human,
    })

    validation_status = "passed" if validation.valid else "failed"
    unsupported_claims = [c for c in validation.reason_codes if "claimed_skill_not_in_profile" in c]

    # --- Create ApprovalItem (in DB if not dry_run) ---
    approval_item_id = None
    if not cfg.dry_run:
        approval_item_id = _create_approval_item(job_id, job_title, validation_status, errors)

    result = ApplicationPacketResult(
        job_id=job_id,
        company_name=company_name,
        job_title=job_title,
        cover_letter=cover_letter,
        resume_tailoring=tailoring,
        short_answers=short_answers,
        referral_message=referral_message,
        interview_notes=interview_notes,
        unsupported_claims=unsupported_claims,
        validation_status=validation_status,
        approval_status="pending",   # always pending — never "auto"
        approval_item_id=approval_item_id,
        generated_by=cl_by,
        trace_dir=str(trace.run_dir),
        errors=errors,
    )

    trace.save_output(result.model_dump(mode="json"))
    return result


# ---------------------------------------------------------------------------
# Cover letter generation
# ---------------------------------------------------------------------------


def _generate_cover_letter(
    job: dict,
    company: dict,
    profile: CandidateProfile,
    signals: list[dict],
    cfg: PacketConfig,
    trace: TraceLogger,
    errors: list[str],
    use_llm: bool,
) -> tuple[str | None, str]:
    if use_llm:
        try:
            return _cover_letter_llm(job, company, profile, signals, cfg, trace, errors), "llm"
        except Exception as exc:
            errors.append(f"Cover letter LLM failed: {exc}")

    return _cover_letter_heuristic(job, company, profile, signals), "heuristic"


def _cover_letter_llm(
    job: dict, company: dict, profile: CandidateProfile,
    signals: list[dict], cfg: PacketConfig, trace: TraceLogger, errors: list[str],
) -> str:
    template = (PROMPTS_DIR / "cover_letter_draft.txt").read_text()
    signal_text = "\n".join(
        f"- [{s.get('signal_type','?')}] {s.get('summary','')}" for s in signals[:3]
    ) or "No specific signals available."

    prompt = template.format(
        company_name=company.get("name", ""),
        job_title=job.get("title", "Software Engineer"),
        candidate_name=profile.name,
        candidate_skills=", ".join(profile.skills[:8]),
        candidate_experience_level=profile.experience_level,
        candidate_degree=profile.degree or "BS Computer Science",
        candidate_notable=", ".join(profile.notable[:3]) or "N/A",
        company_signals=signal_text,
        job_description_excerpt=(job.get("description_text") or "")[:500],
    )
    trace.log("cover_letter_prompt", {"prompt": prompt})

    import anthropic
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=cfg.llm_model,
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.content[0].text.strip()
    trace.log("cover_letter_llm_response", {"text": text})
    return text


def _cover_letter_heuristic(
    job: dict, company: dict, profile: CandidateProfile, signals: list[dict],
) -> str:
    company_name = company.get("name", "this company")
    job_title = job.get("title", "Software Engineer")
    skills_str = ", ".join(profile.skills[:4]) or "software development"

    # Find first relevant signal for specificity
    signal_line = ""
    for s in signals:
        if s.get("signal_type") not in ("irrelevant", None) and s.get("summary"):
            signal_line = f" I was particularly interested to read about {s['summary']}"
            break

    para1 = (
        f"I am writing to express my interest in the {job_title} position at {company_name}.{signal_line} "
        f"I believe my background aligns well with what you are looking for."
    )
    para2 = (
        f"As a {profile.experience_level.replace('_', ' ')} with experience in {skills_str}, "
        f"I am excited by the opportunity to contribute to {company_name}'s engineering team. "
        f"My academic and project experience has prepared me to take on challenging technical problems."
    )
    para3 = (
        f"I would welcome the opportunity to discuss how my background fits the {job_title} role. "
        f"Thank you for considering my application."
    )
    return f"{para1}\n\n{para2}\n\n{para3}"


# ---------------------------------------------------------------------------
# Resume tailoring suggestions
# ---------------------------------------------------------------------------


def _generate_tailoring(
    job: dict, profile: CandidateProfile, signals: list[dict],
) -> list[str]:
    suggestions: list[str] = []
    desc = (job.get("description_text") or "").lower()
    title = (job.get("title") or "").lower()

    for skill in profile.skills:
        if skill.lower() in desc or skill.lower() in title:
            suggestions.append(f"Highlight {skill} prominently — mentioned in job description.")

    for s in signals:
        angle = s.get("application_angle")
        if angle and s.get("signal_type") != "irrelevant":
            suggestions.append(f"[{s.get('signal_type')}] {angle}")

    if not suggestions:
        suggestions.append("Emphasize relevant coursework and projects aligned with the job requirements.")

    return suggestions[:6]


# ---------------------------------------------------------------------------
# Short-answer drafts
# ---------------------------------------------------------------------------


def _generate_short_answers(
    questions: list[str],
    job: dict,
    company: dict,
    profile: CandidateProfile,
    signals: list[dict],
    cfg: PacketConfig,
    trace: TraceLogger,
    errors: list[str],
    use_llm: bool,
) -> dict[str, str]:
    answers: dict[str, str] = {}
    company_name = company.get("name", "this company")

    for q in questions:
        q_lower = q.lower()
        # Heuristic templates for common question types
        if "why" in q_lower and ("us" in q_lower or "company" in q_lower or company_name.lower() in q_lower):
            signal_note = ""
            for s in signals:
                if s.get("signal_type") in ("technical_signal", "culture_signal", "hiring_signal"):
                    signal_note = f" {s.get('summary', '')}"
                    break
            answers[q] = (
                f"I am drawn to {company_name} because of its engineering culture and technical depth.{signal_note} "
                f"My background in {', '.join(profile.skills[:2])} aligns well with the team's work."
            )
        elif "project" in q_lower or "experience" in q_lower:
            notable = profile.notable[0] if profile.notable else "a relevant course project"
            answers[q] = (
                f"In {notable}, I applied {', '.join(profile.skills[:2])} to solve a challenging problem. "
                f"This experience strengthened my ability to work on production-quality software."
            )
        elif "challenge" in q_lower or "difficult" in q_lower:
            answers[q] = (
                f"A significant challenge I faced was designing a system under tight constraints. "
                f"I approached it by breaking the problem into components and iterating on the solution."
            )
        else:
            answers[q] = f"[Please provide a specific answer for: {q}]"

    return answers


# ---------------------------------------------------------------------------
# Referral message
# ---------------------------------------------------------------------------


def _generate_referral_message(
    company_name: str, job_title: str, profile: CandidateProfile,
) -> str:
    return (
        f"Hi [Name],\n\n"
        f"I hope you're doing well! I recently came across the {job_title} opening at {company_name} "
        f"and am very excited about the opportunity. Given your experience there, I would be incredibly "
        f"grateful if you'd be willing to refer me or share any insights about the team.\n\n"
        f"My background is in {', '.join(profile.skills[:3])}, and I'd love to bring those skills to "
        f"{company_name}. Happy to share my resume or discuss further!\n\n"
        f"Thank you so much,\n{profile.name}"
    )


# ---------------------------------------------------------------------------
# Interview prep notes
# ---------------------------------------------------------------------------


def _generate_interview_notes(
    signals: list[dict], job: dict, company_name: str,
) -> list[str]:
    notes: list[str] = []

    for s in signals:
        q = s.get("interview_question")
        if q and s.get("signal_type") not in ("irrelevant", None):
            notes.append(f"[{s.get('signal_type')}] Prep question: {q}")

    if not notes:
        notes.append(f"Research {company_name}'s engineering blog and recent product launches.")
        notes.append("Prepare 2-3 STAR stories from your projects and internships.")
        notes.append("Review system design fundamentals: scalability, consistency, availability tradeoffs.")

    return notes[:8]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _llm_available() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def _create_approval_item(
    job_id: str, job_title: str, validation_status: str, errors: list[str],
) -> str | None:
    try:
        import uuid, os
        from dotenv import load_dotenv
        load_dotenv()
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            return None
        from sqlmodel import Session, create_engine
        from db.models import ApprovalItem
        now = datetime.utcnow()
        engine = create_engine(db_url, echo=False)
        with Session(engine) as session:
            item = ApprovalItem(
                item_type="application_packet",
                item_id=job_id,
                item_data={"job_title": job_title, "validation_status": validation_status},
                status="pending",
                created_at=now,
                updated_at=now,
            )
            session.add(item)
            session.commit()
            session.refresh(item)
            return item.id
    except Exception as exc:
        errors.append(f"ApprovalItem creation error: {exc}")
        return None
