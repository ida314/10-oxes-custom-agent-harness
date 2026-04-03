"""
Tests for harnesses/job_discovery/v0.py.
All tests use fixture data + monkeypatching — no live network, no Postgres.
"""

import json
from pathlib import Path

import pytest

from harnesses.job_discovery.v0 import (
    run_company_scan,
    HarnessConfig,
    CandidateProfile,
    CompanyScanReport,
)

FIXTURES = Path(__file__).parent / "fixtures"

DATADOG_COMPANY = {
    "id": "test-datadog-001",
    "name": "Datadog",
    "domain": "datadoghq.com",
    "ats_type": "greenhouse",
    "careers_url": "https://www.datadoghq.com/careers/",
    "priority": 2,
}

RAMP_COMPANY = {
    "id": "test-ramp-001",
    "name": "Ramp",
    "domain": "ramp.com",
    "ats_type": "lever",
    "careers_url": "https://ramp.com/careers",
    "priority": 2,
}

SAMPLE_PROFILE = CandidateProfile(
    id="profile-001",
    name="Test Candidate",
    experience_level="new_grad",
    skills=["Python", "Go", "algorithms", "data structures"],
    graduation_year=2025,
)


def _patch_greenhouse(monkeypatch, fixture="datadog_jobs.json"):
    data = json.loads((FIXTURES / "greenhouse" / fixture).read_text())
    import skills.ats.greenhouse.skill as mod
    monkeypatch.setattr(mod, "_http_get_fn", lambda url: data)


def _patch_lever(monkeypatch, fixture="ramp_jobs.json"):
    data = json.loads((FIXTURES / "lever" / fixture).read_text())
    import skills.ats.lever.skill as mod
    monkeypatch.setattr(mod, "_http_get_fn", lambda url: data)


def _patch_no_blog(monkeypatch):
    import skills.company_research.find_recent_articles.skill as mod
    monkeypatch.setattr(mod, "_http_get_text_fn", lambda url: (404, ""))
    import skills.company_research.find_events.skill as mod2
    monkeypatch.setattr(mod2, "_http_get_text_fn", lambda url: (404, ""))
    import skills.company_research.find_engineering_blog.skill as mod3
    monkeypatch.setattr(mod3, "_http_get_text_fn", lambda url: (404, ""))
    import skills.company_research.find_careers_page.skill as mod4
    monkeypatch.setattr(mod4, "_http_get_text_fn", lambda url: (404, ""))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestJobDiscoveryHarnessV0:

    def test_runs_end_to_end_greenhouse(self, monkeypatch):
        _patch_greenhouse(monkeypatch)
        _patch_no_blog(monkeypatch)

        report = run_company_scan(
            company_id="test-datadog-001",
            profile_id="profile-001",
            config=HarnessConfig(dry_run=True),
            profile=SAMPLE_PROFILE,
            company_override=DATADOG_COMPANY,
        )
        assert isinstance(report, CompanyScanReport)
        assert report.jobs_discovered == 4  # 4 valid from fixture (1 skipped)
        assert report.jobs_after_dedup == 4

    def test_runs_end_to_end_lever(self, monkeypatch):
        _patch_lever(monkeypatch)
        _patch_no_blog(monkeypatch)

        report = run_company_scan(
            company_id="test-ramp-001",
            profile_id="profile-001",
            config=HarnessConfig(dry_run=True),
            profile=SAMPLE_PROFILE,
            company_override=RAMP_COMPANY,
        )
        assert report.jobs_discovered == 3
        assert report.jobs_after_dedup == 3

    def test_deduplication_removes_same_hash(self, monkeypatch):
        # Inject duplicate jobs by returning same fixture twice
        data = json.loads((FIXTURES / "greenhouse" / "datadog_jobs.json").read_text())
        # Add a duplicate entry (same title+location → same hash)
        data["jobs"].append(data["jobs"][0].copy())  # exact duplicate
        import skills.ats.greenhouse.skill as mod
        monkeypatch.setattr(mod, "_http_get_fn", lambda url: data)
        _patch_no_blog(monkeypatch)

        report = run_company_scan(
            company_id="test-datadog-001",
            profile_id="profile-001",
            config=HarnessConfig(dry_run=True),
            company_override=DATADOG_COMPANY,
        )
        # Duplicate should be removed
        assert report.jobs_after_dedup < report.jobs_discovered

    def test_senior_jobs_scored_low(self, monkeypatch):
        _patch_greenhouse(monkeypatch)
        _patch_no_blog(monkeypatch)

        report = run_company_scan(
            company_id="test-datadog-001",
            profile_id="profile-001",
            config=HarnessConfig(dry_run=True),
            profile=SAMPLE_PROFILE,
            company_override=DATADOG_COMPANY,
        )
        senior_jobs = [s for s in report.scored_jobs if "senior" in s.job.title.lower()]
        for sj in senior_jobs:
            assert sj.entry_level_score < 0.5
            assert sj.recommendation in ("skip", "research")

    def test_new_grad_jobs_scored_high(self, monkeypatch):
        _patch_greenhouse(monkeypatch)
        _patch_no_blog(monkeypatch)

        report = run_company_scan(
            company_id="test-datadog-001",
            profile_id="profile-001",
            config=HarnessConfig(dry_run=True),
            profile=SAMPLE_PROFILE,
            company_override=DATADOG_COMPANY,
        )
        ng_jobs = [s for s in report.scored_jobs if "university" in s.job.title.lower()]
        for sj in ng_jobs:
            assert sj.entry_level_score >= 0.7

    def test_trace_directory_created(self, monkeypatch, tmp_path, monkeypatch_experiments):
        _patch_greenhouse(monkeypatch)
        _patch_no_blog(monkeypatch)

        report = run_company_scan(
            company_id="test-datadog-001",
            profile_id="profile-001",
            config=HarnessConfig(dry_run=True),
            company_override=DATADOG_COMPANY,
        )
        trace_dir = Path(report.trace_dir)
        assert trace_dir.exists()
        assert (trace_dir / "output.json").exists()
        # At least a few trace event files
        trace_files = list(trace_dir.glob("*.json"))
        assert len(trace_files) >= 3

    def test_invalid_ats_type_returns_empty(self, monkeypatch):
        _patch_no_blog(monkeypatch)
        company = {**DATADOG_COMPANY, "ats_type": "unknown_ats"}

        report = run_company_scan(
            company_id="test-datadog-001",
            profile_id="profile-001",
            config=HarnessConfig(dry_run=True),
            company_override=company,
        )
        assert report.jobs_discovered == 0

    def test_report_has_all_required_fields(self, monkeypatch):
        _patch_greenhouse(monkeypatch)
        _patch_no_blog(monkeypatch)

        report = run_company_scan(
            company_id="test-datadog-001",
            profile_id="profile-001",
            config=HarnessConfig(dry_run=True),
            company_override=DATADOG_COMPANY,
        )
        assert report.company_id == "test-datadog-001"
        assert report.company_name == "Datadog"
        assert report.harness_version == "v0"
        assert report.started_at is not None
        assert report.finished_at is not None
        assert report.finished_at >= report.started_at
        assert isinstance(report.errors, list)
        assert isinstance(report.scored_jobs, list)


@pytest.fixture
def monkeypatch_experiments(monkeypatch, tmp_path):
    """Redirect experiment traces to tmp_path during tests."""
    import harnesses.job_discovery.v0 as mod
    monkeypatch.setattr(mod, "EXPERIMENTS_DIR", tmp_path)
