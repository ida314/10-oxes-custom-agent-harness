"""
Tests for Phase 2 ATS connectors and company research skills.
All tests use saved fixtures — no live network calls.
"""

import json
from pathlib import Path
from datetime import datetime

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> dict | list:
    return json.loads(path.read_text())


def _load_text(path: Path) -> str:
    return path.read_text()


def _make_context():
    from skills.base import RunContext
    return RunContext(timeout_seconds=5)


# ---------------------------------------------------------------------------
# Greenhouse tests
# ---------------------------------------------------------------------------

class TestGreenhouseSkill:

    @pytest.fixture(autouse=True)
    def patch_http(self, monkeypatch):
        data = _load_json(FIXTURES / "greenhouse" / "datadog_jobs.json")
        import skills.ats.greenhouse.skill as mod
        monkeypatch.setattr(mod, "_http_get_fn", lambda url: data)

    def test_returns_normalized_jobs(self):
        from skills.ats.greenhouse.skill import QueryGreenhouseJobs, GreenhouseInput
        skill = QueryGreenhouseJobs()
        result = skill.run(
            GreenhouseInput(company_name="Datadog", board_token="datadog"),
            _make_context(),
        )
        assert result.success is True
        assert len(result.items) == 4  # 4 valid; 1 skipped (missing title/url)

    def test_jobs_have_required_fields(self):
        from skills.ats.greenhouse.skill import QueryGreenhouseJobs, GreenhouseInput
        skill = QueryGreenhouseJobs()
        result = skill.run(
            GreenhouseInput(company_name="Datadog", board_token="datadog"),
            _make_context(),
        )
        for job in result.items:
            assert job.title
            assert job.url
            assert job.source_type == "greenhouse"
            assert job.normalized_hash
            assert isinstance(job.discovered_at, datetime)

    def test_skips_jobs_missing_title_or_url(self):
        from skills.ats.greenhouse.skill import QueryGreenhouseJobs, GreenhouseInput
        skill = QueryGreenhouseJobs()
        result = skill.run(
            GreenhouseInput(company_name="Datadog", board_token="datadog"),
            _make_context(),
        )
        titles = [j.title for j in result.items]
        assert "" not in titles
        assert len(result.errors) == 1  # the empty-title job

    def test_empty_board_returns_success_with_no_items(self, monkeypatch):
        empty = _load_json(FIXTURES / "greenhouse" / "empty_board.json")
        import skills.ats.greenhouse.skill as mod
        monkeypatch.setattr(mod, "_http_get_fn", lambda url: empty)

        from skills.ats.greenhouse.skill import QueryGreenhouseJobs, GreenhouseInput
        skill = QueryGreenhouseJobs()
        result = skill.run(
            GreenhouseInput(company_name="Unknown", board_token="unknown"),
            _make_context(),
        )
        assert result.success is True
        assert result.items == []

    def test_http_error_returns_failure(self, monkeypatch):
        import skills.ats.greenhouse.skill as mod
        def raise_error(url):
            raise ConnectionError("Connection refused")
        monkeypatch.setattr(mod, "_http_get_fn", raise_error)

        from skills.ats.greenhouse.skill import QueryGreenhouseJobs, GreenhouseInput
        skill = QueryGreenhouseJobs()
        result = skill.run(
            GreenhouseInput(company_name="Datadog", board_token="datadog"),
            _make_context(),
        )
        assert result.success is False
        assert len(result.errors) == 1

    def test_normalized_hashes_differ_by_location(self):
        from skills.ats.greenhouse.skill import QueryGreenhouseJobs, GreenhouseInput
        skill = QueryGreenhouseJobs()
        result = skill.run(
            GreenhouseInput(company_name="Datadog", board_token="datadog"),
            _make_context(),
        )
        # Job 5001 (NY) and job 5002 (SF) are different roles — different hashes
        hashes = [j.normalized_hash for j in result.items]
        assert len(set(hashes)) == len(hashes), "Normalized hashes must be unique per job"

    def test_evidence_populated(self):
        from skills.ats.greenhouse.skill import QueryGreenhouseJobs, GreenhouseInput
        skill = QueryGreenhouseJobs()
        result = skill.run(
            GreenhouseInput(company_name="Datadog", board_token="datadog"),
            _make_context(),
        )
        assert len(result.evidence) == 1
        assert result.evidence[0].source_type == "greenhouse_api"


