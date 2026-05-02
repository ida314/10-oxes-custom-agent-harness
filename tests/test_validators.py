"""
Phase 7 validator tests — positive and negative cases for every validator.
All pure Python, no network, no DB.
"""

import pytest
from harnesses.validators.base import ValidationResult
from harnesses.validators.job import is_valid_job, is_safe_to_apply, entry_level_score
from harnesses.validators.article_signal import is_valid_article_signal
from harnesses.validators.recommendation import (
    is_valid_recommendation,
    is_safe_application_recommendation,
)
from harnesses.validators.application_packet import is_valid_application_packet
from harnesses.validators.browser_action import (
    is_allowed_browser_action,
    is_safe_page_state,
)
from harnesses.validators.retry import validate_with_retry
from skills.base import NormalizedJob
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _job(title="Software Engineer, New Grad", url="https://co.com/jobs/1",
         location="NY", posted_days_ago=10):
    from datetime import timedelta
    posted = datetime.now(timezone.utc) - timedelta(days=posted_days_ago)
    return NormalizedJob(
        title=title,
        url=url,
        location=location,
        description_text="Build things.",
        source_type="greenhouse",
        source_url="https://co.com/",
        discovered_at=datetime.now(timezone.utc),
        normalized_hash="abc123",
        posted_at=posted,
    )


# ---------------------------------------------------------------------------
# ValidationResult base
# ---------------------------------------------------------------------------

class TestValidationResultBase:
    def test_valid_no_codes(self):
        r = ValidationResult(valid=True)
        assert r.valid
        assert r.reason_codes == []

    def test_merge_both_valid(self):
        a = ValidationResult(valid=True)
        b = ValidationResult(valid=True)
        assert a.merge(b).valid

    def test_merge_one_invalid(self):
        a = ValidationResult(valid=True)
        b = ValidationResult(valid=False, reason_codes=["missing_url"])
        merged = a.merge(b)
        assert not merged.valid
        assert "missing_url" in merged.reason_codes

    def test_merge_collects_all_codes(self):
        a = ValidationResult(valid=False, reason_codes=["code_a"])
        b = ValidationResult(valid=False, reason_codes=["code_b"])
        merged = a.merge(b)
        assert "code_a" in merged.reason_codes
        assert "code_b" in merged.reason_codes


# ---------------------------------------------------------------------------
# Job validator
# ---------------------------------------------------------------------------

class TestJobValidator:
    def test_valid_new_grad_job(self):
        result = is_valid_job(_job())
        assert result.valid

    def test_missing_url_invalid(self):
        job = _job(url="")
        result = is_valid_job(job)
        assert not result.valid
        assert "missing_url" in result.reason_codes

    def test_senior_title_invalid(self):
        job = _job(title="Senior Software Engineer")
        result = is_valid_job(job)
        assert not result.valid
        assert "likely_senior_role" in result.reason_codes

    def test_staff_title_invalid(self):
        result = is_valid_job(_job(title="Staff Engineer, Platform"))
        assert not result.valid

    def test_new_grad_overrides_senior_keyword(self):
        # "Senior" in title but also "New Grad" → treated as entry level
        result = is_valid_job(_job(title="Senior New Grad Program Engineer"))
        assert result.valid

    def test_safe_to_apply_fresh_role(self):
        result = is_safe_to_apply(_job(posted_days_ago=10))
        assert result.valid

    def test_safe_to_apply_stale_role(self):
        result = is_safe_to_apply(_job(posted_days_ago=120), staleness_threshold_days=90)
        assert not result.valid
        assert any("stale_role" in c for c in result.reason_codes)

    def test_safe_to_apply_senior_blocked(self):
        result = is_safe_to_apply(_job(title="Principal Engineer"))
        assert not result.valid
        assert "senior_role" in result.reason_codes

    def test_entry_level_score_new_grad(self):
        assert entry_level_score(_job(title="Software Engineer, New Grad")) >= 0.8

    def test_entry_level_score_intern(self):
        assert entry_level_score(_job(title="SWE Intern Summer 2026")) >= 0.8

    def test_entry_level_score_senior(self):
        assert entry_level_score(_job(title="Senior Staff Engineer")) < 0.2

    def test_entry_level_score_unlabeled(self):
        score = entry_level_score(_job(title="Software Engineer"))
        assert 0.3 <= score <= 0.7


