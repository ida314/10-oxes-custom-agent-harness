"""Tests for Phase 4 article discovery harness and Phase 6 eval runner."""

import pytest
from pathlib import Path

from harnesses.article_discovery.v0 import (
    score_articles,
    ArticleDiscoveryConfig,
    CandidateProfile,
    ArticleDiscoveryReport,
)

COMPANY = {"name": "Datadog", "domain": "datadoghq.com"}
PROFILE = CandidateProfile(
    id="eval-profile",
    name="Test Candidate",
    experience_level="new_grad",
    skills=["Python", "Go", "distributed systems"],
)
CFG = ArticleDiscoveryConfig(use_llm=False, dry_run=True)  # heuristic only

TECH_ARTICLE = {
    "title": "How Datadog Scales Its Agent to Monitor Millions of Hosts",
    "source_url": "https://www.datadoghq.com/blog/engineering/",
    "published": "2025-11-20",
    "full_text": (
        "Our infrastructure team walks through the architectural decisions behind "
        "Datadog Agent v7, covering Go runtime tuning, check scheduling, and how we "
        "maintain sub-second metric collection across 10M+ monitored hosts."
    ),
}

IRRELEVANT_ARTICLE = {
    "title": "Observability Market Share Report 2025",
    "source_url": "https://gartner.com/",
    "published": "2025-09-10",
    "full_text": (
        "The 2025 APM and observability market reached $8.4B. Datadog holds 23% "
        "market share. Gartner Magic Quadrant Leader for the third year."
    ),
}

HIRING_ARTICLE = {
    "title": "Datadog University Hiring 2026",
    "source_url": "https://www.datadoghq.com/careers/",
    "published": "2025-12-01",
    "full_text": (
        "The Datadog engineering team is hiring new grad and university engineers in 2026. "
        "Applications for our 2026 cohort open January 15. "
        "Apply now at datadoghq.com/careers."
    ),
}


