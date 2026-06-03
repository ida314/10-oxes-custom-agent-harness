"""
Phase 11 tests — browser application assistant.
All tests use dry_run=True (no Playwright, no live network).
"""

import pytest
from pathlib import Path

from harnesses.browser_application.v0 import (
    run_browser_assist,
    BrowserConfig,
    BrowserAssistResult,
)

CFG_DRY = BrowserConfig(dry_run=True, approval_status="pending")
CFG_APPROVED = BrowserConfig(dry_run=True, approval_status="approved")

JOB = {
    "id": "job-001",
    "title": "Software Engineer, New Grad",
    "url": "https://stripe.com/jobs/listing/swe-newgrad-2026",
}

PACKET = {
    "candidate_name": "Dylan Doe",
    "candidate_email": "dylan@example.com",
    "cover_letter": "I am excited to apply to Stripe because of its API design excellence.",
    "linkedin_url": "https://linkedin.com/in/dylandoe",
    "approval_status": "pending",
}


@pytest.fixture
def result(tmp_path, monkeypatch):
    monkeypatch.setattr("harnesses.browser_application.v0.EXPERIMENTS_DIR", tmp_path)
    return run_browser_assist(JOB, PACKET, CFG_DRY)


class TestBrowserAssistant:

    def test_returns_result_type(self, result):
        assert isinstance(result, BrowserAssistResult)

    def test_dry_run_mode(self, result):
        assert result.mode == "dry_run"

    def test_fields_inspected(self, result):
        assert len(result.fields_found) >= 4  # mock fields: first, last, email, resume, cover, linkedin

    def test_fields_mapped_from_packet(self, result):
        assert result.fields_mapped > 0

    def test_submit_blocked_without_approval(self, result):
        blocked_types = [b["action"] for b in result.blocked_actions]
        assert "submit_form" in blocked_types

    def test_submit_allowed_with_approval(self, tmp_path, monkeypatch):
        monkeypatch.setattr("harnesses.browser_application.v0.EXPERIMENTS_DIR", tmp_path)
        r = run_browser_assist(JOB, PACKET, CFG_APPROVED)
        blocked_types = [b["action"] for b in r.blocked_actions]
        assert "submit_form" not in blocked_types

    def test_approval_handoff_created_when_blocked(self, result):
        assert result.approval_handoff is not None
        assert result.approval_handoff["action"] == "submit_form"
        assert "approval_status" in result.approval_handoff["requires"]

    def test_no_approval_handoff_when_approved(self, tmp_path, monkeypatch):
        monkeypatch.setattr("harnesses.browser_application.v0.EXPERIMENTS_DIR", tmp_path)
        r = run_browser_assist(JOB, PACKET, CFG_APPROVED)
        assert r.approval_handoff is None

    def test_screenshot_taken_in_dry_run(self, result):
        assert len(result.screenshots) >= 1
        ss_path = Path(result.screenshots[0])
        assert ss_path.exists()

    def test_open_page_always_in_actions(self, result):
        action_types = [a["type"] for a in result.actions_taken]
        assert "open_page" in action_types

    def test_fill_draft_local_always_in_actions(self, result):
        action_types = [a["type"] for a in result.actions_taken]
        assert "fill_draft_local" in action_types

    def test_trace_directory_created(self, result):
        trace_dir = Path(result.trace_dir)
        assert trace_dir.exists()
        assert (trace_dir / "output.json").exists()

    def test_missing_url_returns_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr("harnesses.browser_application.v0.EXPERIMENTS_DIR", tmp_path)
        job_no_url = {"id": "j1", "title": "SWE", "url": ""}
        r = run_browser_assist(job_no_url, PACKET, CFG_DRY)
        assert len(r.errors) >= 1
        assert "URL" in r.errors[0] or "url" in r.errors[0].lower()

    def test_first_name_mapped(self, result):
        first_name_fields = [f for f in result.fields_found if "first" in f.field_name.lower()]
        assert any(f.mapped_value == "Dylan" for f in first_name_fields)

    def test_cover_letter_mapped(self, result):
        cl_fields = [f for f in result.fields_found if "cover" in f.field_name.lower()]
        assert any(f.mapped_value is not None for f in cl_fields)

    def test_file_upload_not_mapped(self, result):
        file_fields = [f for f in result.fields_found if f.field_type == "file"]
        for f in file_fields:
            # File uploads require approval — value should not be auto-filled
            assert f.mapped_value is None or f.mapping_source == "requires_approval"


class TestBrowserActionValidatorIntegration:
    """Confirm browser_action validator gates work end-to-end through the harness."""

    def test_bypass_captcha_blocked_even_with_approval(self, tmp_path, monkeypatch):
        from harnesses.validators.browser_action import is_allowed_browser_action
        action = {"type": "bypass_captcha"}
        result = is_allowed_browser_action(action, approval_status="approved")
        assert not result.valid
        assert any("always_forbidden" in c for c in result.reason_codes)

    def test_inject_script_always_blocked(self):
        from harnesses.validators.browser_action import is_allowed_browser_action
        result = is_allowed_browser_action({"type": "inject_script"}, approval_status="approved")
        assert not result.valid
