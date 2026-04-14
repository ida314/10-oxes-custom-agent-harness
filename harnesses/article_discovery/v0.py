"""
Article/company-intelligence scoring harness v0.

score_articles(company, articles, candidate_profile, config) -> ArticleDiscoveryReport

For each article:
1. Fetch full text (if URL available)
2. Classify signal type via LLM
3. Validate output (pure Python)
4. Retry once on validation failure
5. Save full trace

Degrades gracefully: if no LLM key is set, uses heuristic keyword classifier.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from harnesses.validators.article_signal import is_valid_article_signal

EXPERIMENTS_DIR = Path(__file__).parents[2] / "experiments" / "runs"
PROMPTS_DIR = Path(__file__).parents[2] / "prompts"

SIGNAL_TYPES = [
    "hiring_signal", "technical_signal", "culture_signal", "strategy_signal",
    "interview_prep_signal", "networking_signal", "risk_signal", "irrelevant",
]

# Keyword heuristics used when no LLM is available
_HEURISTIC_KEYWORDS: dict[str, list[str]] = {
    "hiring_signal": ["hiring", "open roles", "new grad", "cohort", "university hire",
                      "recruiting", "headcount", "apply now", "applications open"],
    "technical_signal": ["architecture", "tech stack", "go ", "python", "rust",
                         "distributed", "scalab", "observability", "microservice",
                         "infrastructure", "latency", "throughput", "open source"],
    "culture_signal": ["onboarding", "culture", "values", "team", "blameless",
                       "ownership", "autonomy", "remote", "hybrid", "work-life"],
    "interview_prep_signal": ["interview", "hiring process", "what we look for",
                              "evaluation", "assessment", "coding challenge", "puzzle"],
    "networking_signal": ["engineer at", "team lead", "our team", "meet the team",
                          "author:", "written by"],
    "strategy_signal": ["product direction", "roadmap", "bet on", "investing in",
                        "partnership", "acquisition", "launch", "series"],
    "risk_signal": ["layoff", "laid off", "restructur", "hiring freeze",
                    "cost cutting", "revenue miss", "down round"],
}


# ---------------------------------------------------------------------------
# Config and output types
# ---------------------------------------------------------------------------


class ArticleDiscoveryConfig(BaseModel):
    max_articles: int = 10
    use_llm: bool = True          # set False to force heuristic mode
    max_retries: int = 1
    dry_run: bool = False
    llm_model: str = "claude-haiku-4-5-20251001"  # cheapest capable model


class CandidateProfile(BaseModel):
    id: str
    name: str
    experience_level: str = "new_grad"
    skills: list[str] = []


class ArticleSignal(BaseModel):
    article_title: str | None
    article_url: str | None
    article_source: str | None
    signal_type: str
    summary: str
    why_it_matters: str | None = None
    application_angle: str | None = None
    outreach_angle: str | None = None
    interview_question: str | None = None
    confidence: float
    source_evidence: str | None = None
    is_valid: bool
    validation_codes: list[str] = []
    classified_by: str  # "llm" | "heuristic"


class ArticleDiscoveryReport(BaseModel):
    company_name: str
    profile_id: str
    harness_version: str = "v0"
    started_at: datetime
    finished_at: datetime
    articles_processed: int
    signals: list[ArticleSignal]
    errors: list[str]
    trace_dir: str


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def score_articles(
    company: dict,
    articles: list[dict],
    candidate_profile: CandidateProfile,
    config: ArticleDiscoveryConfig | None = None,
) -> ArticleDiscoveryReport:
    cfg = config or ArticleDiscoveryConfig()
    started_at = datetime.utcnow()
    trace = _TraceLogger(started_at, "article_discovery", "v0")
    errors: list[str] = []

    company_name = company.get("name", "Unknown")
    articles = articles[: cfg.max_articles]

    trace.log("config", {
        "company": company_name,
        "articles_count": len(articles),
        "use_llm": cfg.use_llm,
        "profile_id": candidate_profile.id,
    })

    signals: list[ArticleSignal] = []

    for i, article in enumerate(articles):
        title = article.get("title") or ""
        url = article.get("url") or ""
        source = article.get("source_url") or article.get("published") or ""
        text = article.get("full_text") or article.get("descriptionPlain") or title

        trace.log(f"article_{i:02d}_input", {
            "title": title, "url": url, "source": source, "text_len": len(text)
        })

        # Choose classifier
        if cfg.use_llm and _llm_available():
            signal_dict, classified_by = _classify_with_llm(
                article=article,
                company_name=company_name,
                candidate_profile=candidate_profile,
                config=cfg,
                trace=trace,
                idx=i,
                errors=errors,
            )
        else:
            signal_dict, classified_by = _classify_heuristic(article, company_name)

        trace.log(f"article_{i:02d}_raw_classification", signal_dict)

        # Validate
        val = is_valid_article_signal(signal_dict, text)

        # Retry once on validation failure (with LLM)
        if not val.valid and cfg.use_llm and _llm_available() and cfg.max_retries > 0:
            signal_dict, classified_by = _classify_with_llm(
                article=article,
                company_name=company_name,
                candidate_profile=candidate_profile,
                config=cfg,
                trace=trace,
                idx=i,
                errors=errors,
                retry_with_feedback=val.reason_codes,
            )
            val = is_valid_article_signal(signal_dict, text)
            trace.log(f"article_{i:02d}_retry_result", {
                "valid": val.valid, "codes": val.reason_codes
            })

        if not val.valid:
            errors.append(
                f"Article '{title}' failed validation: {val.reason_codes}"
            )

        signal = ArticleSignal(
            article_title=title or None,
            article_url=url or None,
            article_source=source or None,
            signal_type=signal_dict.get("signal_type", "irrelevant"),
            summary=signal_dict.get("summary", ""),
            why_it_matters=signal_dict.get("why_it_matters"),
            application_angle=signal_dict.get("application_angle"),
            outreach_angle=signal_dict.get("outreach_angle"),
            interview_question=signal_dict.get("interview_question"),
            confidence=float(signal_dict.get("confidence", 0.0)),
            source_evidence=signal_dict.get("source_evidence"),
            is_valid=val.valid,
            validation_codes=val.reason_codes,
            classified_by=classified_by,
        )
        signals.append(signal)
        trace.log(f"article_{i:02d}_signal", signal.model_dump())

    # Sort: most actionable first (non-irrelevant, high confidence)
    signals.sort(
        key=lambda s: (s.signal_type != "irrelevant", s.confidence),
        reverse=True,
    )

    finished_at = datetime.utcnow()
    report = ArticleDiscoveryReport(
        company_name=company_name,
        profile_id=candidate_profile.id,
        started_at=started_at,
        finished_at=finished_at,
        articles_processed=len(articles),
        signals=signals,
        errors=errors,
        trace_dir=str(trace.run_dir),
    )
    trace.save_output(report.model_dump(mode="json"))
    return report


# ---------------------------------------------------------------------------
# LLM classifier
# ---------------------------------------------------------------------------


def _llm_available() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def _classify_with_llm(
    article: dict,
    company_name: str,
    candidate_profile: CandidateProfile,
    config: ArticleDiscoveryConfig,
    trace: "_TraceLogger",
    idx: int,
    errors: list[str],
    retry_with_feedback: list[str] | None = None,
) -> tuple[dict, str]:
    prompt_template = (PROMPTS_DIR / "article_signal_classify.txt").read_text()
    title = article.get("title") or ""
    text = article.get("full_text") or article.get("descriptionPlain") or title
    prompt = prompt_template.format(
        company_name=company_name,
        candidate_level=candidate_profile.experience_level,
        candidate_skills=", ".join(candidate_profile.skills),
        article_title=title,
        article_source=article.get("source_url") or "",
        article_date=article.get("published") or "unknown",
        article_text=text[:3000],  # cap context
    )

    if retry_with_feedback:
        prompt += f"\n\nPrevious attempt failed validation: {retry_with_feedback}. Fix those issues."

    trace.log(f"article_{idx:02d}_prompt", {"prompt": prompt})

    try:
        import anthropic
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=config.llm_model,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        raw_text = response.content[0].text.strip()
        trace.log(f"article_{idx:02d}_llm_response", {"text": raw_text})
        signal_dict = _parse_json_response(raw_text)
        return signal_dict, "llm"
    except Exception as exc:
        errors.append(f"LLM call failed for article {idx}: {exc}")
        # Fall back to heuristic
        result, _ = _classify_heuristic(article, company_name)
        return result, "heuristic_fallback"


def _parse_json_response(text: str) -> dict:
    # Strip markdown fences if present
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE)
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        # Try to extract JSON object
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group(0))
        return {"signal_type": "irrelevant", "confidence": 0.0, "summary": "parse error"}


# ---------------------------------------------------------------------------
# Heuristic classifier (no LLM)
# ---------------------------------------------------------------------------


def _classify_heuristic(article: dict, company_name: str) -> tuple[dict, str]:
    title = (article.get("title") or "").lower()
    text = (article.get("full_text") or article.get("descriptionPlain") or title).lower()
    combined = title + " " + text

    best_type = "irrelevant"
    best_score = 0

    for signal_type, keywords in _HEURISTIC_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in combined)
        if score > best_score:
            best_score = score
            best_type = signal_type

    confidence = min(0.9, best_score * 0.2) if best_score > 0 else 0.1

    summary = f"Article about {company_name}"
    if article.get("title"):
        summary = article["title"]

    result: dict[str, Any] = {
        "signal_type": best_type,
        "summary": summary,
        "confidence": confidence,
        "why_it_matters": None,
        "application_angle": None,
        "outreach_angle": None,
        "interview_question": None,
        "source_evidence": None,
    }

    if best_type != "irrelevant":
        result["why_it_matters"] = f"This article provides {best_type.replace('_', ' ')} about {company_name}."
        result["application_angle"] = f"Reference insights from this article when applying to {company_name}."
        result["interview_question"] = f"What do you know about {company_name}'s recent engineering work?"

    return result, "heuristic"


# ---------------------------------------------------------------------------
# Trace logger (shared pattern with job discovery harness)
# ---------------------------------------------------------------------------


class _TraceLogger:
    def __init__(self, started_at: datetime, harness: str, version: str):
        ts = started_at.strftime("%Y-%m-%dT%H-%M-%S")
        self.run_dir = EXPERIMENTS_DIR / f"{ts}_{harness}_{version}"
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self._seq = 0

    def log(self, name: str, data: Any) -> None:
        fname = f"{self._seq:03d}_{name}.json"
        (self.run_dir / fname).write_text(json.dumps(data, indent=2, default=str))
        self._seq += 1

    def save_output(self, report: dict) -> None:
        (self.run_dir / "output.json").write_text(
            json.dumps(report, indent=2, default=str)
        )
