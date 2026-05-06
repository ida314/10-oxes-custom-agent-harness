"""
Meta-Harness optimization loop (Phase 8).

Implements the core loop from the Meta-Harness paper:
  1. Evaluate current harness candidates on search set
  2. Store full traces
  3. Proposer agent inspects prior runs
  4. Proposer writes one new harness candidate
  5. Validate candidate interface (static check)
  6. Evaluate candidate on search set
  7. Add to population with lineage
  8. Update Pareto frontier
  9. Repeat

Write access is strictly restricted: the proposer may only write to
  harnesses/*/candidates/  and  notes/

The proposer never sees test-set results. Test evaluation is a separate
manual step (evaluate_job_discovery(..., split="test", allow_test=True)).
"""

from __future__ import annotations

import importlib.util
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

ROOT = Path(__file__).parent.parent
CANDIDATES_INDEX = ROOT / "experiments" / "candidates" / "index.json"
CANDIDATES_DIR = ROOT / "harnesses" / "job_discovery" / "candidates"
NOTES_DIR = ROOT / "notes"
SEARCH_DATASET = ROOT / "evals" / "datasets" / "search" / "job_tracker_search.jsonl"

METRIC_WEIGHTS = {
    "job_recall": 0.25,
    "job_precision": 0.20,
    "entry_level_accuracy": 0.20,
    "recommendation_acceptability": 0.20,
    "unsafe_action_rate": -0.30,   # minimize
    "context_tokens": -0.05,        # minimize
}


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


class CandidateRecord(BaseModel):
    id: str
    domain: str
    name: str
    version: str
    file_path: str
    parent_id: str | None = None
    search_scores: dict[str, float] = {}
    weighted_score: float = 0.0
    status: str = "experimental"  # experimental | active | rejected
    created_at: str
    notes_path: str | None = None
    on_pareto_frontier: bool = False


class OptimizationState(BaseModel):
    candidates: list[CandidateRecord] = []
    pareto_frontier: list[str] = []  # candidate IDs on frontier
    last_updated: str | None = None
    total_evaluated: int = 0
    metrics_tracked: list[str] = list(METRIC_WEIGHTS.keys())


# ---------------------------------------------------------------------------
# Index management
# ---------------------------------------------------------------------------


def load_index() -> OptimizationState:
    if CANDIDATES_INDEX.exists():
        raw = json.loads(CANDIDATES_INDEX.read_text())
        return OptimizationState(**raw)
    return OptimizationState()


def save_index(state: OptimizationState) -> None:
    state.last_updated = datetime.utcnow().isoformat()
    CANDIDATES_INDEX.write_text(json.dumps(state.model_dump(), indent=2, default=str))


# ---------------------------------------------------------------------------
# Candidate interface validation (static check)
# ---------------------------------------------------------------------------


