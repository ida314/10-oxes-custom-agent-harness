"""Ashby ATS connector — fetches open postings from the Ashby public API."""

from __future__ import annotations

import hashlib
from datetime import datetime

from pydantic import BaseModel

from skills.base import Evidence, NormalizedJob, RunContext, SkillResult

_http_get_fn = None


def _http_get(url: str, timeout: int = 30) -> dict:
    if _http_get_fn is not None:
        return _http_get_fn(url)
    import httpx
    resp = httpx.get(url, timeout=timeout, follow_redirects=True)
    if resp.status_code == 404:
        return {"jobPostings": []}
    resp.raise_for_status()
    return resp.json()


def _normalize_hash(company_name: str, title: str, location: str | None) -> str:
    raw = f"{company_name.lower()}|{title.lower()}|{(location or '').lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()


class AshbyInput(BaseModel):
    company_name: str
    board_slug: str  # e.g. "linear", "retool"


ASHBY_API = "https://api.ashbyhq.com/posting-api/job-board/{slug}"


class QueryAshbyJobs:
    name = "query_ashby_jobs"
    version = "0.1.0"
    domain = "ats"

    def run(self, input: AshbyInput, context: RunContext) -> SkillResult:
        url = ASHBY_API.format(slug=input.board_slug)
        now = datetime.utcnow()

        try:
            data = _http_get(url, timeout=context.timeout_seconds)
        except Exception as exc:
            return SkillResult.failure(f"HTTP error fetching {url}: {exc}")

        postings_raw: list[dict] = data.get("jobPostings", [])
        if not isinstance(postings_raw, list):
            return SkillResult.failure("Unexpected Ashby response shape", raw=data)

        items: list[NormalizedJob] = []
        errors: list[str] = []

        for raw_job in postings_raw:
            try:
                title = (raw_job.get("title") or "").strip()
                job_url = (raw_job.get("jobUrl") or raw_job.get("applyUrl") or "").strip()
                if not title or not job_url:
                    errors.append(f"Skipped posting missing title/url: id={raw_job.get('id')}")
                    continue

                # Ashby nests location in "locationName" or "primaryLocation"
                location: str | None = (
                    raw_job.get("locationName")
                    or raw_job.get("primaryLocation")
                )

                # publishedDate is ISO string
                posted_at: datetime | None = None
                if raw_job.get("publishedDate"):
                    try:
                        posted_at = datetime.fromisoformat(
                            raw_job["publishedDate"].replace("Z", "+00:00")
                        )
                    except ValueError:
                        pass

                description = raw_job.get("descriptionPlain") or raw_job.get("description") or ""

                items.append(
                    NormalizedJob(
                        title=title,
                        url=job_url,
                        location=location,
                        description_text=description,
                        source_type="ashby",
                        source_url=url,
                        posted_at=posted_at,
                        discovered_at=now,
                        normalized_hash=_normalize_hash(input.company_name, title, location),
                        raw_id=raw_job.get("id", ""),
                    )
                )
            except Exception as exc:
                errors.append(f"Parse error for posting id={raw_job.get('id')}: {exc}")

        evidence = [
            Evidence(
                url=url,
                source_type="ashby_api",
                excerpt=f"{len(postings_raw)} postings returned",
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
            raw={"postings_count": len(postings_raw), "board_slug": input.board_slug},
        )
