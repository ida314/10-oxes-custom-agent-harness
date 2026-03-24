"""
Base types for the career-agent skill library.

Every skill implements the Skill protocol and returns a SkillResult.
Skills are deterministic executable units — not prompt snippets.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Evidence — a single sourced piece of supporting information
# ---------------------------------------------------------------------------


class Evidence(BaseModel):
    url: str | None = None
    source_type: str  # greenhouse_api | lever_api | ashby_api | html_parse | web_search
    excerpt: str | None = None
    fetched_at: datetime
    confidence: float = 1.0


# ---------------------------------------------------------------------------
# SkillResult — typed output from every skill run
# ---------------------------------------------------------------------------


class SkillResult(BaseModel):
    success: bool
    items: list[Any] = []
    evidence: list[Evidence] = []
    confidence: float = 0.0
    errors: list[str] = []
    raw: dict[str, Any] = {}  # raw API/HTML payload for trace logging

    @classmethod
    def failure(cls, error: str, raw: dict | None = None) -> "SkillResult":
        return cls(success=False, errors=[error], raw=raw or {})


# ---------------------------------------------------------------------------
# RunContext — execution context passed into every skill run
# ---------------------------------------------------------------------------


@dataclass
class RunContext:
    agent_run_id: str | None = None
    dry_run: bool = False
    timeout_seconds: int = 30
    extra: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Skill protocol — every skill must implement this
# ---------------------------------------------------------------------------


@runtime_checkable
class Skill(Protocol):
    name: str
    version: str
    domain: str  # ats | company_research | article_extraction | outreach | coding

    def run(self, input: BaseModel, context: RunContext) -> SkillResult:
        ...


# ---------------------------------------------------------------------------
# NormalizedJob — canonical job shape produced by all ATS connectors
# ---------------------------------------------------------------------------


class NormalizedJob(BaseModel):
    title: str
    url: str
    location: str | None = None
    description_text: str = ""
    source_type: str
    source_url: str | None = None
    posted_at: datetime | None = None
    discovered_at: datetime
    normalized_hash: str  # sha256 of company|title|location (lowercased)
    raw_id: str | None = None  # ATS-native requisition ID
    extra: dict[str, Any] = {}