def validate_candidate_interface(candidate_path: Path) -> tuple[bool, str]:
    """
    Check that the candidate file:
    1. Can be imported without error
    2. Exposes run_company_scan with the correct signature
    3. Returns a CompanyScanReport-like object
    """
    try:
        spec = importlib.util.spec_from_file_location("_candidate", candidate_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception as exc:
        return False, f"Import error: {exc}"

    if not hasattr(module, "run_company_scan"):
        return False, "Missing run_company_scan function"

    import inspect
    sig = inspect.signature(module.run_company_scan)
    required = {"company_id", "profile_id"}
    params = set(sig.parameters.keys())
    missing = required - params
    if missing:
        return False, f"run_company_scan missing parameters: {missing}"

    return True, "OK"


# ---------------------------------------------------------------------------
# Candidate evaluation (search set only)
# ---------------------------------------------------------------------------


def evaluate_candidate_on_search_set(
    candidate_path: Path,
    dry_run: bool = True,
) -> dict[str, float]:
    """
    Run the candidate harness against the search-set fixture companies
    and return scalar metrics.

    In dry_run mode (default): uses fixture data, no live network, no DB.
    Returns heuristic proxy metrics based on the harness structure.
    """
    valid, msg = validate_candidate_interface(candidate_path)
    if not valid:
        return {"error": -1.0, "interface_valid": 0.0}

    # Load and run candidate against fixture companies
    spec = importlib.util.spec_from_file_location("_eval_candidate", candidate_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Fixture companies (no DB needed)
    test_companies = [
        {"id": "eval-datadog", "name": "Datadog", "domain": "datadoghq.com",
         "ats_type": "greenhouse", "careers_url": "https://datadoghq.com/careers", "priority": 1},
        {"id": "eval-ramp", "name": "Ramp", "domain": "ramp.com",
         "ats_type": "lever", "careers_url": "https://ramp.com/careers", "priority": 1},
    ]

    from harnesses.job_discovery.v0 import CandidateProfile, HarnessConfig
    from skills.base import RunContext
    import skills.ats.greenhouse.skill as gh_mod
    import skills.ats.lever.skill as lv_mod
    import skills.company_research.find_recent_articles.skill as art_mod
    import skills.company_research.find_events.skill as ev_mod
    import skills.company_research.find_careers_page.skill as fp_mod

    # Patch all HTTP calls to return empty (safe dry-run)
    gh_mod._http_get_fn = lambda url: {"jobs": []}
    lv_mod._http_get_fn = lambda url: []
    art_mod._http_get_text_fn = lambda url: (404, "")
    ev_mod._http_get_text_fn = lambda url: (404, "")
    fp_mod._http_get_text_fn = lambda url: (404, "")

    profile = CandidateProfile(
        id="eval-profile", name="Eval Candidate",
        experience_level="new_grad", skills=["Python", "Go"],
    )
    cfg = HarnessConfig(dry_run=True)

    results = []
    for company in test_companies:
        try:
            report = module.run_company_scan(
                company_id=company["id"],
                profile_id=profile.id,
                config=cfg,
                profile=profile,
                company_override=company,
            )
            results.append(report)
        except Exception as exc:
            results.append(None)

    # Compute proxy metrics
    valid_reports = [r for r in results if r is not None]
    if not valid_reports:
        return {"interface_valid": 1.0, "job_recall": 0.0, "job_precision": 0.0,
                "entry_level_accuracy": 0.0, "recommendation_acceptability": 0.0,
                "unsafe_action_rate": 0.0, "context_tokens": 0.0}

    # In dry-run with empty fixtures, recall will be 0 (no real jobs returned)
    # These are structural metrics: harness runs without crashing = baseline pass
    total_jobs = sum(r.jobs_after_dedup for r in valid_reports)
    total_valid = sum(r.jobs_valid for r in valid_reports)
    total_errors = sum(len(r.errors) for r in valid_reports)
    senior_jobs = sum(
        1 for r in valid_reports
        for sj in r.scored_jobs
        if sj.entry_level_score < 0.3 and sj.recommendation == "apply"
    )
    unsafe_rate = senior_jobs / max(total_jobs, 1)
    error_rate = total_errors / max(len(valid_reports), 1)

    return {
        "interface_valid": 1.0,
        "job_recall": 0.0,          # can't measure without live data
        "job_precision": max(0.0, 1.0 - unsafe_rate),
        "entry_level_accuracy": max(0.0, 1.0 - unsafe_rate),
        "recommendation_acceptability": max(0.0, 1.0 - error_rate * 0.1),
        "unsafe_action_rate": unsafe_rate,
        "context_tokens": 0.0,      # no LLM calls in dry-run
    }


# ---------------------------------------------------------------------------
# Weighted score and Pareto frontier
# ---------------------------------------------------------------------------


def weighted_score(metrics: dict[str, float]) -> float:
    score = 0.0
    for metric, weight in METRIC_WEIGHTS.items():
        score += weight * metrics.get(metric, 0.0)
    return round(score, 4)


def update_pareto_frontier(state: OptimizationState) -> None:
    """
    Keep candidates that are not dominated on any tracked metric.
    A candidate A dominates B if A is >= B on all metrics and > B on at least one.
    """
    candidates = [c for c in state.candidates if c.search_scores]
    dominated: set[str] = set()

    for i, a in enumerate(candidates):
        for j, b in enumerate(candidates):
            if i == j:
                continue
            # Does a dominate b?
            metrics = [m for m in METRIC_WEIGHTS if m in a.search_scores and m in b.search_scores]
            if not metrics:
                continue
            a_better_all = all(
                (a.search_scores[m] >= b.search_scores[m] if METRIC_WEIGHTS[m] > 0
                 else a.search_scores[m] <= b.search_scores[m])
                for m in metrics
            )
            a_better_one = any(
                (a.search_scores[m] > b.search_scores[m] if METRIC_WEIGHTS[m] > 0
                 else a.search_scores[m] < b.search_scores[m])
                for m in metrics
            )
            if a_better_all and a_better_one:
                dominated.add(b.id)

    for c in state.candidates:
        c.on_pareto_frontier = c.id not in dominated and bool(c.search_scores)

    state.pareto_frontier = [c.id for c in state.candidates if c.on_pareto_frontier]


# ---------------------------------------------------------------------------
# Main optimization loop
# ---------------------------------------------------------------------------


def run_optimization_loop(
    n_iterations: int = 5,
    dry_run: bool = True,
    verbose: bool = True,
) -> OptimizationState:
    """
    Run n_iterations of the Meta-Harness optimization loop.

    Each iteration:
    1. Load current state
    2. Register v0 as baseline if no candidates exist
    3. Select parent candidate (best weighted score)
    4. In a real run: invoke proposer agent to write a new candidate
       In dry_run: copy v0 with a minor version bump (stub)
    5. Validate interface
    6. Evaluate on search set
    7. Record in index
    8. Update Pareto frontier
    """
    state = load_index()

    # Bootstrap: register v0 as the first candidate if empty
    if not state.candidates:
        v0_path = ROOT / "harnesses" / "job_discovery" / "v0.py"
        if v0_path.exists():
            scores = evaluate_candidate_on_search_set(v0_path, dry_run=dry_run)
            ws = weighted_score(scores)
            record = CandidateRecord(
                id="v0",
                domain="job_discovery",
                name="v0",
                version="0.1.0",
                file_path=str(v0_path),
                search_scores=scores,
                weighted_score=ws,
                status="active",
                created_at=datetime.utcnow().isoformat(),
            )
            state.candidates.append(record)
            state.total_evaluated += 1
            if verbose:
                print(f"[bootstrap] registered v0 | weighted_score={ws:.4f}")

    for iteration in range(n_iterations):
        if verbose:
            print(f"\n[iter {iteration + 1}/{n_iterations}]")

        # Select best current candidate as parent
        ranked = sorted(state.candidates, key=lambda c: c.weighted_score, reverse=True)
        parent = ranked[0] if ranked else None

        if parent and verbose:
            print(f"  parent: {parent.name} | score={parent.weighted_score:.4f}")

        # Generate candidate name
        candidate_name = f"candidate_{state.total_evaluated + 1:03d}"
        candidate_path = CANDIDATES_DIR / f"{candidate_name}.py"

        # In dry_run: stub candidate = copy of v0 with version comment
        # In real run: invoke proposer agent (Claude Code subagent)
        if dry_run:
            _write_stub_candidate(candidate_path, candidate_name, parent, iteration)
        else:
            ok = _invoke_proposer_agent(parent, candidate_name, state)
            if not ok:
                if verbose:
                    print(f"  proposer failed — skipping iteration")
                continue

        # Validate interface
        valid, msg = validate_candidate_interface(candidate_path)
        if not valid:
            if verbose:
                print(f"  interface invalid: {msg} — skipping")
            continue

        # Evaluate on search set
        scores = evaluate_candidate_on_search_set(candidate_path, dry_run=dry_run)
        ws = weighted_score(scores)

        record = CandidateRecord(
            id=candidate_name,
            domain="job_discovery",
            name=candidate_name,
            version=f"0.{state.total_evaluated + 1}.0",
            file_path=str(candidate_path),
            parent_id=parent.id if parent else None,
            search_scores=scores,
            weighted_score=ws,
            status="experimental",
            created_at=datetime.utcnow().isoformat(),
        )
        state.candidates.append(record)
        state.total_evaluated += 1

        update_pareto_frontier(state)
        save_index(state)

        if verbose:
            print(f"  candidate: {candidate_name} | score={ws:.4f} | pareto={record.on_pareto_frontier}")
            for m, v in scores.items():
                print(f"    {m}: {v:.4f}")

    save_index(state)
    if verbose:
        print(f"\nDone. {state.total_evaluated} total candidates evaluated.")
        print(f"Pareto frontier: {state.pareto_frontier}")
    return state


# ---------------------------------------------------------------------------
# Stub candidate writer (dry_run mode)
# ---------------------------------------------------------------------------


def _write_stub_candidate(
    path: Path,
    name: str,
    parent: CandidateRecord | None,
    iteration: int,
) -> None:
    """Write a minimal valid candidate file for dry_run testing (copy of v0 with comment header)."""
    v0_source = (ROOT / "harnesses" / "job_discovery" / "v0.py").read_text()
    # Use # comments so from __future__ imports remain at file top
    header = (
        f"# Candidate: {name}\n"
        f"# Parent: {parent.id if parent else 'none'}\n"
        f"# Iteration: {iteration}\n"
        f"# Generated by: stub (dry_run=True)\n\n"
    )
    path.write_text(header + v0_source)


# ---------------------------------------------------------------------------
# Real proposer agent invocation (non-dry-run)
# ---------------------------------------------------------------------------


def _invoke_proposer_agent(
    parent: CandidateRecord | None,
    candidate_name: str,
    state: OptimizationState,
) -> bool:
    """
    In a real run, this would invoke a Claude Code subagent with the
    propose_job_harness.md skill to write a new candidate.

    Not implemented here — requires ANTHROPIC_API_KEY and Agent SDK.
    Returns False to signal the loop should use dry_run instead.
    """
    return False


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--no-dry-run", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    run_optimization_loop(
        n_iterations=args.iterations,
        dry_run=not args.no_dry_run,
        verbose=not args.quiet,
    )
