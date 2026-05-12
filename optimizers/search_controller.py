"""
AutoHarness-style tree search controller with Thompson sampling (Phase 9).

Maintains candidate population, tracks metric history, selects candidates
for refinement using Thompson sampling over a Beta distribution.
"""

from __future__ import annotations

import random
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from optimizers.meta_harness_loop import (
    CandidateRecord,
    OptimizationState,
    METRIC_WEIGHTS,
    load_index,
    save_index,
    update_pareto_frontier,
    weighted_score,
)


# ---------------------------------------------------------------------------
# Thompson sampling
# ---------------------------------------------------------------------------


def _beta_sample(successes: int, failures: int) -> float:
    """Sample from Beta(alpha, beta) where alpha=successes+1, beta=failures+1."""
    return random.betavariate(successes + 1, failures + 1)


def _candidate_to_successes_failures(
    candidate: CandidateRecord,
    threshold: float = 0.5,
) -> tuple[int, int]:
    """
    Convert metric history to (successes, failures) for Thompson sampling.
    A 'success' is a metric run where weighted_score >= threshold.
    We use the weighted_score as a single proxy.
    """
    ws = candidate.weighted_score
    # Treat as a Bernoulli trial: success if ws >= threshold
    successes = 1 if ws >= threshold else 0
    failures = 1 - successes
    return successes, failures


def select_candidate_thompson(
    candidates: list[CandidateRecord],
    threshold: float = 0.5,
    rng_seed: int | None = None,
) -> CandidateRecord | None:
    """
    Select a candidate for refinement using Thompson sampling.
    Candidates with higher weighted_score are sampled more often,
    but exploration is preserved via Beta distribution variance.
    """
    if not candidates:
        return None

    if rng_seed is not None:
        random.seed(rng_seed)

    sampled_values: list[tuple[float, CandidateRecord]] = []
    for c in candidates:
        s, f = _candidate_to_successes_failures(c, threshold)
        sampled = _beta_sample(s, f)
        sampled_values.append((sampled, c))

    sampled_values.sort(key=lambda x: x[0], reverse=True)
    return sampled_values[0][1]


# ---------------------------------------------------------------------------
# Search controller state
# ---------------------------------------------------------------------------


class SearchControllerState(BaseModel):
    iteration: int = 0
    selection_history: list[dict] = []  # [{iteration, selected_id, sampled_value}]
    pareto_history: list[list[str]] = []  # pareto frontier at each iteration


class SearchController:
    """
    Wraps the optimization loop with Thompson sampling candidate selection.

    Usage:
        controller = SearchController()
        for _ in range(20):
            parent = controller.select_parent()
            candidate = controller.propose_and_evaluate(parent)
            controller.record(candidate)
    """

    def __init__(self, state: OptimizationState | None = None):
        self.opt_state = state or load_index()
        self.ctrl_state = SearchControllerState()

    def select_parent(self, threshold: float = 0.5) -> CandidateRecord | None:
        """Select the best candidate to refine, using Thompson sampling."""
        evaluated = [c for c in self.opt_state.candidates if c.search_scores]
        selected = select_candidate_thompson(evaluated, threshold)

        if selected:
            self.ctrl_state.selection_history.append({
                "iteration": self.ctrl_state.iteration,
                "selected_id": selected.id,
                "weighted_score": selected.weighted_score,
            })

        return selected

    def register_candidate(self, candidate: CandidateRecord) -> None:
        """Register a new candidate and update the Pareto frontier."""
        self.opt_state.candidates.append(candidate)
        self.opt_state.total_evaluated += 1
        update_pareto_frontier(self.opt_state)
        self.ctrl_state.pareto_history.append(list(self.opt_state.pareto_frontier))
        self.ctrl_state.iteration += 1
        save_index(self.opt_state)

    def pareto_frontier_candidates(self) -> list[CandidateRecord]:
        frontier_ids = set(self.opt_state.pareto_frontier)
        return [c for c in self.opt_state.candidates if c.id in frontier_ids]

    def best_candidate(self) -> CandidateRecord | None:
        if not self.opt_state.candidates:
            return None
        return max(self.opt_state.candidates, key=lambda c: c.weighted_score)

    def summary(self) -> dict[str, Any]:
        return {
            "total_candidates": len(self.opt_state.candidates),
            "total_evaluated": self.opt_state.total_evaluated,
            "pareto_frontier_size": len(self.opt_state.pareto_frontier),
            "best_weighted_score": self.best_candidate().weighted_score
            if self.best_candidate() else 0.0,
            "iterations": self.ctrl_state.iteration,
        }
