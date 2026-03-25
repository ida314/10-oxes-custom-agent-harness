"""
Greenhouse ATS connector.

Fetches all open jobs from the Greenhouse Job Board API (public endpoint).
Returns NormalizedJob instances in SkillResult.items.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from skills.base import Evidence, NormalizedJob, RunContext, SkillResult

# Injected at test time to avoid live network calls
_http_get_fn = None


def _http_get(url: str, timeout: int = 30) -> dict:
    if _http_get_fn is not None:
        return _http_get_fn(url)
    import httpx
    resp = httpx.get(url, timeout=timeout, follow_redirects=True)
    resp.raise_for_status()
    return resp.json()


def _normalize_hash(company_name: str, title: str, location: str | None) -> str:
    raw = f"{company_name.lower()}|{title.lower()}|{(location or '').lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()


class GreenhouseInput(BaseModel):
    company_name: str
    board_token: str  # e.g. "datadog", "stripe"


GREENHOUSE_BOARD_API = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"


class QueryGreenhouseJobs:
    name = "query_greenhouse_jobs"
    version = "0.1.0"
    domain = "ats"

    def run(self, input: GreenhouseInput, context: RunContext) -> SkillResult:
        url = GREENHOUSE_BOARD_API.format(token=input.board_token)
        now = datetime.utcnow()

        try:
            data = _http_get(url, timeout=context.timeout_seconds)
        except Exception as exc:
            return SkillResult.failure(f"HTTP error fetching {url}: {exc}")

        jobs_raw: list[dict] = data.get("jobs", [])
        if not isinstance(jobs_raw, list):
            return SkillResult.failure("Unexpected Greenhouse response shape", raw=data)

        items: list[NormalizedJob] = []
        errors: list[str] = []

        for raw_job in jobs_raw:
            try:
                title = raw_job.get("title", "").strip()
                job_url = raw_job.get("absolute_url", "").strip()
                if not title or not job_url:
                    errors.append(f"Skipped job missing title/url: id={raw_job.get('id')}")
                    continue

                # Location: Greenhouse nests it under offices or location
                location: str | None = None
                if raw_job.get("location", {}).get("name"):
                    location = raw_job["location"]["name"]
                elif raw_job.get("offices"):
                    location = raw_job["offices"][0].get("name")

                # Posted-at: Greenhouse uses "updated_at" at the job level
                posted_at: datetime | None = None
                if raw_job.get("updated_at"):
                    try:
                        posted_at = datetime.fromisoformat(
                            raw_job["updated_at"].replace("Z", "+00:00")
                        )
                    except ValueError:
                        pass

                # Description: may be HTML; store as-is for now
                description = ""
                if raw_job.get("content"):
                    description = raw_job["content"]

                items.append(
                    NormalizedJob(
                        title=title,
                        url=job_url,
                        location=location,
                        description_text=description,
                        source_type="greenhouse",
                        source_url=url,
                        posted_at=posted_at,
                        discovered_at=now,
                        normalized_hash=_normalize_hash(input.company_name, title, location),
                        raw_id=str(raw_job.get("id", "")),
                    )
                )
            except Exception as exc:
                errors.append(f"Parse error for job id={raw_job.get('id')}: {exc}")

        evidence = [
            Evidence(
                url=url,
                source_type="greenhouse_api",
                excerpt=f"{len(jobs_raw)} jobs returned",
                fetched_at=now,
                confidence=1.0,
            )
        ]

        return SkillResult(
            success=True,
            items=items,
            evidence=evidence,
            confidence=1.0 if items else 0.5,
            errors=errors,
            raw={"jobs_count": len(jobs_raw), "board_token": input.board_token},
        )