# ---------------------------------------------------------------------------
# Lever tests
# ---------------------------------------------------------------------------

class TestLeverSkill:

    @pytest.fixture(autouse=True)
    def patch_http(self, monkeypatch):
        data = _load_json(FIXTURES / "lever" / "ramp_jobs.json")
        import skills.ats.lever.skill as mod
        monkeypatch.setattr(mod, "_http_get_fn", lambda url: data)

    def test_returns_normalized_jobs(self):
        from skills.ats.lever.skill import QueryLeverJobs, LeverInput
        skill = QueryLeverJobs()
        result = skill.run(
            LeverInput(company_name="Ramp", board_slug="ramp"),
            _make_context(),
        )
        assert result.success is True
        assert len(result.items) == 3

    def test_jobs_have_required_fields(self):
        from skills.ats.lever.skill import QueryLeverJobs, LeverInput
        skill = QueryLeverJobs()
        result = skill.run(LeverInput(company_name="Ramp", board_slug="ramp"), _make_context())
        for job in result.items:
            assert job.title
            assert job.url
            assert job.source_type == "lever"
            assert job.normalized_hash

    def test_empty_array_returns_success(self, monkeypatch):
        import skills.ats.lever.skill as mod
        monkeypatch.setattr(mod, "_http_get_fn", lambda url: [])
        from skills.ats.lever.skill import QueryLeverJobs, LeverInput
        result = QueryLeverJobs().run(LeverInput(company_name="X", board_slug="x"), _make_context())
        assert result.success is True
        assert result.items == []

    def test_http_error_returns_failure(self, monkeypatch):
        import skills.ats.lever.skill as mod
        monkeypatch.setattr(mod, "_http_get_fn", lambda url: (_ for _ in ()).throw(ConnectionError("err")))
        from skills.ats.lever.skill import QueryLeverJobs, LeverInput
        # Use a simpler raise approach
        def raise_err(url):
            raise ConnectionError("err")
        monkeypatch.setattr(mod, "_http_get_fn", raise_err)
        result = QueryLeverJobs().run(LeverInput(company_name="X", board_slug="x"), _make_context())
        assert result.success is False


# ---------------------------------------------------------------------------
# Ashby tests
# ---------------------------------------------------------------------------

class TestAshbySkill:

    @pytest.fixture(autouse=True)
    def patch_http(self, monkeypatch):
        data = _load_json(FIXTURES / "ashby" / "linear_jobs.json")
        import skills.ats.ashby.skill as mod
        monkeypatch.setattr(mod, "_http_get_fn", lambda url: data)

    def test_returns_normalized_jobs(self):
        from skills.ats.ashby.skill import QueryAshbyJobs, AshbyInput
        result = QueryAshbyJobs().run(
            AshbyInput(company_name="Linear", board_slug="linear"),
            _make_context(),
        )
        assert result.success is True
        assert len(result.items) == 2

    def test_jobs_have_required_fields(self):
        from skills.ats.ashby.skill import QueryAshbyJobs, AshbyInput
        result = QueryAshbyJobs().run(
            AshbyInput(company_name="Linear", board_slug="linear"), _make_context()
        )
        for job in result.items:
            assert job.title
            assert job.url
            assert job.source_type == "ashby"
            assert job.normalized_hash

    def test_posted_at_parsed(self):
        from skills.ats.ashby.skill import QueryAshbyJobs, AshbyInput
        result = QueryAshbyJobs().run(
            AshbyInput(company_name="Linear", board_slug="linear"), _make_context()
        )
        assert result.items[0].posted_at is not None

    def test_empty_board_returns_success(self, monkeypatch):
        import skills.ats.ashby.skill as mod
        monkeypatch.setattr(mod, "_http_get_fn", lambda url: {"jobPostings": []})
        from skills.ats.ashby.skill import QueryAshbyJobs, AshbyInput
        result = QueryAshbyJobs().run(AshbyInput(company_name="X", board_slug="x"), _make_context())
        assert result.success is True
        assert result.items == []


# ---------------------------------------------------------------------------
# FindCareersPage tests
# ---------------------------------------------------------------------------

