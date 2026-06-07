# harnesses/browser_application/

**System 1.** Assisted (not autonomous) browser form filling. Dry-run by default.

---

## Entry point

```python
from harnesses.browser_application.v0 import run_browser_assist, BrowserConfig

config = BrowserConfig(dry_run=True)   # default: dry-run only
result = run_browser_assist(packet, job_url, config)
# result: BrowserAssistResult
```

## What it does automatically (no approval needed)

- Open page and read field structure
- Classify form fields (text, textarea, select, file, submit)
- Map packet fields to form fields
- Draft values for each field
- Fill a local form draft (in-memory only)
- Take a screenshot

## What requires `approval_status == "approved"`

- Submit application
- Upload resume or any file
- Send a message
- Create an account

Attempts to do any of the above without approval raise a `PermissionError` and create an `ApprovalItem` row.

## Hard blocks (always forbidden, no approval path)

- `bypass_captcha`
- `fake_answer`

## Playwright dependency

Playwright is optional. Install it for live browser automation:

```bash
uv pip install playwright
playwright install chromium
```

Without Playwright, the harness runs in `dry_run` mode using mock page state and placeholder screenshots.

## Trace output

Each run creates:
```
experiments/runs/{ts}_browser_application_v0/
  screenshots/
    000_initial_page.png
    001_filled_form.png
  field_mapping.json
  output.json
```