# ---------------------------------------------------------------------------
# Article signal validator
# ---------------------------------------------------------------------------

class TestArticleSignalValidator:
    SOURCE = "This article discusses Go runtime tuning and hiring for new grads in 2026."

    def test_valid_technical_signal(self):
        signal = {
            "signal_type": "technical_signal",
            "summary": "Go runtime optimization at scale.",
            "application_angle": "Emphasize Go experience.",
            "interview_question": "How does Go manage goroutines?",
            "confidence": 0.85,
        }
        assert is_valid_article_signal(signal, self.SOURCE).valid

    def test_unknown_signal_type_invalid(self):
        signal = {"signal_type": "made_up_type", "confidence": 0.5}
        result = is_valid_article_signal(signal, self.SOURCE)
        assert not result.valid
        assert any("unknown_signal_type" in c for c in result.reason_codes)

    def test_zero_confidence_invalid(self):
        signal = {
            "signal_type": "technical_signal",
            "summary": "x",
            "application_angle": "y",
            "interview_question": "z",
            "confidence": 0.0,
        }
        result = is_valid_article_signal(signal, self.SOURCE)
        assert not result.valid
        assert "zero_confidence" in result.reason_codes

    def test_irrelevant_skips_angle_check(self):
        signal = {"signal_type": "irrelevant", "confidence": 0.9}
        assert is_valid_article_signal(signal, self.SOURCE).valid

    def test_missing_summary_invalid(self):
        signal = {
            "signal_type": "hiring_signal",
            "summary": "",
            "application_angle": "Apply now.",
            "interview_question": "Why us?",
            "confidence": 0.7,
        }
        result = is_valid_article_signal(signal, self.SOURCE)
        assert not result.valid
        assert "missing_summary" in result.reason_codes

    def test_missing_interview_question_invalid(self):
        signal = {
            "signal_type": "culture_signal",
            "summary": "Great culture.",
            "application_angle": "Emphasize ownership.",
            "interview_question": "",
            "confidence": 0.6,
        }
        result = is_valid_article_signal(signal, self.SOURCE)
        assert not result.valid
        assert "missing_interview_question" in result.reason_codes


# ---------------------------------------------------------------------------
# Recommendation validators
# ---------------------------------------------------------------------------

class TestRecommendationValidator:
    PROFILE = {"skills": ["Python", "Go", "algorithms"]}

    def test_valid_apply_recommendation(self):
        rec = {
            "action": "apply",
            "sources": ["https://co.com/jobs/1"],
            "entry_level_score": 0.9,
            "claimed_skills": ["Python", "Go"],
            "source_count": 1,
        }
        assert is_valid_recommendation(rec, self.PROFILE).valid

    def test_missing_source_invalid(self):
        rec = {"action": "apply", "sources": [], "entry_level_score": 0.9}
        result = is_valid_recommendation(rec, self.PROFILE)
        assert not result.valid
        assert "missing_source_citation" in result.reason_codes

    def test_senior_role_apply_blocked(self):
        rec = {
            "action": "apply",
            "sources": ["https://co.com/jobs/1"],
            "entry_level_score": 0.1,
            "claimed_skills": [],
        }
        result = is_valid_recommendation(rec, self.PROFILE)
        assert not result.valid
        assert "senior_only_role" in result.reason_codes

    def test_fabricated_skill_blocked(self):
        rec = {
            "action": "apply",
            "sources": ["https://co.com/jobs/1"],
            "entry_level_score": 0.8,
            "claimed_skills": ["Kubernetes", "Terraform"],  # not in profile
        }
        result = is_valid_recommendation(rec, self.PROFILE)
        assert not result.valid
        assert any("skills_not_in_profile" in c for c in result.reason_codes)

    def test_outreach_without_approval_blocked(self):
        rec = {
            "action": "outreach",
            "sources": ["https://linkedin.com/in/person"],
            "entry_level_score": 0.8,
            "claimed_skills": [],
            "approval_status": "pending",
        }
        result = is_valid_recommendation(rec, self.PROFILE)
        assert not result.valid
        assert "external_action_without_approval" in result.reason_codes

    def test_outreach_with_approval_valid(self):
        rec = {
            "action": "outreach",
            "sources": ["https://linkedin.com/in/person"],
            "entry_level_score": 0.8,
            "claimed_skills": [],
            "approval_status": "approved",
        }
        assert is_valid_recommendation(rec, self.PROFILE).valid

    def test_safe_recommendation_valid(self):
        rec = {"source_count": 2, "action": "apply", "referral_check_completed": True}
        assert is_safe_application_recommendation(rec).valid

    def test_safe_recommendation_no_sources(self):
        result = is_safe_application_recommendation({"source_count": 0, "action": "apply"})
        assert not result.valid
        assert "no_sources" in result.reason_codes


