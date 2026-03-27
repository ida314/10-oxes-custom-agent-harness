"""
Find a company's careers page URL via common URL patterns, then extract job links.
Used as fallback when no ATS connector matches.
"""

from __future__ import annotations

from datetime import datetime
from urllib.parse import urljoin, urlparse

from pydantic import BaseModel

from skills.base import Evidence, RunContext, SkillResult

_http_get_text_fn = None


def _http_get_text(url: str, timeout: int = 20) -> tuple[int, str]:
    """Returns (status_code, text)."""
    if _http_get_text_fn is not None:
        return _http_get_text_fn(url)
    import httpx
    try:
        resp = httpx.get(url, timeout=timeout, follow_redirects=True)
        return resp.status_code, resp.text
    except Exception:
        return 0, ""


CAREERS_PATHS = ["/careers", "/jobs", "/work-with-us", "/join-us", "/about/careers"]


class FindCareersPageInput(BaseModel):
    company_name: str
    domain: str  # e.g. "stripe.com"


class FindCareersPage:
    name = "find_careers_page"
    version = "0.1.0"
    domain = "company_research"

    def run(self, input: FindCareersPageInput, context: RunContext) -> SkillResult:
        now = datetime.utcnow()
        base = f"https://{input.domain}"
        found_url: str | None = None
        job_links: list[str] = []
        errors: list[str] = []

        for path in CAREERS_PATHS:
            candidate = base + path
            status, html = _http_get_text(candidate, timeout=context.timeout_seconds)
            if status == 200:
                found_url = candidate
                job_links = _extract_job_links(html, candidate)
                break
            elif status not in (0, 404, 403):
                errors.append(f"{candidate} returned {status}")

        if not found_url:
            return SkillResult(
                success=False,
                items=[],
                evidence=[],
                confidence=0.0,
                errors=errors + [f"No careers page found at common paths for {input.domain}"],
            )

        evidence = [
            Evidence(
                url=found_url,
                source_type="html_parse",
                excerpt=f"{len(job_links)} job links extracted",
                fetched_at=now,
                confidence=0.8,
            )
        ]

        return SkillResult(
            success=True,
            items=job_links,  # list of URL strings
            evidence=evidence,
            confidence=0.8,
            errors=errors,
            raw={"careers_url": found_url, "job_links_count": len(job_links)},
        )


def _extract_job_links(html: str, base_url: str) -> list[str]:
    """Extract href links that look like job postings."""
    import re
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', html)
    domain = urlparse(base_url).netloc
    job_keywords = {"job", "jobs", "career", "careers", "posting", "position", "opening", "role"}
    results: list[str] = []
    seen: set[str] = set()

    for href in hrefs:
        if href.startswith("#") or href.startswith("mailto:"):
            continue
        full = href if href.startswith("http") else urljoin(base_url, href)
        parsed = urlparse(full)
        path_lower = parsed.path.lower()
        if parsed.netloc and parsed.netloc != domain:
            continue
        if any(kw in path_lower for kw in job_keywords) and full not in seen:
            results.append(full)
            seen.add(full)
        if len(results) >= 50:
            break

    return results