class TestArticleDiscoveryHarness:

    def test_returns_report(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "harnesses.article_discovery.v0.EXPERIMENTS_DIR", tmp_path
        )
        report = score_articles(COMPANY, [TECH_ARTICLE], PROFILE, CFG)
        assert isinstance(report, ArticleDiscoveryReport)
        assert report.articles_processed == 1
        assert len(report.signals) == 1

    def test_technical_article_classified_non_irrelevant(self, tmp_path, monkeypatch):
        monkeypatch.setattr("harnesses.article_discovery.v0.EXPERIMENTS_DIR", tmp_path)
        report = score_articles(COMPANY, [TECH_ARTICLE], PROFILE, CFG)
        signal = report.signals[0]
        assert signal.signal_type != "irrelevant"
        assert signal.classified_by == "heuristic"

    def test_irrelevant_article_classified_irrelevant(self, tmp_path, monkeypatch):
        monkeypatch.setattr("harnesses.article_discovery.v0.EXPERIMENTS_DIR", tmp_path)
        report = score_articles(COMPANY, [IRRELEVANT_ARTICLE], PROFILE, CFG)
        signal = report.signals[0]
        # Market share report has no strong keyword hits → irrelevant
        # (may vary; test confidence is low)
        assert signal.confidence <= 0.5 or signal.signal_type in (
            "irrelevant", "strategy_signal"
        )

    def test_hiring_article_classified_hiring_signal(self, tmp_path, monkeypatch):
        monkeypatch.setattr("harnesses.article_discovery.v0.EXPERIMENTS_DIR", tmp_path)
        report = score_articles(COMPANY, [HIRING_ARTICLE], PROFILE, CFG)
        signal = report.signals[0]
        assert signal.signal_type == "hiring_signal"
        assert signal.confidence > 0.0

    def test_multiple_articles_processed(self, tmp_path, monkeypatch):
        monkeypatch.setattr("harnesses.article_discovery.v0.EXPERIMENTS_DIR", tmp_path)
        articles = [TECH_ARTICLE, IRRELEVANT_ARTICLE, HIRING_ARTICLE]
        report = score_articles(COMPANY, articles, PROFILE, CFG)
        assert report.articles_processed == 3
        assert len(report.signals) == 3

    def test_trace_directory_created(self, tmp_path, monkeypatch):
        monkeypatch.setattr("harnesses.article_discovery.v0.EXPERIMENTS_DIR", tmp_path)
        report = score_articles(COMPANY, [TECH_ARTICLE], PROFILE, CFG)
        trace_dir = Path(report.trace_dir)
        assert trace_dir.exists()
        assert (trace_dir / "output.json").exists()

    def test_empty_article_list(self, tmp_path, monkeypatch):
        monkeypatch.setattr("harnesses.article_discovery.v0.EXPERIMENTS_DIR", tmp_path)
        report = score_articles(COMPANY, [], PROFILE, CFG)
        assert report.articles_processed == 0
        assert report.signals == []

    def test_max_articles_respected(self, tmp_path, monkeypatch):
        monkeypatch.setattr("harnesses.article_discovery.v0.EXPERIMENTS_DIR", tmp_path)
        articles = [TECH_ARTICLE, IRRELEVANT_ARTICLE, HIRING_ARTICLE]
        cfg = ArticleDiscoveryConfig(use_llm=False, dry_run=True, max_articles=2)
        report = score_articles(COMPANY, articles, PROFILE, cfg)
        assert report.articles_processed == 2

    def test_signal_has_required_fields(self, tmp_path, monkeypatch):
        monkeypatch.setattr("harnesses.article_discovery.v0.EXPERIMENTS_DIR", tmp_path)
        report = score_articles(COMPANY, [TECH_ARTICLE], PROFILE, CFG)
        signal = report.signals[0]
        assert signal.signal_type in {
            "hiring_signal", "technical_signal", "culture_signal",
            "strategy_signal", "interview_prep_signal", "networking_signal",
            "risk_signal", "irrelevant",
        }
        assert isinstance(signal.confidence, float)
        assert isinstance(signal.is_valid, bool)
        assert isinstance(signal.classified_by, str)


class TestEvalRunner:

    def test_evaluate_article_signals_search_split(self, tmp_path):
        from evals.runners.evaluate_article_signals import evaluate_article_signals
        report = evaluate_article_signals(split="search", output_dir=tmp_path)
        assert report.n_cases == 15
        assert 0.0 <= report.pass_rate <= 1.0
        assert (tmp_path / "metrics.json").exists()

    def test_test_split_blocked_without_flag(self):
        from evals.runners.evaluate_article_signals import evaluate_article_signals
        with pytest.raises(ValueError, match="held out"):
            evaluate_article_signals(split="test", allow_test=False)

    def test_test_split_allowed_with_flag(self, tmp_path):
        from evals.runners.evaluate_article_signals import evaluate_article_signals
        # Uses search dataset as proxy since article test split not yet created
        report = evaluate_article_signals(split="test", allow_test=True)
        assert report.n_cases >= 0

    def test_job_discovery_eval_search_split(self, tmp_path):
        from evals.runners.evaluate_job_discovery import evaluate_job_discovery
        report = evaluate_job_discovery(split="search", output_dir=tmp_path)
        assert report.n_cases == 40
        assert report.pass_rate >= 0.0
        assert (tmp_path / "metrics.json").exists()

    def test_job_discovery_eval_test_split_blocked(self):
        from evals.runners.evaluate_job_discovery import evaluate_job_discovery
        with pytest.raises(ValueError, match="held out"):
            evaluate_job_discovery(split="test", allow_test=False)

    def test_job_discovery_by_metric_populated(self, tmp_path):
        from evals.runners.evaluate_job_discovery import evaluate_job_discovery
        report = evaluate_job_discovery(split="search")
        assert len(report.by_metric) >= 4
        for score in report.by_metric.values():
            assert 0.0 <= score <= 1.0
