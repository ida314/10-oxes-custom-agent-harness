"""
Browser action validator (pure Python, no LLM).

is_allowed_browser_action() enforces hard gates:
- Submit / send / upload / create-account require approval_status == "approved"
- Bypass / fake-answer are always blocked
"""

from __future__ import annotations
from .base import ValidationResult

# Actions that require explicit human approval before execution
_APPROVAL_REQUIRED = {
    "submit_form",
    "click_submit",
    "send_message",
    "upload_resume",
    "upload_file",
    "create_account",
    "register",
    "sign_up",
    "final_submit",
    "apply_now",
}

# Actions that are always forbidden regardless of approval
_ALWAYS_FORBIDDEN = {
    "bypass_captcha",
    "fake_answer",
    "inject_script",
    "modify_dom",
    "impersonate",
    "auto_fill_personal_data_without_review",
}

# Actions always allowed without approval
_ALWAYS_ALLOWED = {
    "open_page",
    "read_page",
    "take_screenshot",
    "inspect_form",
    "classify_fields",
    "fill_draft_local",
    "scroll",
    "hover",
}


def is_allowed_browser_action(
    action: dict,
    page_state: dict | None = None,
    approval_status: str = "pending",
) -> ValidationResult:
    """
    Returns ValidationResult.valid=True only if the action is permitted.

    action dict must have:
      - type: str  (one of the action types above)
      - target: str | None  (CSS selector or URL)
      - value: str | None  (text to fill, etc.)
    """
    codes: list[str] = []
    action_type = (action.get("type") or "").lower().replace("-", "_").replace(" ", "_")

    if action_type in _ALWAYS_FORBIDDEN:
        codes.append(f"always_forbidden:{action_type}")
        return ValidationResult(valid=False, reason_codes=codes,
                                details=f"{action_type} is never permitted")

    if action_type in _APPROVAL_REQUIRED:
        if approval_status != "approved":
            codes.append(f"requires_approval:{action_type}")
            return ValidationResult(
                valid=False,
                reason_codes=codes,
                details=f"{action_type} requires approval_status='approved', got '{approval_status}'",
            )

    if action_type in _ALWAYS_ALLOWED:
        return ValidationResult(valid=True)

    # Unknown action types are allowed but flagged for review
    if action_type not in (_APPROVAL_REQUIRED | _ALWAYS_ALLOWED | _ALWAYS_FORBIDDEN):
        codes.append(f"unknown_action_type:{action_type}")
        # Allow but note — human reviewer should classify it
        return ValidationResult(valid=True, reason_codes=codes,
                                details=f"Unknown action type '{action_type}' — review recommended")

    return ValidationResult(valid=True, reason_codes=codes)


def is_safe_page_state(page_state: dict) -> ValidationResult:
    """
    Sanity check on the browser page state before any action.
    Blocks actions on unexpected domains or error pages.
    """
    codes: list[str] = []
    url = page_state.get("url", "")
    status = page_state.get("http_status", 200)

    if status >= 500:
        codes.append(f"server_error_page:{status}")
    if status == 404:
        codes.append("page_not_found")

    # Block if the page is not an HTTPS application page
    if url and not url.startswith("https://"):
        codes.append("non_https_url")

    return ValidationResult(valid=len(codes) == 0, reason_codes=codes)
