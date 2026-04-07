"""
Shared trace logger for all harnesses.
Every harness run creates a directory under experiments/runs/ with:
  config.json, output.json, per-step trace files, failures/
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

EXPERIMENTS_DIR = Path(__file__).parents[2] / "experiments" / "runs"


class TraceLogger:
    """
    Creates experiments/runs/{timestamp}_{harness}_{version}/ and writes
    sequential JSON trace files. Used by all harnesses.

    Usage:
        trace = TraceLogger(datetime.utcnow(), "job_discovery", "v0")
        trace.log("config", {...})
        trace.log("ats_result", {...})
        trace.save_output(report.model_dump())
    """

    def __init__(
        self,
        started_at: datetime,
        harness: str,
        version: str,
        base_dir: Path | None = None,
    ):
        self.base_dir = base_dir or EXPERIMENTS_DIR
        ts = started_at.strftime("%Y-%m-%dT%H-%M-%S")
        self.run_dir = self.base_dir / f"{ts}_{harness}_{version}"
        self.run_dir.mkdir(parents=True, exist_ok=True)
        (self.run_dir / "failures").mkdir(exist_ok=True)
        self._seq = 0
        self._harness = harness
        self._version = version
        self._started_at = started_at

    def log(self, name: str, data: Any) -> Path:
        fname = f"{self._seq:03d}_{name}.json"
        path = self.run_dir / fname
        path.write_text(json.dumps(data, indent=2, default=str))
        self._seq += 1
        return path

    def log_failure(self, name: str, data: Any) -> Path:
        path = self.run_dir / "failures" / f"{name}.json"
        path.write_text(json.dumps(data, indent=2, default=str))
        return path

    def save_config(self, config: Any) -> None:
        (self.run_dir / "config.json").write_text(
            json.dumps(config, indent=2, default=str)
        )

    def save_output(self, report: Any) -> None:
        (self.run_dir / "output.json").write_text(
            json.dumps(report, indent=2, default=str)
        )

    def save_metrics(self, metrics: dict) -> None:
        (self.run_dir / "metrics.json").write_text(
            json.dumps(metrics, indent=2, default=str)
        )

    def snapshot_harness_source(self, source_path: Path) -> None:
        """Copy the harness source file into the trace directory."""
        import shutil
        dest = self.run_dir / f"harness_{source_path.name}"
        shutil.copy2(source_path, dest)

    @property
    def run_id(self) -> str:
        return self.run_dir.name
