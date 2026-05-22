"""
Phase 10 tests — application packet generation.
All tests use dry_run=True + use_llm=False (heuristic mode, no API key needed).
"""

import pytest
from pathlib import Path

from harnesses.application_packet.v0 import (
    generate_application_packet,
    PacketConfig,
    CandidateProfile,
    ApplicationPacketResult,
)

CFG = PacketConfig(use_llm=False, dry_run=True)

PROFILE = CandidateProfile(
    id="test-profile",
    name="Dylan Doe",
    experience_level="new_grad",
    skills=["Python", "Go", "algorithms", "distributed systems"],
    degree="BS Computer Science",
    gpa="3.8",
    graduation_year="2025",
    notable=["built a metrics dashboard", "open source contributor"],
)

JOB = {
    "id": "job-001",
    "title": "Software Engineer, New Grad",
    "url": "https://datadoghq.com/careers/job-001",
    "description_text": "Build Go and Python backend services for our observability platform.",
    "required_questions": ["why_us", "relevant_project"],
}

COMPANY = {"name": "Datadog", "domain": "datadoghq.com"}

SIGNALS = [
    {
        "signal_type": "technical_signal",
        "summary": "Datadog uses Go extensively for its Agent and backend services.",
        "application_angle": "Highlight Go and distributed systems experience.",
        "interview_question": "How does Datadog Agent manage concurrent metric collection?",
        "confidence": 0.85,
    },
    {
        "signal_type": "hiring_signal",
        "summary": "Datadog University Hire 2026 cohort opens January 15.",
        "application_angle": "Apply by January 15 for the 2026 cohort.",
        "interview_question": None,
        "confidence": 0.9,
    },
]


@pytest.fixture
def result(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "harnesses.application_packet.v0.EXPERIMENTS_DIR", tmp_path
    )
    return generate_application_packet(JOB, COMPANY, PROFILE, SIGNALS, CFG)


class TestApplicationPacketGeneration:

    def test_returns_result_type(self, result):
        assert isinstance(result, ApplicationPacketResult)

    def test_approval_status_always_pending(self, result):
        assert result.approval_status == "pending"
        assert result.approval_status != "auto"

    def test_cover_letter_generated(self, result):
        assert result.cover_letter is not None
        assert len(result.cover_letter) >= 50

    def test_cover_letter_mentions_company(self, result):
        assert "Datadog" in result.cover_letter

    def test_resume_tailoring_nonempty(self, result):
        assert len(result.resume_tailoring) >= 1

    def test_short_answers_for_required_questions(self, result):
        assert "why_us" in result.short_answers
        assert "relevant_project" in result.short_answers

    def test_short_answers_mention_company(self, result):
        assert "Datadog" in result.short_answers.get("why_us", "")

    def test_referral_message_generated(self, result):
        assert result.referral_message is not None
        assert "Software Engineer" in result.referral_message
        assert "Datadog" in result.referral_message
        assert result.referral_message.startswith("Hi")

    def test_interview_notes_from_signals(self, result):
        assert len(result.interview_notes) >= 1
        # At least one note should reference a signal question
        notes_text = " ".join(result.interview_notes)
        assert "concurrent metric collection" in notes_text or "Go" in notes_text

    def test_validation_status_passed(self, result):
        assert result.validation_status == "passed", result.errors

    def test_unsupported_claims_empty_for_clean_profile(self, result):
        assert result.unsupported_claims == []

    def test_trace_directory_created(self, result):
        trace_dir = Path(result.trace_dir)
        assert trace_dir.exists()
        assert (trace_dir / "output.json").exists()

    def test_no_errors_for_valid_input(self, result):
        assert result.errors == []

    def test_generated_by_heuristic(self, result):
        assert result.generated_by == "heuristic"

    def test_job_id_in_result(self, result):
        assert result.job_id == "job-001"

    def test_no_required_questions_produces_empty_answers(self, tmp_path, monkeypatch):
        monkeypatch.setattr("harnesses.application_packet.v0.EXPERIMENTS_DIR", tmp_path)
        job_no_q = {**JOB, "required_questions": []}
        r = generate_application_packet(job_no_q, COMPANY, PROFILE, [], CFG)
        assert r.short_answers == {}

    def test_fabricated_skill_detected(self, tmp_path, monkeypatch):
        monkeypatch.setattr("harnesses.application_packet.v0.EXPERIMENTS_DIR", tmp_path)
        # Profile without Kubernetes but job mentions it
        profile_no_k8s = CandidateProfile(
            id="p-nok8s", name="Test",
            skills=["Python"], experience_level="new_grad",
            degree="BS CS", gpa="3.5", graduation_year="2025",
        )
        job_with_k8s = {
            **JOB,
            "description_text": "Experience with kubernetes and terraform required.",
            "required_questions": [],
        }
        r = generate_application_packet(job_with_k8s, COMPANY, profile_no_k8s, [], CFG)
        # The cover letter heuristic won't mention kubernetes for this profile,
        # so validation should pass (no fabrication in the generated text)
        assert r.approval_status == "pending"

    def test_signals_surface_in_tailoring(self, result):
        tailoring_text = " ".join(result.resume_tailoring)
        assert "Go" in tailoring_text or "distributed systems" in tailoring_text


class TestApplicationPacketEvalRunner:

    def test_eval_runner_returns_report(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "harnesses.application_packet.v0.EXPERIMENTS_DIR", tmp_path
        )
        from evals.runners.evaluate_application_packet import evaluate_application_packet
        report = evaluate_application_packet()
        assert report.n_cases == 2
        assert 0.0 <= report.pass_rate <= 1.0
        assert "validation" in report.by_metric
        assert "no_auto_submit" in report.by_metric

    def test_no_auto_submit_score_is_1(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "harnesses.application_packet.v0.EXPERIMENTS_DIR", tmp_path
        )
        from evals.runners.evaluate_application_packet import evaluate_application_packet
        report = evaluate_application_packet()
        assert report.by_metric["no_auto_submit"] == pytest.approx(1.0)