# ---------------------------------------------------------------------------
# Application packet validator
# ---------------------------------------------------------------------------

class TestApplicationPacketValidator:
    PROFILE = {
        "skills": ["Python", "Go", "algorithms"],
        "gpa": "3.8",
        "graduation_year": "2025",
        "degree": "BS Computer Science",
    }
    JOB = {"required_questions": ["why_us", "relevant_project"]}

    def test_valid_packet(self):
        packet = {
            "cover_letter": "I am excited to join because of your observability work. " * 3,
            "short_answers": {"why_us": "I love Go.", "relevant_project": "Built a metrics dashboard."},
            "unsupported_claims": [],
            "approval_status": "pending",
            "gpa": "3.8",
            "graduation_year": "2025",
        }
        result = is_valid_application_packet(packet, self.PROFILE, self.JOB)
        assert result.valid, result.reason_codes

    def test_unsupported_claims_blocked(self):
        packet = {
            "cover_letter": "I led a team of 10 engineers. " * 3,
            "short_answers": {"why_us": "x", "relevant_project": "y"},
            "unsupported_claims": ["led team of 10"],
            "approval_status": "pending",
        }
        result = is_valid_application_packet(packet, self.PROFILE, self.JOB)
        assert not result.valid
        assert any("unsupported_claims" in c for c in result.reason_codes)

    def test_auto_submit_always_blocked(self):
        packet = {
            "cover_letter": "Valid cover letter text here. " * 3,
            "short_answers": {"why_us": "x", "relevant_project": "y"},
            "unsupported_claims": [],
            "approval_status": "auto",
        }
        result = is_valid_application_packet(packet, self.PROFILE, self.JOB)
        assert not result.valid
        assert "auto_submit_forbidden" in result.reason_codes

    def test_altered_gpa_blocked(self):
        packet = {
            "cover_letter": "Good cover letter text goes here. " * 2,
            "short_answers": {"why_us": "x", "relevant_project": "y"},
            "unsupported_claims": [],
            "approval_status": "pending",
            "gpa": "3.9",  # actual is 3.8
        }
        result = is_valid_application_packet(packet, self.PROFILE, self.JOB)
        assert not result.valid
        assert "altered_gpa" in result.reason_codes

    def test_missing_required_answer_blocked(self):
        packet = {
            "cover_letter": "Solid cover letter content for testing purposes. " * 2,
            "short_answers": {"why_us": "x"},  # missing "relevant_project"
            "unsupported_claims": [],
            "approval_status": "pending",
        }
        result = is_valid_application_packet(packet, self.PROFILE, self.JOB)
        assert not result.valid
        assert any("missing_required_answers" in c for c in result.reason_codes)

    def test_claimed_kubernetes_not_in_profile_blocked(self):
        packet = {
            "cover_letter": "I have extensive kubernetes and terraform experience building microservices. " * 2,
            "short_answers": {"why_us": "x", "relevant_project": "y"},
            "unsupported_claims": [],
            "approval_status": "pending",
        }
        result = is_valid_application_packet(packet, self.PROFILE, self.JOB)
        assert not result.valid
        assert any("claimed_skill_not_in_profile" in c for c in result.reason_codes)

    def test_cover_letter_too_short(self):
        packet = {
            "cover_letter": "Hi.",
            "short_answers": {"why_us": "x", "relevant_project": "y"},
            "unsupported_claims": [],
            "approval_status": "pending",
        }
        result = is_valid_application_packet(packet, self.PROFILE, self.JOB)
        assert not result.valid
        assert "cover_letter_too_short" in result.reason_codes


