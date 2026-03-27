"""
Discover recent company articles from their engineering blog.
Parses RSS feeds first, then falls back to HTML link extraction.
"""

from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urljoin

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


RSS_SUFFIXES = ["/feed", "/rss", "/feed.xml", "/rss.xml", "/atom.xml"]


class FindRecentArticlesInput(BaseModel):
    company_name: str
    blog_url: str  # URL of the engineering blog
    max_articles: int = 10


class FindRecentArticles:
    name = "find_recent_articles"
    version = "0.1.0"
    domain = "company_research"

    def run(self, input: FindRecentArticlesInput, context: RunContext) -> SkillResult:
        now = datetime.utcnow()
        articles: list[dict] = []
        errors: list[str] = []
        source_url: str | None = None

        # Try RSS first
        for suffix in RSS_SUFFIXES:
            rss_url = input.blog_url.rstrip("/") + suffix
            status, text = _http_get_text(rss_url, timeout=context.timeout_seconds)
            if status == 200 and ("<rss" in text or "<feed" in text or "<atom" in text):
                articles = _parse_rss(text, rss_url)
                source_url = rss_url
                break

        # Fall back to HTML link extraction
        if not articles:
            status, html = _http_get_text(input.blog_url, timeout=context.timeout_seconds)
            if status == 200:
                articles = _extract_article_links(html, input.blog_url)
                source_url = input.blog_url
            else:
                errors.append(f"Blog URL returned {status}: {input.blog_url}")

        articles = articles[: input.max_articles]

        evidence = []
        if source_url:
            evidence.append(
                Evidence(
                    url=source_url,
                    source_type="html_parse",
                    excerpt=f"{len(articles)} articles discovered",
                    fetched_at=now,
                    confidence=0.7,
                )
            )

        return SkillResult(
            success=bool(articles),
            items=articles,
            evidence=evidence,
            confidence=0.7 if articles else 0.0,
            errors=errors,
            raw={"source_url": source_url, "article_count": len(articles)},
        )


def _parse_rss(xml: str, source_url: str) -> list[dict]:
    articles: list[dict] = []
    items = re.findall(r"<item>(.*?)</item>", xml, re.DOTALL)
    if not items:
        items = re.findall(r"<entry>(.*?)</entry>", xml, re.DOTALL)
    for item in items[:20]:
        title = _extract_tag(item, "title")
        link = _extract_tag(item, "link") or _extract_tag(item, "id")
        pub_date = _extract_tag(item, "pubDate") or _extract_tag(item, "published")
        if title and link:
            articles.append({"title": title, "url": link, "published": pub_date, "source_url": source_url})
    return articles


def _extract_article_links(html: str, base_url: str) -> list[dict]:
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', html)
    articles: list[dict] = []
    seen: set[str] = set()
    for href in hrefs:
        full = href if href.startswith("http") else urljoin(base_url, href)
        if full in seen or full == base_url:
            continue
        path = full.split("?")[0].rstrip("/")
        # Heuristic: blog post URLs tend to have date patterns or >3 path segments
        segments = [s for s in path.split("/") if s]
        if len(segments) >= 3:
            articles.append({"title": None, "url": full, "published": None, "source_url": base_url})
            seen.add(full)
        if len(articles) >= 20:
            break
    return articles


def _extract_tag(xml: str, tag: str) -> str | None:
    m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", xml, re.DOTALL | re.IGNORECASE)
    if m:
        return re.sub(r"<[^>]+>", "", m.group(1)).strip() or None
    return None
