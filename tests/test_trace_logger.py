"""Tests for app/tracing/logger.py (Phase 5 trace filesystem)."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from app.tracing.logger import TraceLogger


@pytest.fixture
def tmp_logger(tmp_path):
    return TraceLogger(datetime.utcnow(), "test_harness", "v0", base_dir=tmp_path)


def test_run_dir_created(tmp_logger):
    assert tmp_logger.run_dir.exists()
    assert (tmp_logger.run_dir / "failures").exists()


def test_log_writes_json_file(tmp_logger):
    path = tmp_logger.log("config", {"key": "value", "count": 42})
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["key"] == "value"
    assert data["count"] == 42


def test_log_files_are_sequential(tmp_logger):
    tmp_logger.log("step_a", {"a": 1})
    tmp_logger.log("step_b", {"b": 2})
    tmp_logger.log("step_c", {"c": 3})
    files = sorted(tmp_logger.run_dir.glob("0*.json"))
    names = [f.name for f in files]
    assert names[0].startswith("000_")
    assert names[1].startswith("001_")
    assert names[2].startswith("002_")


def test_save_output_creates_output_json(tmp_logger):
    tmp_logger.save_output({"result": "ok", "count": 5})
    out = tmp_logger.run_dir / "output.json"
    assert out.exists()
    assert json.loads(out.read_text())["result"] == "ok"


def test_save_metrics(tmp_logger):
    tmp_logger.save_metrics({"recall": 0.85, "precision": 0.72})
    m = tmp_logger.run_dir / "metrics.json"
    assert m.exists()
    assert json.loads(m.read_text())["recall"] == pytest.approx(0.85)


def test_log_failure_writes_to_failures_dir(tmp_logger):
    path = tmp_logger.log_failure("false_positives", [{"job": "Senior SWE"}])
    assert path.parent.name == "failures"
    assert path.exists()


def test_run_id_matches_dir_name(tmp_logger):
    assert tmp_logger.run_id == tmp_logger.run_dir.name


def test_snapshot_harness_source(tmp_logger, tmp_path):
    src = tmp_path / "v0.py"
    src.write_text("# harness code")
    tmp_logger.snapshot_harness_source(src)
    snapped = tmp_logger.run_dir / "harness_v0.py"
    assert snapped.exists()
    assert snapped.read_text() == "# harness code"