class TestFindCareersPage:

    def _make_http_fn(self, html: str, status: int = 200):
        call_count = {"n": 0}
        def fn(url):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return status, html
            return 404, ""
        return fn

    def test_finds_job_links(self, monkeypatch):
        html = _load_text(FIXTURES / "careers_page" / "stripe_careers.html")
        import skills.company_research.find_careers_page.skill as mod
        monkeypatch.setattr(mod, "_http_get_text_fn", self._make_http_fn(html))

        from skills.company_research.find_careers_page.skill import FindCareersPage, FindCareersPageInput
        result = FindCareersPage().run(
            FindCareersPageInput(company_name="Stripe", domain="stripe.com"),
            _make_context(),
        )
        assert result.success is True
        assert len(result.items) > 0
        assert all(isinstance(u, str) for u in result.items)

    def test_returns_failure_when_no_page_found(self, monkeypatch):
        import skills.company_research.find_careers_page.skill as mod
        monkeypatch.setattr(mod, "_http_get_text_fn", lambda url: (404, ""))

        from skills.company_research.find_careers_page.skill import FindCareersPage, FindCareersPageInput
        result = FindCareersPage().run(
            FindCareersPageInput(company_name="Acme", domain="acme-unknown.com"),
            _make_context(),
        )
        assert result.success is False
        assert result.items == []

    def test_evidence_populated_on_success(self, monkeypatch):
        html = _load_text(FIXTURES / "careers_page" / "stripe_careers.html")
        import skills.company_research.find_careers_page.skill as mod
        monkeypatch.setattr(mod, "_http_get_text_fn", self._make_http_fn(html))

        from skills.company_research.find_careers_page.skill import FindCareersPage, FindCareersPageInput
        result = FindCareersPage().run(
            FindCareersPageInput(company_name="Stripe", domain="stripe.com"),
            _make_context(),
        )
        assert len(result.evidence) == 1
        assert result.evidence[0].source_type == "html_parse"


# ---------------------------------------------------------------------------
# FindRecentArticles tests
# ---------------------------------------------------------------------------

class TestFindRecentArticles:

    RSS_FIXTURE = """<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>Stripe Engineering Blog</title>
    <item>
      <title>How Stripe Engineers Think About API Design</title>
      <link>https://stripe.com/blog/api-design-principles</link>
      <pubDate>Mon, 15 Jun 2025 00:00:00 +0000</pubDate>
    </item>
    <item>
      <title>Scaling Stripe's Payments Infrastructure</title>
      <link>https://stripe.com/blog/payments-scaling</link>
      <pubDate>Tue, 01 Apr 2025 00:00:00 +0000</pubDate>
    </item>
  </channel>
</rss>"""

    def test_parses_rss_feed(self, monkeypatch):
        rss = self.RSS_FIXTURE
        import skills.company_research.find_recent_articles.skill as mod
        call_count = {"n": 0}
        def fn(url):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return 200, rss
            return 404, ""
        monkeypatch.setattr(mod, "_http_get_text_fn", fn)

        from skills.company_research.find_recent_articles.skill import FindRecentArticles, FindRecentArticlesInput
        result = FindRecentArticles().run(
            FindRecentArticlesInput(company_name="Stripe", blog_url="https://stripe.com/blog/engineering"),
            _make_context(),
        )
        assert result.success is True
        assert len(result.items) == 2
        assert result.items[0]["title"] == "How Stripe Engineers Think About API Design"

    def test_returns_failure_when_blog_unreachable(self, monkeypatch):
        import skills.company_research.find_recent_articles.skill as mod
        monkeypatch.setattr(mod, "_http_get_text_fn", lambda url: (0, ""))

        from skills.company_research.find_recent_articles.skill import FindRecentArticles, FindRecentArticlesInput
        result = FindRecentArticles().run(
            FindRecentArticlesInput(company_name="X", blog_url="https://x.com/blog"),
            _make_context(),
        )
        assert result.success is False

    def test_max_articles_respected(self, monkeypatch):
        rss = self.RSS_FIXTURE
        import skills.company_research.find_recent_articles.skill as mod
        monkeypatch.setattr(mod, "_http_get_text_fn", lambda url: (200, rss))

        from skills.company_research.find_recent_articles.skill import FindRecentArticles, FindRecentArticlesInput
        result = FindRecentArticles().run(
            FindRecentArticlesInput(
                company_name="Stripe",
                blog_url="https://stripe.com/blog/engineering",
                max_articles=1,
            ),
            _make_context(),
        )
        assert len(result.items) <= 1
