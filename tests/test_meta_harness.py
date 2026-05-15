"""
Tests for Phase 8 (Meta-Harness loop) and Phase 9 (Thompson sampling search controller).
All tests run in dry_run mode — no live network, no DB, no LLM.
"""

import json
from pathlib import Path

import pytest

from optimizers.meta_harness_loop import (
    OptimizationState,
    CandidateRecord,
    validate_candidate_interface,
    weighted_score,
    update_pareto_frontier,
    run_optimization_loop,
    load_index,
    save_index,
    CANDIDATES_INDEX,
    CANDIDATES_DIR,
)
from optimizers.search_controller import (
    SearchController,
    select_candidate_thompson,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_candidate(id_: str, scores: dict[str, float]) -> CandidateRecord:
    from datetime import datetime
    return CandidateRecord(
        id=id_,
        domain="job_discovery",
        name=id_,
        version="0.1.0",
        file_path=f"harnesses/job_discovery/candidates/{id_}.py",
        search_scores=scores,
        weighted_score=weighted_score(scores),
        created_at=datetime.utcnow().isoformat(),
    )


def _good_scores() -> dict:
    return {
        "job_recall": 0.9, "job_precision": 0.85,
        "entry_level_accuracy": 0.88, "recommendation_acceptability": 0.80,
        "unsafe_action_rate": 0.02, "context_tokens": 0.1,
    }


def _bad_scores() -> dict:
    return {
        "job_recall": 0.3, "job_precision": 0.4,
        "entry_level_accuracy": 0.35, "recommendation_acceptability": 0.40,
        "unsafe_action_rate": 0.30, "context_tokens": 0.5,
    }


# ---------------------------------------------------------------------------
# Weighted score
# ---------------------------------------------------------------------------

class TestWeightedScore:
    def test_perfect_scores_positive(self):
        scores = _good_scores()
        ws = weighted_score(scores)
        assert ws > 0

    def test_high_unsafe_rate_penalizes(self):
        good = _good_scores()
        unsafe = {**good, "unsafe_action_rate": 0.9}
        assert weighted_score(unsafe) < weighted_score(good)

    def test_good_beats_bad(self):
        assert weighted_score(_good_scores()) > weighted_score(_bad_scores())

    def test_missing_metrics_default_zero(self):
        ws = weighted_score({"job_recall": 0.8})
        assert isinstance(ws, float)


# ---------------------------------------------------------------------------
# Pareto frontier
# ---------------------------------------------------------------------------

class TestParetoFrontier:
    def test_single_candidate_on_frontier(self):
        state = OptimizationState()
        state.candidates.append(_make_candidate("a", _good_scores()))
        update_pareto_frontier(state)
        assert "a" in state.pareto_frontier

    def test_dominated_candidate_not_on_frontier(self):
        state = OptimizationState()
        state.candidates.append(_make_candidate("good", _good_scores()))
        state.candidates.append(_make_candidate("bad", _bad_scores()))
        update_pareto_frontier(state)
        assert "good" in state.pareto_frontier
        assert "bad" not in state.pareto_frontier

    def test_incomparable_candidates_both_on_frontier(self):
        # A better on recall, B better on precision — incomparable → both on frontier
        state = OptimizationState()
        a_scores = {**_good_scores(), "job_recall": 1.0, "job_precision": 0.4}
        b_scores = {**_good_scores(), "job_recall": 0.4, "job_precision": 1.0}
        state.candidates.append(_make_candidate("a", a_scores))
        state.candidates.append(_make_candidate("b", b_scores))
        update_pareto_frontier(state)
        assert "a" in state.pareto_frontier
        assert "b" in state.pareto_frontier


# ---------------------------------------------------------------------------
# Candidate interface validation
# ---------------------------------------------------------------------------

class TestCandidateInterfaceValidation:
    def test_v0_passes_validation(self):
        v0_path = Path("harnesses/job_discovery/v0.py")
        if not v0_path.exists():
            pytest.skip("v0.py not found")
        valid, msg = validate_candidate_interface(v0_path)
        assert valid, msg

    def test_missing_function_fails(self, tmp_path):
        bad = tmp_path / "bad_candidate.py"
        bad.write_text("# no run_company_scan here\n")
        valid, msg = validate_candidate_interface(bad)
        assert not valid
        assert "Missing" in msg

    def test_syntax_error_fails(self, tmp_path):
        bad = tmp_path / "syntax_error.py"
        bad.write_text("def run_company_scan(: pass\n")
        valid, msg = validate_candidate_interface(bad)
        assert not valid


# ---------------------------------------------------------------------------
# Optimization loop (dry_run)
# ---------------------------------------------------------------------------

class TestOptimizationLoop:
    @pytest.fixture(autouse=True)
    def isolate_index(self, tmp_path, monkeypatch):
        # Redirect index and candidates to tmp_path
        import optimizers.meta_harness_loop as mod
        monkeypatch.setattr(mod, "CANDIDATES_INDEX", tmp_path / "index.json")
        monkeypatch.setattr(mod, "CANDIDATES_DIR", tmp_path / "candidates")
        (tmp_path / "candidates").mkdir()
        # Patch all HTTP to empty
        import skills.ats.greenhouse.skill as gh
        import skills.ats.lever.skill as lv
        import skills.company_research.find_recent_articles.skill as art
        import skills.company_research.find_events.skill as ev
        import skills.company_research.find_careers_page.skill as fp
        monkeypatch.setattr(gh, "_http_get_fn", lambda url: {"jobs": []})
        monkeypatch.setattr(lv, "_http_get_fn", lambda url: [])
        monkeypatch.setattr(art, "_http_get_text_fn", lambda url: (404, ""))
        monkeypatch.setattr(ev, "_http_get_text_fn", lambda url: (404, ""))
        monkeypatch.setattr(fp, "_http_get_text_fn", lambda url: (404, ""))

    def test_loop_runs_5_iterations(self, monkeypatch, tmp_path):
        import optimizers.meta_harness_loop as mod
        monkeypatch.setattr(mod, "CANDIDATES_INDEX", tmp_path / "index.json")
        monkeypatch.setattr(mod, "CANDIDATES_DIR", tmp_path / "candidates")
        (tmp_path / "candidates").mkdir(exist_ok=True)

        state = run_optimization_loop(n_iterations=5, dry_run=True, verbose=False)
        # v0 bootstrap + 5 iterations = 6 total
        assert state.total_evaluated >= 5

    def test_all_candidates_have_lineage(self, monkeypatch, tmp_path):
        import optimizers.meta_harness_loop as mod
        monkeypatch.setattr(mod, "CANDIDATES_INDEX", tmp_path / "index.json")
        monkeypatch.setattr(mod, "CANDIDATES_DIR", tmp_path / "candidates")
        (tmp_path / "candidates").mkdir(exist_ok=True)

        state = run_optimization_loop(n_iterations=3, dry_run=True, verbose=False)
        non_root = [c for c in state.candidates if c.id != "v0"]
        for c in non_root:
            assert c.parent_id is not None

    def test_pareto_frontier_nonempty(self, monkeypatch, tmp_path):
        import optimizers.meta_harness_loop as mod
        monkeypatch.setattr(mod, "CANDIDATES_INDEX", tmp_path / "index.json")
        monkeypatch.setattr(mod, "CANDIDATES_DIR", tmp_path / "candidates")
        (tmp_path / "candidates").mkdir(exist_ok=True)

        state = run_optimization_loop(n_iterations=3, dry_run=True, verbose=False)
        assert len(state.pareto_frontier) >= 1

    def test_index_json_written(self, monkeypatch, tmp_path):
        import optimizers.meta_harness_loop as mod
        idx = tmp_path / "index.json"
        monkeypatch.setattr(mod, "CANDIDATES_INDEX", idx)
        monkeypatch.setattr(mod, "CANDIDATES_DIR", tmp_path / "candidates")
        (tmp_path / "candidates").mkdir(exist_ok=True)

        run_optimization_loop(n_iterations=2, dry_run=True, verbose=False)
        assert idx.exists()
        data = json.loads(idx.read_text())
        assert data["total_evaluated"] >= 2


# ---------------------------------------------------------------------------
# Thompson sampling search controller
# ---------------------------------------------------------------------------

class TestSearchController:
    def test_select_with_one_candidate(self):
        c = _make_candidate("a", _good_scores())
        result = select_candidate_thompson([c], rng_seed=42)
        assert result.id == "a"

    def test_select_prefers_better_candidate_over_many_draws(self):
        good = _make_candidate("good", _good_scores())
        bad = _make_candidate("bad", _bad_scores())
        selections = [
            select_candidate_thompson([good, bad], rng_seed=i).id
            for i in range(50)
        ]
        good_count = selections.count("good")
        # Good should be selected majority of the time
        assert good_count > 25, f"Expected >25/50 good, got {good_count}"

    def test_controller_register_updates_total(self):
        state = OptimizationState()
        state.candidates.append(_make_candidate("v0", _good_scores()))
        ctrl = SearchController(state)

        new_c = _make_candidate("c1", _good_scores())
        ctrl.register_candidate(new_c)
        assert ctrl.opt_state.total_evaluated == 1

    def test_controller_pareto_frontier_populated(self):
        state = OptimizationState()
        c1 = _make_candidate("c1", _good_scores())
        state.candidates.append(c1)
        ctrl = SearchController(state)
        ctrl.register_candidate(_make_candidate("c2", _bad_scores()))
        frontier = ctrl.pareto_frontier_candidates()
        ids = {c.id for c in frontier}
        assert "c1" in ids

    def test_controller_summary_fields(self):
        state = OptimizationState()
        state.candidates.append(_make_candidate("v0", _good_scores()))
        ctrl = SearchController(state)
        s = ctrl.summary()
        assert "total_candidates" in s
        assert "pareto_frontier_size" in s
        assert "best_weighted_score" in s

    def test_select_returns_none_for_empty_population(self):
        result = select_candidate_thompson([])
        assert result is None

    def test_thompson_provides_exploration(self):
        # Even with a good candidate, bad candidate should occasionally be selected
        good = _make_candidate("good", _good_scores())
        bad = _make_candidate("bad", _bad_scores())
        selections = [
            select_candidate_thompson([good, bad], rng_seed=i).id
            for i in range(100)
        ]
        # Bad should appear at least sometimes (exploration)
        assert "bad" in selections, "Thompson sampling should explore occasionally"
