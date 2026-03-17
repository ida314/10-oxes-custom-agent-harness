"""
SQLModel models for the career-agent harness system.
All tables use UUID primary keys and include created_at/updated_at.
Single-column indexes: Field(index=True).
Multi-column indexes: __table_args__ only.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlmodel import Field, SQLModel, Column
from sqlalchemy import UniqueConstraint, Index, JSON, Text


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.utcnow()


# ---------------------------------------------------------------------------
# Company tables
# ---------------------------------------------------------------------------


class Company(SQLModel, table=True):
    __tablename__ = "companies"

    id: str = Field(default_factory=_uuid, primary_key=True)
    name: str = Field(index=True)
    domain: str = Field(unique=True)
    ats_type: Optional[str] = Field(default=None)
    careers_url: Optional[str] = Field(default=None)
    priority: int = Field(default=5)
    notes: Optional[str] = Field(default=None, sa_column=Column(Text))
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class CompanySource(SQLModel, table=True):
    __tablename__ = "company_sources"
    __table_args__ = (
        UniqueConstraint("company_id", "source_type", "url", name="uq_company_source"),
    )

    id: str = Field(default_factory=_uuid, primary_key=True)
    company_id: str = Field(foreign_key="companies.id", index=True)
    source_type: str
    url: str
    last_fetched_at: Optional[datetime] = Field(default=None)
    confidence: float = Field(default=1.0)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


# ---------------------------------------------------------------------------
# Job tables
# ---------------------------------------------------------------------------


class Job(SQLModel, table=True):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("url", name="uq_job_url"),
        UniqueConstraint("normalized_hash", name="uq_job_hash"),
        Index("ix_jobs_company_discovered", "company_id", "discovered_at"),
        Index("ix_jobs_source_status", "source_type", "status"),
        Index("ix_jobs_scores", "entry_level_score", "fit_score"),
    )

    id: str = Field(default_factory=_uuid, primary_key=True)
    company_id: str = Field(foreign_key="companies.id", index=True)
    title: str
    url: str
    location: Optional[str] = Field(default=None)
    description_text: str = Field(sa_column=Column(Text))
    source_type: str = Field(index=True)
    source_url: Optional[str] = Field(default=None)
    discovered_at: datetime = Field(default_factory=_now, index=True)
    posted_at: Optional[datetime] = Field(default=None)
    normalized_hash: str
    entry_level_score: Optional[float] = Field(default=None)
    fit_score: Optional[float] = Field(default=None)
    status: str = Field(default="new", index=True)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


# ---------------------------------------------------------------------------
# Content tables
# ---------------------------------------------------------------------------


class Article(SQLModel, table=True):
    __tablename__ = "articles"
    __table_args__ = (
        Index("ix_articles_company_discovered", "company_id", "discovered_at"),
        Index("ix_articles_source_score", "source_type", "relevance_score"),
    )

    id: str = Field(default_factory=_uuid, primary_key=True)
    company_id: str = Field(foreign_key="companies.id", index=True)
    title: str
    url: Optional[str] = Field(default=None, unique=True)
    source_type: str
    published_at: Optional[datetime] = Field(default=None)
    discovered_at: datetime = Field(default_factory=_now)
    summary: str = Field(sa_column=Column(Text))
    relevance_score: float = Field(default=0.0)
    signal_type: Optional[str] = Field(default=None)
    application_angle: Optional[str] = Field(default=None, sa_column=Column(Text))
    interview_questions: Optional[Any] = Field(default=None, sa_column=Column(JSON))
    confidence: float = Field(default=0.0)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class Event(SQLModel, table=True):
    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_company_date", "company_id", "event_date"),
    )

    id: str = Field(default_factory=_uuid, primary_key=True)
    company_id: str = Field(foreign_key="companies.id", index=True)
    title: str
    url: Optional[str] = Field(default=None)
    event_date: Optional[datetime] = Field(default=None)
    discovered_at: datetime = Field(default_factory=_now)
    event_type: str
    relevance_score: float = Field(default=0.0)
    notes: Optional[str] = Field(default=None, sa_column=Column(Text))
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class Person(SQLModel, table=True):
    __tablename__ = "people"

    id: str = Field(default_factory=_uuid, primary_key=True)
    company_id: str = Field(foreign_key="companies.id", index=True)
    name: str
    role: Optional[str] = Field(default=None)
    linkedin_url: Optional[str] = Field(default=None, unique=True)
    connection_type: Optional[str] = Field(default=None)
    notes: Optional[str] = Field(default=None, sa_column=Column(Text))
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


# ---------------------------------------------------------------------------
# Application tables
# ---------------------------------------------------------------------------


class ApplicationPacket(SQLModel, table=True):
    __tablename__ = "application_packets"

    id: str = Field(default_factory=_uuid, primary_key=True)
    job_id: str = Field(foreign_key="jobs.id", index=True)
    resume_variant_id: Optional[str] = Field(default=None)
    cover_letter: Optional[str] = Field(default=None, sa_column=Column(Text))
    short_answers: Optional[Any] = Field(default=None, sa_column=Column(JSON))
    referral_message: Optional[str] = Field(default=None, sa_column=Column(Text))
    interview_notes: Optional[Any] = Field(default=None, sa_column=Column(JSON))
    unsupported_claims: Optional[Any] = Field(default=None, sa_column=Column(JSON))
    validation_status: str = Field(default="pending")
    approval_status: str = Field(default="pending", index=True)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class Application(SQLModel, table=True):
    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint("job_id", name="uq_application_job"),
    )

    id: str = Field(default_factory=_uuid, primary_key=True)
    job_id: str = Field(foreign_key="jobs.id", index=True)
    status: str = Field(default="draft", index=True)
    submitted_at: Optional[datetime] = Field(default=None)
    packet_id: Optional[str] = Field(default=None, foreign_key="application_packets.id")
    notes: Optional[str] = Field(default=None, sa_column=Column(Text))
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


# ---------------------------------------------------------------------------
# Skill library
# ---------------------------------------------------------------------------


class Skill(SQLModel, table=True):
    __tablename__ = "skills"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_skill_name_version"),
    )

    id: str = Field(default_factory=_uuid, primary_key=True)
    name: str = Field(index=True)
    version: str
    domain: str = Field(index=True)
    status: str = Field(default="experimental")
    file_path: str
    success_rate: Optional[float] = Field(default=None)
    last_used_at: Optional[datetime] = Field(default=None)
    known_failure_modes: Optional[Any] = Field(default=None, sa_column=Column(JSON))
    allowed_tools: Optional[Any] = Field(default=None, sa_column=Column(JSON))
    eval_metrics: Optional[Any] = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


# ---------------------------------------------------------------------------
# Harness candidates
# ---------------------------------------------------------------------------


class HarnessCandidate(SQLModel, table=True):
    __tablename__ = "harness_candidates"
    __table_args__ = (
        UniqueConstraint("domain", "name", "version", name="uq_harness_candidate"),
        Index("ix_harness_domain_status", "domain", "status"),
    )

    id: str = Field(default_factory=_uuid, primary_key=True)
    domain: str = Field(index=True)
    name: str
    version: str
    parent_id: Optional[str] = Field(default=None, foreign_key="harness_candidates.id")
    file_path: str
    search_scores: Optional[Any] = Field(default=None, sa_column=Column(JSON))
    notes: Optional[str] = Field(default=None, sa_column=Column(Text))
    status: str = Field(default="experimental")
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


# ---------------------------------------------------------------------------
# Agent execution tables
# ---------------------------------------------------------------------------


class AgentRun(SQLModel, table=True):
    __tablename__ = "agent_runs"
    __table_args__ = (
        Index("ix_agent_runs_type_status", "run_type", "status"),
    )

    id: str = Field(default_factory=_uuid, primary_key=True)
    harness_candidate_id: Optional[str] = Field(
        default=None, foreign_key="harness_candidates.id", index=True
    )
    run_type: str = Field(index=True)
    started_at: datetime = Field(default_factory=_now)
    finished_at: Optional[datetime] = Field(default=None)
    status: str = Field(default="running", index=True)
    company_id: Optional[str] = Field(default=None, foreign_key="companies.id", index=True)
    profile_id: Optional[str] = Field(default=None)
    trace_dir: Optional[str] = Field(default=None)
    summary_metrics: Optional[Any] = Field(default=None, sa_column=Column(JSON))
    error: Optional[str] = Field(default=None, sa_column=Column(Text))
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class ToolCall(SQLModel, table=True):
    __tablename__ = "tool_calls"
    __table_args__ = (
        Index("ix_tool_calls_run_seq", "agent_run_id", "sequence"),
    )

    id: str = Field(default_factory=_uuid, primary_key=True)
    agent_run_id: str = Field(foreign_key="agent_runs.id", index=True)
    sequence: int = Field(default=0)
    tool_name: str = Field(index=True)
    input_data: Optional[Any] = Field(default=None, sa_column=Column(JSON))
    output_data: Optional[Any] = Field(default=None, sa_column=Column(JSON))
    started_at: datetime = Field(default_factory=_now)
    duration_ms: Optional[int] = Field(default=None)
    success: bool = Field(default=True)
    error: Optional[str] = Field(default=None, sa_column=Column(Text))
    created_at: datetime = Field(default_factory=_now)


class TraceEvent(SQLModel, table=True):
    __tablename__ = "trace_events"
    __table_args__ = (
        Index("ix_trace_events_run_seq", "agent_run_id", "sequence"),
    )

    id: str = Field(default_factory=_uuid, primary_key=True)
    agent_run_id: str = Field(foreign_key="agent_runs.id", index=True)
    sequence: int = Field(default=0)
    event_type: str = Field(index=True)
    payload: Optional[Any] = Field(default=None, sa_column=Column(JSON))
    timestamp: datetime = Field(default_factory=_now)
    created_at: datetime = Field(default_factory=_now)


# ---------------------------------------------------------------------------
# Eval and approval tables
# ---------------------------------------------------------------------------


class EvalScore(SQLModel, table=True):
    __tablename__ = "eval_scores"
    __table_args__ = (
        Index("ix_eval_scores_candidate_split", "harness_candidate_id", "dataset_split"),
    )

    id: str = Field(default_factory=_uuid, primary_key=True)
    harness_candidate_id: str = Field(
        foreign_key="harness_candidates.id", index=True
    )
    dataset_split: str = Field(index=True)
    metric: str = Field(index=True)
    score: float
    n_cases: int = Field(default=0)
    evaluated_at: datetime = Field(default_factory=_now)
    run_id: Optional[str] = Field(default=None, foreign_key="agent_runs.id")
    created_at: datetime = Field(default_factory=_now)


class ApprovalItem(SQLModel, table=True):
    __tablename__ = "approval_items"
    __table_args__ = (
        Index("ix_approval_items_status_type", "status", "item_type"),
    )

    id: str = Field(default_factory=_uuid, primary_key=True)
    item_type: str = Field(index=True)
    item_id: Optional[str] = Field(default=None)
    item_data: Optional[Any] = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_now)
    status: str = Field(default="pending", index=True)
    reviewed_at: Optional[datetime] = Field(default=None)
    reviewer_notes: Optional[str] = Field(default=None, sa_column=Column(Text))
    updated_at: datetime = Field(default_factory=_now)
