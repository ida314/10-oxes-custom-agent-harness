# tests/

174 tests covering all 11 phases. No live network calls. No Docker required. No API key required.

---

## Running tests

```bash
# Full suite
pytest tests/ -q

# Single file
pytest tests/test_validators.py -v

# By marker (if added)
pytest tests/ -k "not slow"
```

---

## Test files by system

### System 1 — Job-Search Intelligence

| File | What it tests | Count |
|------|--------------|-------|
| `test_ats_connectors.py` | Greenhouse, Lever, Ashby, careers page skills | 21 |
| `test_job_discovery_harness.py` | `run_company_scan` end-to-end | 8 |
| `test_article_discovery.py` | `score_articles` + eval runner | 15 |
| `test_application_packet.py` | Packet generation + validator | 20 |
| `test_browser_assistant.py` | Browser assist + approval gates | 18 |
| `test_validators.py` | All 6 validator modules | 53 |
| `test_trace_logger.py` | `TraceLogger` | 8 |

### Shared Infrastructure

| File | What it tests | Count |
|------|--------------|-------|
| `test_db_models.py` | SQLModel tables (SQLite in-memory) | 10 |

### System 2 — Harness Optimizer

| File | What it tests | Count |
|------|--------------|-------|
| `test_meta_harness.py` | Optimizer loop + Thompson sampling | 21 |

---

## Test infrastructure

**No Docker:** DB tests use SQLite in-memory via `sqlite:///:memory:`.

**No live network:** ATS connector tests use saved fixtures in `tests/fixtures/`.

**No API key:** All harnesses degrade to heuristic mode when `ANTHROPIC_API_KEY` is absent.

---

## Fixtures

```
tests/fixtures/
  greenhouse/datadog_jobs.json     ← Greenhouse API response
  lever/ramp_jobs.json             ← Lever API response
  ashby/linear_jobs.json           ← Ashby GraphQL response
  careers_page/stripe_careers.html ← Scraped careers page HTML
```

Add new fixture files here when writing new ATS or connector tests. Never use `requests` or `httpx` in tests without monkeypatching.

---

## Adding tests

- DB tests: use `engine = create_engine("sqlite:///:memory:")` in a fixture
- ATS tests: monkeypatch `httpx.get` or `httpx.post` to return fixture data
- Harness tests: use `HarnessConfig(dry_run=True)` to skip DB writes
- Validator tests: call `is_valid_*()` directly — they're pure functions
