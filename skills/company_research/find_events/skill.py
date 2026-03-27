"""
Discover company events (hackathons, info sessions, career fairs) from their
careers and events pages via HTML pattern matching.
"""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel

from skills.base import Evidence, RunContext, SkillResult

_http_get_text_fn = None


def _http_get_text(url: str, timeout: int = 15) -> tuple[int, str]:
    if _http_get_text_fn is not None:
        return _http_get_text_fn(url)
    import httpx
    try:
        resp = httpx.get(url, timeout=timeout, follow_redirects=True)
        return resp.status_code, resp.text
    except Exception:
        return 0, ""


EVENT_PATHS = ["/events", "/university", "/campus", "/students", "/careers/events"]
EVENT_KEYWORDS = [
    "hackathon", "info session", "information session", "career fair",
    "tech talk", "webinar", "workshop", "recruiting event", "campus event",
    "open house", "intern", "university hiring",
]


class FindEventsInput(BaseModel):
    company_name: str
    domain: str


class FindEvents:
    name = "find_events"
    version = "0.1.0"
    domain = "company_research"

    def run(self, input: FindEventsInput, context: RunContext) -> SkillResult:
        now = datetime.utcnow()
        base = f"https://{input.domain}"
        found_events: list[dict] = []
        errors: list[str] = []
        source_url: str | None = None

        for path in EVENT_PATHS:
            url = base + path
            status, html = _http_get_text(url, timeout=context.timeout_seconds)
            if status == 200:
                source_url = url
                found_events = _extract_events(html, url, input.company_name)
                if found_events:
                    break

        evidence = []
        if source_url:
            evidence.append(
                Evidence(
                    url=source_url,
                    source_type="html_parse",
                    excerpt=f"{len(found_events)} events extracted",
                    fetched_at=now,
                    confidence=0.6,
                )
            )

        return SkillResult(
            success=True,
            items=found_events,
            evidence=evidence,
            confidence=0.6 if found_events else 0.2,
            errors=errors,
            raw={"source_url": source_url},
        )


def _extract_events(html: str, source_url: str, company_name: str) -> list[dict]:
    html_lower = html.lower()
    found: list[dict] = []
    for kw in EVENT_KEYWORDS:
        if kw in html_lower:
            # Find surrounding text snippet
            idx = html_lower.find(kw)
            snippet = html[max(0, idx - 50): idx + 150].strip()
            # Strip tags
            snippet = re.sub(r"<[^>]+>", " ", snippet).strip()
            if snippet:
                found.append({
                    "keyword": kw,
                    "snippet": snippet,
                    "source_url": source_url,
                    "company_name": company_name,
                })
    return found[:10]
