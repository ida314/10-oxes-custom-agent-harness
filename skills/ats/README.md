# skills/ats/

**System 1.** Deterministic HTTP connectors for Applicant Tracking System platforms.

No LLM calls. No browser automation. HTTP + JSON parsing only.

---

## Connectors

| Skill | Platform | How it works |
|-------|----------|-------------|
| `greenhouse/` | Greenhouse | `GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs` |
| `lever/` | Lever | `GET https://api.lever.co/v0/postings/{company}?mode=json` |
| `ashby/` | Ashby | GraphQL `jobPostings` query against `api.ashbyhq.com` |

---

## Usage

```python
from skills.ats.greenhouse.skill import GreenhouseSkill
from skills.base import RunContext

skill = GreenhouseSkill()
result = skill.run({"company_name": "Datadog", "board_token": "datadog"}, RunContext())

for job in result.items:
    print(job.title, job.url, job.location)
```

All three skills return `list[NormalizedJob]` in `result.items`.

---

## NormalizedJob fields

```python
class NormalizedJob(BaseModel):
    title: str
    url: str           # UNIQUE — deduplication key
    location: str | None
    description_text: str
    source_type: str   # "greenhouse" | "lever" | "ashby"
    discovered_at: datetime
    posted_at: datetime | None
    normalized_hash: str   # UNIQUE — content-based dedup key
```

---

## Tests

All tests use saved HTTP fixtures in `tests/fixtures/` — no live network calls.

```bash
pytest tests/test_ats_connectors.py -v
```

Fixture files:
- `tests/fixtures/greenhouse/datadog_jobs.json`
- `tests/fixtures/lever/ramp_jobs.json`
- `tests/fixtures/ashby/linear_jobs.json`
- `tests/fixtures/careers_page/stripe_careers.html`

---

## Adding a new ATS connector

1. Create `skills/ats/{platform}/skill.py` implementing the `Skill` protocol
2. Add `metadata.yaml` with `status: experimental`
3. Save a fixture response in `tests/fixtures/{platform}/`
4. Add at least 3 tests to `tests/test_ats_connectors.py`
5. Add `examples.json` and `eval_history.jsonl`
