# Project Brief — Career Agent Harness System

## What This System Is

A **two-system harness-engineering platform** that:

1. **Job-search intelligence harness**: finds entry-level software jobs, company events, engineering blog articles, company intelligence signals, and referral opportunities — then produces ranked, validated, human-approvable recommendations.

2. **Coding-agent / harness-optimizer system**: improves the first system (and later general coding-agent workflows) through measured harness search guided by raw execution traces, eval metrics, and a Pareto frontier.

The key product property: every recommendation is backed by a source, validated by Python code, and logged with full traces. The agent does not take external actions without human approval.

---

## The Two Systems

### System 1 — Job-Search Intelligence Harness

**Inputs:** target company list, candidate profile (skills, experience, preferences)

**Outputs:**
- Discovered entry-level jobs with source links, freshness, and fit scores
- Company intelligence signals classified by type (hiring, technical, culture, strategy, interview prep, networking, risk)
- Application angles: how to use each signal in a resume/cover letter/outreach/interview
- Ranked, validated recommendations (apply, research further, outreach, skip)
- Application packet drafts (resume tailoring, cover letter, short answers, referral request, interview notes)
- Approval queue items for any external action

**Does NOT do (yet):**
- Auto-apply or browser form submission without approval
- Real-time push notifications
- Resume PDF generation

### System 2 — Coding-Agent / Harness Optimizer

**Inputs:** harness candidate files, eval dataset (search set only), raw execution traces

**Outputs:**
- Improved harness candidates under `harnesses/*/candidates/`
- Pareto frontier over multiple metrics (recall, precision, safety, context tokens, runtime)
- Notes explaining what changed and why
- New skills proposed for the skill library

**Does NOT do:**
- Modify eval datasets
- Access held-out test scores
- Modify production harnesses directly
- Push to external systems

---

## Core Design Ideas (From the Papers)

### AutoHarness Idea
Learn small executable control logic (validators/verifiers) that prevent bad actions. For each domain: `propose_X()` (LLM) → `is_valid_X()` (Python) → retry or route to human. AutoHarness showed that LLMs can reason well but still take illegal/unsafe actions; the fix is an external verifiable code layer around outputs. Applied here to: job filtering, article signal classification, recommendation generation, application packet content, browser action control.

### Meta-Harness Idea
Keep every harness candidate, score, execution trace, prompt, tool call, and failure in a filesystem + database. Let a coding-agent proposer inspect the full history (not summaries) and propose better harness code. The raw traces are what enable diagnosis of failures. Loop: evaluate → store logs → proposer inspects → proposes candidate → evaluate → repeat. Pareto frontier tracks multiple objectives simultaneously.

### Voyager-Style Skill Library
Whenever the agent discovers a reusable procedure, store it as an executable skill package with metadata, tests, examples, and eval history. Skills graduate from `experimental` to `active` only after passing eval. Skills can eventually replace LLM calls for stable, well-understood tasks.

---

## Minimal First Milestone

**Given 10 target companies, run one command overnight and produce:**
- New relevant entry-level jobs with source links
- Useful articles/interviews/events with application angles
- Ranked recommendations with validation status
- Full traces for every decision
- Approval queue items (no auto-submit)

```bash
python scripts/run_company_scans.py \
  --company-list target_companies.yaml \
  --profile profiles/user.yaml
```

**Output locations:**
- `experiments/runs/{timestamp}/` — full traces
- Postgres tables — structured records
- `dashboard/` — daily digest (future)
- `approval_items` table — human review queue

---

## What NOT To Do

- Do not start with "build me an autonomous agent that applies to jobs." That creates a brittle demo.
- Do not build the self-improving loop before instrumentation and evals exist. Self-improvement without evals optimizes noise.
- Do not give the optimizer write access to the full repo. It writes only to `harnesses/*/candidates/`.
- Do not store only summaries. Raw traces enable failure diagnosis.
- Do not build browser automation (Phase 11) before application packet generation (Phase 10) works.
- Do not build Phase 3+ before the data layer (Phase 1) and connectors (Phase 2) exist.
- Do not use LangChain memory as real memory. Real memory is Postgres + trace filesystem.
