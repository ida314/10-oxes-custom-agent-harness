# harnesses/validators/

Pure-Python validators for every LLM-generated output type. No LLM calls. No side effects.

**System 1 component.** Every harness output passes through a validator before being saved or acted on.

---

## Pattern

```python
from harnesses.validators.retry import validate_with_retry

result = validate_with_retry(
    propose_fn=lambda: call_llm(prompt),
    validator_fn=is_valid_recommendation,
    max_retries=2,
)
# result is None if exhausted — routed to human review by caller
```

---

## Files

### `base.py`
`ValidationResult(valid, reason_codes, details)` + `merge(*results)`.

### `job.py`
- `is_valid_job(job)` — requires source URL; blocks jobs missing descriptions
- `is_safe_to_apply(job)` — blocks stale postings (>90 days) and senior-only titles
- `entry_level_score(job)` — heuristic 0–1 score based on title keywords

### `article_signal.py`
- `is_valid_article_signal(signal)` — requires evidence grounded in source text; blocks invented claims

### `recommendation.py`
- `is_valid_recommendation(rec, profile)` — blocks recommendations for inaccessible or skill-mismatched roles
- `is_safe_application_recommendation(rec, job)` — blocks apply recommendations for stale or senior roles

### `application_packet.py`
- `is_valid_application_packet(packet, profile)` — blocks:
  - altered employer names, dates, or GPA
  - skill claims not present in `profile.skills`
  - missing source URLs for company-specific claims

### `browser_action.py`
- `is_allowed_browser_action(action, approval_status)` — blocks submit/send/upload/create_account without `approval_status == "approved"`; always blocks `bypass_captcha` and `fake_answer`
- `is_safe_page_state(page_state)` — detects payment pages, sensitive forms

### `retry.py`
- `validate_with_retry(propose_fn, validator_fn, max_retries=2)` — appends validation failures to next prompt; returns `None` after exhaustion
