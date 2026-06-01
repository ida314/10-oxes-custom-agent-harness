"""
Browser application assistant harness v0.

run_browser_assist(job, packet, config) -> BrowserAssistResult

Allowed automatically (no approval needed):
  open_page, read_page, take_screenshot, inspect_form,
  classify_fields, fill_draft_local, scroll, hover

Requires approval (approval_status == "approved"):
  submit_form, click_submit, send_message, upload_resume,
  upload_file, create_account, register, sign_up, final_submit, apply_now

Always forbidden:
  bypass_captcha, fake_answer, inject_script, modify_dom, impersonate

All dry-run actions produce screenshots and field-mapping reports.
Playwright is optional — degrades to mock mode if not installed.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from harnesses.validators.browser_action import is_allowed_browser_action, is_safe_page_state
from app.tracing.logger import TraceLogger

EXPERIMENTS_DIR = Path(__file__).parents[2] / "experiments" / "runs"


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


class BrowserConfig(BaseModel):
    dry_run: bool = True           # always True until Phase 11 approval is wired
    approval_status: str = "pending"
    screenshot_dir: str | None = None
    timeout_ms: int = 10000
    headless: bool = True


class FieldMapping(BaseModel):
    field_name: str
    field_type: str   # text | textarea | select | file | checkbox | submit
    label: str | None = None
    required: bool = False
    mapped_value: str | None = None   # from packet
    mapping_source: str | None = None  # which packet field


class BrowserAssistResult(BaseModel):
    job_id: str
    job_url: str
    page_title: str | None = None
    fields_found: list[FieldMapping] = []
    fields_mapped: int = 0
    fields_unmapped: int = 0
    screenshots: list[str] = []
    actions_taken: list[dict] = []
    blocked_actions: list[dict] = []
    approval_handoff: dict | None = None
    mode: str = "dry_run"  # dry_run | live
    errors: list[str] = []
    trace_dir: str = ""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run_browser_assist(
    job: dict,
    packet: dict,
    config: BrowserConfig | None = None,
) -> BrowserAssistResult:
    cfg = config or BrowserConfig()
    started_at = datetime.utcnow()
    trace = TraceLogger(started_at, "browser_application", "v0",
                        base_dir=EXPERIMENTS_DIR)
    errors: list[str] = []

    job_url = job.get("url", "")
    job_id = job.get("id") or job_url or "unknown"

    trace.log("config", {
        "job_id": job_id, "job_url": job_url,
        "approval_status": cfg.approval_status,
        "dry_run": cfg.dry_run,
    })

    if not job_url:
        return BrowserAssistResult(
            job_id=job_id, job_url="",
            errors=["No job URL provided"],
            trace_dir=str(trace.run_dir),
        )

    # --- Step 1: Validate page state (simulated in dry_run) ---
    page_state = _get_page_state(job_url, cfg, errors, trace)
    page_val = is_safe_page_state(page_state)
    if not page_val.valid:
        trace.log("page_state_blocked", {"codes": page_val.reason_codes})
        return BrowserAssistResult(
            job_id=job_id, job_url=job_url,
            errors=[f"Page state invalid: {page_val.reason_codes}"],
            trace_dir=str(trace.run_dir),
        )

    # --- Step 2: Inspect and classify form fields ---
    fields = _inspect_form_fields(job_url, page_state, cfg, trace)
    trace.log("fields_found", [f.model_dump() for f in fields])

    # --- Step 3: Map packet values to fields ---
    mapped_fields, unmapped = _map_packet_to_fields(fields, packet)
    trace.log("field_mapping", {
        "mapped": len(mapped_fields), "unmapped": unmapped
    })

    # --- Step 4: Record actions (gate any external actions) ---
    actions_taken: list[dict] = []
    blocked_actions: list[dict] = []
    screenshots: list[str] = []

    # Always-allowed: open page, screenshot, fill draft
    _record_action(actions_taken, "open_page", {"url": job_url}, cfg.approval_status)
    _record_action(actions_taken, "take_screenshot", {}, cfg.approval_status)
    _record_action(actions_taken, "fill_draft_local", {"fields": len(mapped_fields)}, cfg.approval_status)

    # Screenshot
    ss_path = _take_screenshot(job_url, cfg, trace)
    if ss_path:
        screenshots.append(ss_path)

    # Final submit — check gate
    submit_action = {"type": "submit_form", "target": job_url}
    submit_val = is_allowed_browser_action(submit_action, page_state, cfg.approval_status)
    if submit_val.valid:
        _record_action(actions_taken, "submit_form", {"url": job_url}, cfg.approval_status)
    else:
        blocked_actions.append({
            "action": "submit_form",
            "reason": submit_val.reason_codes,
            "approval_needed": True,
        })

    # --- Step 5: Build approval handoff if submit was blocked ---
    approval_handoff = None
    if blocked_actions:
        approval_handoff = {
            "item_type": "browser_action",
            "action": "submit_form",
            "job_id": job_id,
            "job_url": job_url,
            "fields_ready": len(mapped_fields),
            "fields_unmapped": unmapped,
            "requires": "approval_status == 'approved'",
            "screenshots": screenshots,
            "created_at": datetime.utcnow().isoformat(),
        }

    result = BrowserAssistResult(
        job_id=job_id,
        job_url=job_url,
        page_title=page_state.get("title"),
        fields_found=mapped_fields,
        fields_mapped=len(mapped_fields),
        fields_unmapped=unmapped,
        screenshots=screenshots,
        actions_taken=actions_taken,
        blocked_actions=blocked_actions,
        approval_handoff=approval_handoff,
        mode="dry_run" if cfg.dry_run else "live",
        errors=errors,
        trace_dir=str(trace.run_dir),
    )

    trace.save_output(result.model_dump(mode="json"))
    return result


# ---------------------------------------------------------------------------
# Page interaction (Playwright or mock)
# ---------------------------------------------------------------------------


def _get_page_state(
    url: str, cfg: BrowserConfig, errors: list[str], trace: TraceLogger
) -> dict:
    if cfg.dry_run or not _playwright_available():
        # Mock page state for dry_run
        return {
            "url": url,
            "http_status": 200,
            "title": f"Apply - {url.split('/')[2] if '//' in url else url}",
        }
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=cfg.headless)
            page = browser.new_page()
            resp = page.goto(url, timeout=cfg.timeout_ms)
            title = page.title()
            status = resp.status if resp else 200
            browser.close()
            return {"url": url, "http_status": status, "title": title}
    except Exception as exc:
        errors.append(f"Page load error: {exc}")
        return {"url": url, "http_status": 0, "title": None}


def _inspect_form_fields(
    url: str, page_state: dict, cfg: BrowserConfig, trace: TraceLogger
) -> list[FieldMapping]:
    if cfg.dry_run or not _playwright_available():
        # Return mock form fields typical of an ATS application form
        return [
            FieldMapping(field_name="first_name", field_type="text", label="First Name", required=True),
            FieldMapping(field_name="last_name", field_type="text", label="Last Name", required=True),
            FieldMapping(field_name="email", field_type="text", label="Email", required=True),
            FieldMapping(field_name="resume", field_type="file", label="Resume (PDF)", required=True),
            FieldMapping(field_name="cover_letter", field_type="textarea", label="Cover Letter", required=False),
            FieldMapping(field_name="linkedin_url", field_type="text", label="LinkedIn URL", required=False),
        ]
    try:
        from playwright.sync_api import sync_playwright
        fields: list[FieldMapping] = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=cfg.headless)
            page = browser.new_page()
            page.goto(url, timeout=cfg.timeout_ms)
            inputs = page.query_selector_all("input, textarea, select")
            for inp in inputs:
                field_type = inp.get_attribute("type") or inp.tag_name.lower()
                name = inp.get_attribute("name") or inp.get_attribute("id") or ""
                label = inp.get_attribute("aria-label") or inp.get_attribute("placeholder") or name
                required = inp.get_attribute("required") is not None
                fields.append(FieldMapping(
                    field_name=name, field_type=field_type,
                    label=label, required=required,
                ))
            browser.close()
        return fields
    except Exception:
        return []


def _map_packet_to_fields(
    fields: list[FieldMapping], packet: dict,
) -> tuple[list[FieldMapping], int]:
    mapped: list[FieldMapping] = []
    unmapped = 0

    for f in fields:
        name_lower = f.field_name.lower()
        label_lower = (f.label or "").lower()

        if "first" in name_lower or "first" in label_lower:
            name_parts = (packet.get("candidate_name") or "").split()
            f.mapped_value = name_parts[0] if name_parts else None
            f.mapping_source = "candidate_name"
        elif "last" in name_lower or "last" in label_lower:
            name_parts = (packet.get("candidate_name") or "").split()
            f.mapped_value = name_parts[-1] if len(name_parts) > 1 else None
            f.mapping_source = "candidate_name"
        elif "email" in name_lower or "email" in label_lower:
            f.mapped_value = packet.get("candidate_email")
            f.mapping_source = "candidate_email"
        elif "cover" in name_lower or "cover" in label_lower:
            f.mapped_value = packet.get("cover_letter")
            f.mapping_source = "cover_letter"
        elif "linkedin" in name_lower or "linkedin" in label_lower:
            f.mapped_value = packet.get("linkedin_url")
            f.mapping_source = "linkedin_url"
        elif f.field_type == "file":
            # File uploads require approval — don't map value
            f.mapped_value = None
            f.mapping_source = "requires_approval"

        if f.mapped_value is None and f.required:
            unmapped += 1

        mapped.append(f)

    return mapped, unmapped


def _take_screenshot(url: str, cfg: BrowserConfig, trace: TraceLogger) -> str | None:
    ss_dir = trace.run_dir / "screenshots"
    ss_dir.mkdir(exist_ok=True)
    ss_path = str(ss_dir / f"page_{datetime.utcnow().strftime('%H%M%S')}.png")

    if cfg.dry_run or not _playwright_available():
        # Write a placeholder file in dry_run
        Path(ss_path).write_bytes(b"MOCK_SCREENSHOT")
        return ss_path

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=cfg.headless)
            page = browser.new_page()
            page.goto(url, timeout=cfg.timeout_ms)
            page.screenshot(path=ss_path)
            browser.close()
        return ss_path
    except Exception:
        return None


def _record_action(
    log: list[dict], action_type: str, data: dict, approval_status: str,
) -> None:
    log.append({
        "type": action_type,
        "data": data,
        "approval_status": approval_status,
        "timestamp": datetime.utcnow().isoformat(),
    })


def _playwright_available() -> bool:
    try:
        import playwright
        return True
    except ImportError:
        return False
