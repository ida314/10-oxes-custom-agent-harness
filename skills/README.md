# skills/

Executable, fixture-tested skill packages. Skills are reusable procedures extracted from harnesses — not prompt snippets.

---

## Skill protocol (`base.py`)

```python
class Skill(Protocol):
    name: str
    version: str

    def run(self, input: BaseModel, context: RunContext) -> SkillResult: ...

class SkillResult(BaseModel):
    success: bool
    items: list[Any]
    evidence: list[Evidence]
    confidence: float
    errors: list[str]
```

Every skill returns a typed `SkillResult` with source evidence. Callers check `result.success` and `result.confidence` before trusting the output.

---

## System 1 — Job-Search Intelligence skills

### `ats/` — ATS platform connectors

Deterministic HTTP + JSON connectors. No LLM calls, no browser automation.

| Skill | Platform | API type |
|-------|----------|----------|
| `ats/greenhouse/` | Greenhouse | Public JSON board API |
| `ats/lever/` | Lever | Public JSON postings API |
| `ats/ashby/` | Ashby | GraphQL jobs API |

See [ats/README.md](ats/README.md).

### `company_research/` — Web research skills

| Skill | What it finds |
|-------|--------------|
| `find_careers_page/` | Company's main careers/jobs URL |
| `find_engineering_blog/` | Engineering blog URL and recent post URLs |
| `find_events/` | Hackathons, info sessions, career fairs |
| `find_recent_articles/` | News, interviews, press mentions |

See [company_research/README.md](company_research/README.md).

---

## System 2 — Optimizer skill

### `meta_harness/`

Contains `propose_job_harness.md` — the skill definition used by the Meta-Harness proposer agent. Defines what the proposer reads, what it writes, and its exact write-permission constraints.

See [meta_harness/README.md](meta_harness/README.md).

---

## Skill lifecycle

1. Agent notices a repeated pattern or failure mode
2. Proposes a new skill with `skill.py`, `metadata.yaml`, `tests.py`, `examples.json`, `eval_history.jsonl`
3. Skill runs against eval examples
4. If metrics improve: mark `status: active` in `metadata.yaml`
5. Otherwise: keep `status: experimental` or mark `status: rejected`

Skills only graduate to `active` after passing evals. Active skills may replace LLM calls for stable, well-understood tasks.

---

## Adding a new skill

```
skills/{domain}/{skill_name}/
  skill.py           — implements Skill protocol
  metadata.yaml      — name, version, inputs, outputs, status, failure_modes, eval_metrics
  tests.py           — at least 3 tests using saved fixtures (no live network)
  examples.json      — 3–5 input/output pairs
  eval_history.jsonl — one row per eval run
  __init__.py
```
