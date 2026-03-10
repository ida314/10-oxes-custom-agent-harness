# CLAUDE.md — Career Agent Harness System

## Project Mission

Build a **evaluated, traceable career-intelligence harness** that:
1. Monitors target companies, discovers entry-level software roles, surfaces company intelligence, and produces ranked, validated recommendations.
2. Continuously improves itself through a Meta-Harness optimizer that reads raw execution traces, proposes better harness candidates, and validates them against eval sets.

This is not an autonomous job applier. It is an instrumented, human-approved intelligence system.

---

## MANDATORY: Read These First

Before starting any work in a new session:

```
1. Read docs/STATE.md    — current phase, what exists, what doesn't
2. Read TODO.md          — next active tasks and checkboxes
```

After completing meaningful changes:

```
1. Update docs/STATE.md  — reflect new files, new status, known issues
2. Update TODO.md        — check off completed tasks, add new ones
```

---

## Non-Negotiable Build Order

```
Phase 0  (PARTIALLY DONE) — Eval benchmark: datasets + metrics
Phase 1  — Postgres data layer: models, migrations, seed, tests
Phase 2  — Deterministic source connectors + skill library v0
Phase 3  — Job-discovery harness v0 with validators
Phase 4  — Article/company-intelligence scoring harness v0
Phase 5  — Trace filesystem + experiment logging system
Phase 6  — Evaluation runners (search set / held-out split)
Phase 7  — AutoHarness-style validators for all domains
Phase 8  — Meta-Harness optimizer loop v0
Phase 9  — AutoHarness tree search + Thompson sampling
Phase 10 — Application packet generation (no auto-submit)
Phase 11 — Browser assistant with hard approval gates
```

**Do not skip phases. Do not build Phase 3+ before Phase 1 and 2 exist.**

---

## Key Architecture Principles

1. **LLMs propose; code validates; evals decide; humans approve external actions.**
2. **Postgres is source of truth for structured state. Filesystem is source of truth for raw traces.**
3. **Never store only summaries. Keep full prompts, model outputs, tool calls, and parser/validator results.**
4. **Separate proposal from verification.** Every LLM-generated output goes through a typed Python validator before being acted on.
5. **Skill library = executable code, not prompt snippets.** Every skill has tests, metadata, examples, and eval history.
6. **Search set and held-out test set are strictly separated.** The optimizer may never see test-set scores during search.
7. **Meta-Harness write access is restricted.** The proposer agent may only write to `harnesses/*/candidates/`, `notes/`, and `skills/meta_harness/`.

---

## Safety Constraints

- **No auto-apply, auto-submit, or auto-send** until Phase 11, and even then only with `approval_status == "approved"`.
- **No browser form submission, file upload, or account creation** unless explicitly approved.
- **No fabricated experience, altered dates/GPA/employer names** in application packets.
- **No validator bypass.** If a validator rejects output, route to human review — do not retry indefinitely.
- **No optimizer access to eval datasets or production harness code.**

---

## Repo Conventions

- Python 3.12, SQLModel or SQLAlchemy, Alembic, Pydantic v2, pytest.
- All harnesses live under `harnesses/{domain}/`. Production harnesses are versioned (v0.py, v1.py). Candidates go under `harnesses/{domain}/candidates/`.
- All skills live under `skills/{domain}/{skill_name}/` with `skill.py`, `metadata.yaml`, `tests.py`, `examples.json`, `eval_history.jsonl`.
- All experiments go under `experiments/runs/{timestamp}_{harness}_{version}/`.
- Docker Compose for local Postgres.
- `scripts/` for one-off and operational scripts.
- `prompts/` for prompt templates (never inline long prompts in Python).

---

## Detailed Docs

| File | Purpose |
|---|---|
| @docs/PROJECT_BRIEF.md | Full product brief, two-system description, what not to do |
| @docs/ARCHITECTURE.md | Repo structure, DB schema, skill library, trace FS, eval runner, Meta-Harness |
| @docs/BUILD_PLAN.md | Phase 0–11 deliverables, acceptance criteria, 6-week plan |
| @docs/DECISIONS.md | ADR-style log of architectural decisions |
| @docs/STATE.md | Current project state, what exists, next task |
| @TODO.md | Actionable phase-by-phase checklist |
