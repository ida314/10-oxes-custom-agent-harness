"""Discover a company's engineering blog URL via common patterns."""

from __future__ import annotations

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


BLOG_PATHS = [
    "/engineering",
    "/blog/engineering",
    "/blog",
    "/tech",
    "/developers",
    "/developer-blog",
]

EXTERNAL_PATTERNS = [
    "engineering.{domain}",
    "tech.{domain}",
    "blog.{domain}",
]


class FindEngineeringBlogInput(BaseModel):
    company_name: str
    domain: str


class FindEngineeringBlog:
    name = "find_engineering_blog"
    version = "0.1.0"
    domain = "company_research"

    def run(self, input: FindEngineeringBlogInput, context: RunContext) -> SkillResult:
        now = datetime.utcnow()
        candidates: list[str] = []
        base_domain = input.domain.lstrip("www.")

        for path in BLOG_PATHS:
            candidates.append(f"https://{input.domain}{path}")

        for pattern in EXTERNAL_PATTERNS:
            candidates.append(f"https://{pattern.format(domain=base_domain)}")

        found: list[dict] = []
        errors: list[str] = []

        for url in candidates:
            status, _ = _http_get_text(url, timeout=context.timeout_seconds)
            if status == 200:
                found.append({"url": url, "status": status})
                break  # take first hit

        if not found:
            return SkillResult(
                success=False,
                items=[],
                errors=[f"No engineering blog found for {input.domain}"],
                confidence=0.0,
            )

        evidence = [
            Evidence(
                url=found[0]["url"],
                source_type="html_parse",
                excerpt="Engineering blog URL confirmed (HTTP 200)",
                fetched_at=now,
                confidence=0.85,
            )
        ]

        return SkillResult(
            success=True,
            items=found,
            evidence=evidence,
            confidence=0.85,
            errors=errors,
            raw={"candidates_tried": len(candidates)},
        )