# ---------------------------------------------------------------------------
# Browser action validator
# ---------------------------------------------------------------------------

class TestBrowserActionValidator:
    def test_open_page_always_allowed(self):
        action = {"type": "open_page", "target": "https://stripe.com/jobs"}
        assert is_allowed_browser_action(action, approval_status="pending").valid

    def test_take_screenshot_always_allowed(self):
        action = {"type": "take_screenshot"}
        assert is_allowed_browser_action(action, approval_status="pending").valid

    def test_submit_form_blocked_without_approval(self):
        action = {"type": "submit_form"}
        result = is_allowed_browser_action(action, approval_status="pending")
        assert not result.valid
        assert any("requires_approval" in c for c in result.reason_codes)

    def test_submit_form_allowed_with_approval(self):
        action = {"type": "submit_form"}
        assert is_allowed_browser_action(action, approval_status="approved").valid

    def test_upload_resume_blocked_without_approval(self):
        result = is_allowed_browser_action({"type": "upload_resume"}, approval_status="pending")
        assert not result.valid

    def test_send_message_blocked_without_approval(self):
        result = is_allowed_browser_action({"type": "send_message"}, approval_status="pending")
        assert not result.valid

    def test_create_account_blocked_without_approval(self):
        result = is_allowed_browser_action({"type": "create_account"}, approval_status="pending")
        assert not result.valid

    def test_bypass_captcha_always_blocked(self):
        result = is_allowed_browser_action({"type": "bypass_captcha"}, approval_status="approved")
        assert not result.valid
        assert any("always_forbidden" in c for c in result.reason_codes)

    def test_fake_answer_always_blocked(self):
        result = is_allowed_browser_action({"type": "fake_answer"}, approval_status="approved")
        assert not result.valid

    def test_safe_page_state_valid(self):
        state = {"url": "https://stripe.com/jobs/apply", "http_status": 200}
        assert is_safe_page_state(state).valid

    def test_server_error_page_invalid(self):
        state = {"url": "https://stripe.com/jobs/apply", "http_status": 500}
        result = is_safe_page_state(state)
        assert not result.valid
        assert any("server_error" in c for c in result.reason_codes)

    def test_non_https_blocked(self):
        state = {"url": "http://stripe.com/jobs/apply", "http_status": 200}
        result = is_safe_page_state(state)
        assert not result.valid
        assert "non_https_url" in result.reason_codes


# ---------------------------------------------------------------------------
# Retry wrapper
# ---------------------------------------------------------------------------

class TestRetryWrapper:
    def test_succeeds_first_try(self):
        def propose(**kwargs):
            return {"value": 42}

        def validate(result):
            return ValidationResult(valid=True)

        r = validate_with_retry(propose, validate)
        assert r.result["value"] == 42
        assert r.attempts == 1
        assert not r.routed_to_human

    def test_retries_on_failure_then_succeeds(self):
        call_count = {"n": 0}

        def propose(**kwargs):
            call_count["n"] += 1
            return {"attempt": call_count["n"]}

        def validate(result):
            return ValidationResult(valid=result["attempt"] >= 2)

        r = validate_with_retry(propose, validate, max_retries=1)
        assert r.result["attempt"] == 2
        assert r.attempts == 2
        assert not r.routed_to_human

    def test_routes_to_human_after_exhaustion(self):
        def propose(**kwargs):
            return {"bad": True}

        def validate(result):
            return ValidationResult(valid=False, reason_codes=["always_bad"])

        r = validate_with_retry(propose, validate, max_retries=2)
        assert r.routed_to_human
        assert r.attempts == 3  # initial + 2 retries

    def test_feedback_passed_to_propose(self):
        received_feedback = {"codes": None}

        def propose(**kwargs):
            received_feedback["codes"] = kwargs.get("feedback")
            return {"ok": kwargs.get("feedback") is not None}

        def validate(result):
            return ValidationResult(valid=result["ok"])

        r = validate_with_retry(propose, validate, max_retries=1)
        # Second call should have received feedback codes
        assert received_feedback["codes"] is not None
        assert not r.routed_to_human
