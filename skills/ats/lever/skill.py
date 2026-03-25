"""Lever ATS connector — fetches open postings from the Lever public API."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from pydantic import BaseModel

from skills.base import Evidence, NormalizedJob, RunContext, SkillResult

_http_get_fn = None


def _http_get(url: str, timeout: int = 30) -> list | dict:
    if _http_get_fn is not None:
        return _http_get_fn(url)
    import httpx
    resp = httpx.get(url, timeout=timeout, follow_redirects=True)
    if resp.status_code == 404:
        return []
    resp.raise_for_status()
    return resp.json()


def _normalize_hash(company_name: str, title: str, location: str | None) -> str:
    raw = f"{company_name.lower()}|{title.lower()}|{(location or '').lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()


class LeverInput(BaseModel):
    company_name: str
    board_slug: str  # e.g. "ramp", "figma"


LEVER_API = "https://api.lever.co/v0/postings/{slug}?mode=json"


class QueryLeverJobs:
    name = "query_lever_jobs"
    version = "0.1.0"
    domain = "ats"

    def run(self, input: LeverInput, context: RunContext) -> SkillResult:
        url = LEVER_API.format(slug=input.board_slug)
        now = datetime.utcnow()

        try:
            data = _http_get(url, timeout=context.timeout_seconds)
        except Exception as exc:
            return SkillResult.failure(f"HTTP error fetching {url}: {exc}")

        if not isinstance(data, list):
            return SkillResult.failure("Unexpected Lever response shape (expected list)", raw={"data": str(data)[:200]})

        items: list[NormalizedJob] = []
        errors: list[str] = []

        for raw_job in data:
            try:
                title = (raw_job.get("text") or "").strip()
                job_url = (raw_job.get("hostedUrl") or raw_job.get("applyUrl") or "").strip()
                if not title or not job_url:
                    errors.append(f"Skipped job missing title/url: id={raw_job.get('id')}")
                    continue

                # Location: Lever nests as categories.location or workplaceType
                location: str | None = None
                categories = raw_job.get("categories", {})
                if categories.get("location"):
                    location = categories["location"]
                elif categories.get("commitment"):
                    location = categories.get("commitment")

                # createdAt is epoch ms
                posted_at: datetime | None = None
                if raw_job.get("createdAt"):
                    try:
                        posted_at = datetime.fromtimestamp(
                            raw_job["createdAt"] / 1000, tz=timezone.utc
                        )
                    except (ValueError, OSError):
                        pass

                description = raw_job.get("descriptionPlain") or raw_job.get("description") or ""

                items.append(
                    NormalizedJob(
                        title=title,
                        url=job_url,
                        location=location,
                        description_text=description,
                        source_type="lever",
                        source_url=url,
                        posted_at=posted_at,
                        discovered_at=now,
                        normalized_hash=_normalize_hash(input.company_name, title, location),
                        raw_id=raw_job.get("id", ""),
                    )
                )
            except Exception as exc:
                errors.append(f"Parse error for job id={raw_job.get('id')}: {exc}")

        evidence = [
            Evidence(
                url=url,
                source_type="lever_api",
                excerpt=f"{len(data)} postings returned",
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
            raw={"postings_count": len(data), "board_slug": input.board_slug},
        )
