"""
Job-discovery harness v0.

run_company_scan(company_id, profile_id, config) -> CompanyScanReport

Phase 3 scope:
- ATS-first ingestion (Greenhouse → Lever → Ashby → careers-page fallback)
- Deduplication by normalized_hash
- Heuristic entry-level scoring (no LLM)
- Article and event discovery
- Stub recommendations (ranked by entry_level_score + fit heuristic)
- Stub validators (full validators built in Phase 7)
- Full trace logging to experiments/runs/{timestamp}/
- Writes jobs/articles/events to Postgres (when DB available)

No LLM calls in v0. The harness is deterministic and fully traceable.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from skills.base import NormalizedJob, RunContext, SkillResult
from skills.ats.greenhouse.skill import QueryGreenhouseJobs, GreenhouseInput
from skills.ats.lever.skill import QueryLeverJobs, LeverInput
from skills.ats.ashby.skill import QueryAshbyJobs, AshbyInput
from skills.company_research.find_careers_page.skill import FindCareersPage, FindCareersPageInput
from skills.company_research.find_recent_articles.skill import FindRecentArticles, FindRecentArticlesInput
from skills.company_research.find_events.skill import FindEvents, FindEventsInput
from harnesses.validators.job import is_valid_job, is_safe_to_apply, entry_level_score

EXPERIMENTS_DIR = Path(__file__).parents[2] / "experiments" / "runs"


# ---------------------------------------------------------------------------
# Config and output types
# ---------------------------------------------------------------------------


class HarnessConfig(BaseModel):
    staleness_threshold_days: int = 90
    ats_confidence_threshold: float = 0.3
    max_articles: int = 10
    dry_run: bool = False  # if True, skip DB writes


class CandidateProfile(BaseModel):
    id: str
    name: str
    experience_level: str = "new_grad"  # new_grad | intern | junior
    skills: list[str] = []
    graduation_year: int | None = None
    degree: str | None = None
    gpa: float | None = None
    preferred_locations: list[str] = []
    notes: str | None = None


class ScoredJob(BaseModel):
    job: NormalizedJob
    entry_level_score: float
    fit_score: float
    is_valid: bool
    is_safe: bool
    validation_codes: list[str]
    recommendation: str  # apply | research | skip


class CompanyScanReport(BaseModel):
    company_id: str
    company_name: str
    company_domain: str
    profile_id: str
    harness_version: str = "v0"
    started_at: datetime
    finished_at: datetime
    jobs_discovered: int
    jobs_after_dedup: int
    jobs_valid: int
    scored_jobs: list[ScoredJob]
    articles: list[dict]
    events: list[dict]
    errors: list[str]
    trace_dir: str


# ---------------------------------------------------------------------------
# Harness entry point
# ---------------------------------------------------------------------------


def run_company_scan(
    company_id: str,
    profile_id: str,
    config: HarnessConfig | None = None,
    profile: CandidateProfile | None = None,
    company_override: dict | None = None,
) -> CompanyScanReport:
    """
    Main entry point. company_override allows passing company data without a DB.
    If company_override is None, tries to load from DB.
    """
    cfg = config or HarnessConfig()
    started_at = datetime.utcnow()
    trace = TraceLogger(started_at, "job_discovery", "v0")
    errors: list[str] = []

    # --- Load company ---
    if company_override:
        company = company_override
    else:
        company = _load_company_from_db(company_id, errors)
        if not company:
            finished_at = datetime.utcnow()
            return CompanyScanReport(
                company_id=company_id,
                company_name="unknown",
                company_domain="unknown",
                profile_id=profile_id,
                started_at=started_at,
                finished_at=finished_at,
                jobs_discovered=0,
                jobs_after_dedup=0,
                jobs_valid=0,
                scored_jobs=[],
                articles=[],
                events=[],
                errors=errors,
                trace_dir=str(trace.run_dir),
            )

    trace.log("config", {"company": company, "profile_id": profile_id, "cfg": cfg.model_dump()})

    ctx = RunContext(dry_run=cfg.dry_run, timeout_seconds=20)

    # --- Step 1: ATS connectors ---
    all_jobs: list[NormalizedJob] = []
    ats_type = company.get("ats_type", "unknown")
    domain = company.get("domain", "")
    name = company.get("name", "")

    ats_result = _run_ats(name, domain, ats_type, ctx, trace, errors)
    all_jobs.extend(ats_result.items)
    trace.log("ats_result", {"ats_type": ats_type, "jobs_count": len(ats_result.items), "errors": ats_result.errors})

    # --- Step 2: Fallback to careers page if ATS confidence is low ---
    if ats_result.confidence < cfg.ats_confidence_threshold:
        fp_result = _run_skill(
            "find_careers_page",
            FindCareersPage(),
            FindCareersPageInput(company_name=name, domain=domain),
            ctx,
            trace,
            errors,
        )
        trace.log("careers_page_fallback", {"urls_found": len(fp_result.items)})

    # --- Step 3: Deduplicate by normalized_hash ---
    seen_hashes: set[str] = set()
    unique_jobs: list[NormalizedJob] = []
    for job in all_jobs:
        if job.normalized_hash not in seen_hashes:
            seen_hashes.add(job.normalized_hash)
            unique_jobs.append(job)
    trace.log("dedup", {"before": len(all_jobs), "after": len(unique_jobs)})

    # --- Step 4: Validate and score jobs ---
    scored: list[ScoredJob] = []
    for job in unique_jobs:
        val = is_valid_job(job)
        safety = is_safe_to_apply(job, cfg.staleness_threshold_days)
        el_score = entry_level_score(job)
        fit = _heuristic_fit(job, profile)

        rec = "skip"
        if val.valid and safety.valid and el_score >= 0.7:
            rec = "apply" if fit >= 0.5 else "research"
        elif val.valid and el_score >= 0.4:
            rec = "research"

        scored.append(
            ScoredJob(
                job=job,
                entry_level_score=el_score,
                fit_score=fit,
                is_valid=val.valid,
                is_safe=safety.valid,
                validation_codes=val.reason_codes + safety.reason_codes,
                recommendation=rec,
            )
        )

    scored.sort(key=lambda s: (s.fit_score + s.entry_level_score), reverse=True)
    trace.log("scoring", {"total_scored": len(scored), "apply": sum(1 for s in scored if s.recommendation == "apply")})

    # --- Step 5: Articles ---
    articles: list[dict] = []
    careers_url = company.get("careers_url", f"https://{domain}/careers")
    blog_url = f"https://engineering.{domain}"
    art_result = _run_skill(
        "find_recent_articles",
        FindRecentArticles(),
        FindRecentArticlesInput(company_name=name, blog_url=blog_url, max_articles=cfg.max_articles),
        ctx,
        trace,
        errors,
    )
    articles = art_result.items  # list of dicts from RSS/HTML parse
    trace.log("articles", {"count": len(articles)})

    # --- Step 6: Events ---
    events: list[dict] = []
    ev_result = _run_skill(
        "find_events",
        FindEvents(),
        FindEventsInput(company_name=name, domain=domain),
        ctx,
        trace,
        errors,
    )
    events = ev_result.items
    trace.log("events", {"count": len(events)})

    # --- Step 7: Persist to DB ---
    if not cfg.dry_run:
        _save_to_db(company_id, scored, articles, events, errors)

    finished_at = datetime.utcnow()

    report = CompanyScanReport(
        company_id=company_id,
        company_name=name,
        company_domain=domain,
        profile_id=profile_id,
        started_at=started_at,
        finished_at=finished_at,
        jobs_discovered=len(all_jobs),
        jobs_after_dedup=len(unique_jobs),
        jobs_valid=sum(1 for s in scored if s.is_valid),
        scored_jobs=scored,
        articles=articles,
        events=events,
        errors=errors,
        trace_dir=str(trace.run_dir),
    )

    trace.save_output(report.model_dump(mode="json"))
    return report


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _run_ats(
    company_name: str,
    domain: str,
    ats_type: str,
    ctx: RunContext,
    trace: "TraceLogger",
    errors: list[str],
) -> SkillResult:
    slug = domain.split(".")[0]  # heuristic: "stripe.com" → "stripe"

    if ats_type == "greenhouse":
        return _run_skill("greenhouse", QueryGreenhouseJobs(),
                          GreenhouseInput(company_name=company_name, board_token=slug), ctx, trace, errors)
    if ats_type == "lever":
        return _run_skill("lever", QueryLeverJobs(),
                          LeverInput(company_name=company_name, board_slug=slug), ctx, trace, errors)
    if ats_type == "ashby":
        return _run_skill("ashby", QueryAshbyJobs(),
                          AshbyInput(company_name=company_name, board_slug=slug), ctx, trace, errors)

    # Unknown ATS: return empty with low confidence
    return SkillResult(success=True, items=[], confidence=0.0,
                       errors=[f"Unknown ATS type: {ats_type}"])


def _run_skill(name: str, skill: Any, input: Any, ctx: RunContext,
               trace: "TraceLogger", errors: list[str]) -> SkillResult:
    try:
        result = skill.run(input, ctx)
        trace.log(f"skill_{name}", {
            "success": result.success,
            "items_count": len(result.items),
            "errors": result.errors,
            "confidence": result.confidence,
        })
        if result.errors:
            errors.extend(result.errors)
        return result
    except Exception as exc:
        err = f"Skill {name} raised: {exc}"
        errors.append(err)
        trace.log(f"skill_{name}_exception", {"error": err})
        return SkillResult.failure(err)


def _heuristic_fit(job: NormalizedJob, profile: CandidateProfile | None) -> float:
    """Simple keyword-overlap fit score. Phase 3 stub; replace with LLM in Phase 4+."""
    if profile is None:
        return 0.5
    if not profile.skills:
        return 0.5

    desc_lower = (job.title + " " + job.description_text).lower()
    matches = sum(1 for skill in profile.skills if skill.lower() in desc_lower)
    return min(1.0, matches / max(len(profile.skills), 1))


def _load_company_from_db(company_id: str, errors: list[str]) -> dict | None:
    try:
        import os
        from dotenv import load_dotenv
        load_dotenv()
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            errors.append("DATABASE_URL not set; cannot load company from DB")
            return None

        from sqlmodel import Session, create_engine, select
        from db.models import Company

        engine = create_engine(db_url, echo=False)
        with Session(engine) as session:
            company = session.get(Company, company_id)
            if not company:
                errors.append(f"Company {company_id} not found in DB")
                return None
            return {
                "id": company.id,
                "name": company.name,
                "domain": company.domain,
                "ats_type": company.ats_type or "unknown",
                "careers_url": company.careers_url,
                "priority": company.priority,
            }
    except Exception as exc:
        errors.append(f"DB load error: {exc}")
        return None


def _save_to_db(
    company_id: str,
    scored: list[ScoredJob],
    articles: list[dict],
    events: list[dict],
    errors: list[str],
) -> None:
    try:
        import os
        from dotenv import load_dotenv
        load_dotenv()
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            return

        from sqlmodel import Session, create_engine, select
        from db.models import Job as DBJob, Article as DBArticle

        engine = create_engine(db_url, echo=False)
        now = datetime.utcnow()

        with Session(engine) as session:
            for s in scored:
                job = s.job
                existing = session.exec(
                    select(DBJob).where(DBJob.normalized_hash == job.normalized_hash)
                ).first()
                if existing:
                    continue

                db_job = DBJob(
                    company_id=company_id,
                    title=job.title,
                    url=job.url,
                    location=job.location,
                    description_text=job.description_text,
                    source_type=job.source_type,
                    source_url=job.source_url,
                    discovered_at=job.discovered_at,
                    posted_at=job.posted_at,
                    normalized_hash=job.normalized_hash,
                    entry_level_score=s.entry_level_score,
                    fit_score=s.fit_score,
                    status="new",
                    created_at=now,
                    updated_at=now,
                )
                session.add(db_job)
            session.commit()
    except Exception as exc:
        errors.append(f"DB save error: {exc}")


# ---------------------------------------------------------------------------
# Trace logger
# ---------------------------------------------------------------------------


class TraceLogger:
    def __init__(self, started_at: datetime, harness: str, version: str):
        ts = started_at.strftime("%Y-%m-%dT%H-%M-%S")
        self.run_dir = EXPERIMENTS_DIR / f"{ts}_{harness}_{version}"
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self._seq = 0

    def log(self, name: str, data: Any) -> None:
        fname = f"{self._seq:03d}_{name}.json"
        (self.run_dir / fname).write_text(
            json.dumps(data, indent=2, default=str)
        )
        self._seq += 1

    def save_output(self, report: dict) -> None:
        (self.run_dir / "output.json").write_text(
            json.dumps(report, indent=2, default=str)
        )
