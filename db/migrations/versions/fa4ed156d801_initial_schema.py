"""initial schema

Revision ID: fa4ed156d801
Revises:
Create Date: 2026-06-07

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "fa4ed156d801"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("domain", sa.String(), nullable=False, unique=True),
        sa.Column("ats_type", sa.String(), nullable=True),
        sa.Column("careers_url", sa.String(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_companies_name", "companies", ["name"])

    op.create_table(
        "company_sources",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("company_id", sa.String(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("last_fetched_at", sa.DateTime(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "source_type", "url", name="uq_company_source"),
    )
    op.create_index("ix_company_sources_company_id", "company_sources", ["company_id"])

    op.create_table(
        "jobs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("company_id", sa.String(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("location", sa.String(), nullable=True),
        sa.Column("description_text", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("source_url", sa.String(), nullable=True),
        sa.Column("discovered_at", sa.DateTime(), nullable=False),
        sa.Column("posted_at", sa.DateTime(), nullable=True),
        sa.Column("normalized_hash", sa.String(), nullable=False),
        sa.Column("entry_level_score", sa.Float(), nullable=True),
        sa.Column("fit_score", sa.Float(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="new"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("url", name="uq_job_url"),
        sa.UniqueConstraint("normalized_hash", name="uq_job_hash"),
    )
    op.create_index("ix_jobs_company_id", "jobs", ["company_id"])
    op.create_index("ix_jobs_discovered_at", "jobs", ["discovered_at"])
    op.create_index("ix_jobs_status", "jobs", ["status"])
    op.create_index("ix_jobs_company_discovered", "jobs", ["company_id", "discovered_at"])
    op.create_index("ix_jobs_source_status", "jobs", ["source_type", "status"])
    op.create_index("ix_jobs_scores", "jobs", ["entry_level_score", "fit_score"])

    op.create_table(
        "articles",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("company_id", sa.String(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=True, unique=True),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("discovered_at", sa.DateTime(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("relevance_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("signal_type", sa.String(), nullable=True),
        sa.Column("application_angle", sa.Text(), nullable=True),
        sa.Column("interview_questions", sa.JSON(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_articles_company_id", "articles", ["company_id"])
    op.create_index("ix_articles_company_discovered", "articles", ["company_id", "discovered_at"])
    op.create_index("ix_articles_source_score", "articles", ["source_type", "relevance_score"])

    op.create_table(
        "events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("company_id", sa.String(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=True),
        sa.Column("event_date", sa.DateTime(), nullable=True),
        sa.Column("discovered_at", sa.DateTime(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("relevance_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_events_company_id", "events", ["company_id"])
    op.create_index("ix_events_company_date", "events", ["company_id", "event_date"])

    op.create_table(
        "people",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("company_id", sa.String(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=True),
        sa.Column("linkedin_url", sa.String(), nullable=True, unique=True),
        sa.Column("connection_type", sa.String(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_people_company_id", "people", ["company_id"])

    op.create_table(
        "application_packets",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("job_id", sa.String(), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("resume_variant_id", sa.String(), nullable=True),
        sa.Column("cover_letter", sa.Text(), nullable=True),
        sa.Column("short_answers", sa.JSON(), nullable=True),
        sa.Column("referral_message", sa.Text(), nullable=True),
        sa.Column("interview_notes", sa.JSON(), nullable=True),
        sa.Column("unsupported_claims", sa.JSON(), nullable=True),
        sa.Column("validation_status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("approval_status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_application_packets_job_id", "application_packets", ["job_id"])
    op.create_index("ix_application_packets_approval", "application_packets", ["approval_status"])

    op.create_table(
        "applications",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("job_id", sa.String(), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="draft"),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("packet_id", sa.String(), sa.ForeignKey("application_packets.id"), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("job_id", name="uq_application_job"),
    )
    op.create_index("ix_applications_job_id", "applications", ["job_id"])
    op.create_index("ix_applications_status", "applications", ["status"])

    op.create_table(
        "skills",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("version", sa.String(), nullable=False),
        sa.Column("domain", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="experimental"),
        sa.Column("file_path", sa.String(), nullable=False),
        sa.Column("success_rate", sa.Float(), nullable=True),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("known_failure_modes", sa.JSON(), nullable=True),
        sa.Column("allowed_tools", sa.JSON(), nullable=True),
        sa.Column("eval_metrics", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("name", "version", name="uq_skill_name_version"),
    )
    op.create_index("ix_skills_name", "skills", ["name"])
    op.create_index("ix_skills_domain", "skills", ["domain"])

    op.create_table(
        "harness_candidates",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("domain", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("version", sa.String(), nullable=False),
        sa.Column("parent_id", sa.String(), sa.ForeignKey("harness_candidates.id"), nullable=True),
        sa.Column("file_path", sa.String(), nullable=False),
        sa.Column("search_scores", sa.JSON(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="experimental"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("domain", "name", "version", name="uq_harness_candidate"),
    )
    op.create_index("ix_harness_candidates_domain", "harness_candidates", ["domain"])
    op.create_index("ix_harness_domain_status", "harness_candidates", ["domain", "status"])

    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("harness_candidate_id", sa.String(), sa.ForeignKey("harness_candidates.id"), nullable=True),
        sa.Column("run_type", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="running"),
        sa.Column("company_id", sa.String(), sa.ForeignKey("companies.id"), nullable=True),
        sa.Column("profile_id", sa.String(), nullable=True),
        sa.Column("trace_dir", sa.String(), nullable=True),
        sa.Column("summary_metrics", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_agent_runs_harness_candidate_id", "agent_runs", ["harness_candidate_id"])
    op.create_index("ix_agent_runs_type_status", "agent_runs", ["run_type", "status"])
    op.create_index("ix_agent_runs_company", "agent_runs", ["company_id"])

    op.create_table(
        "tool_calls",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("agent_run_id", sa.String(), sa.ForeignKey("agent_runs.id"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tool_name", sa.String(), nullable=False),
        sa.Column("input_data", sa.JSON(), nullable=True),
        sa.Column("output_data", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_tool_calls_agent_run_id", "tool_calls", ["agent_run_id"])
    op.create_index("ix_tool_calls_run_seq", "tool_calls", ["agent_run_id", "sequence"])
    op.create_index("ix_tool_calls_tool_name", "tool_calls", ["tool_name"])

    op.create_table(
        "trace_events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("agent_run_id", sa.String(), sa.ForeignKey("agent_runs.id"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_trace_events_agent_run_id", "trace_events", ["agent_run_id"])
    op.create_index("ix_trace_events_run_seq", "trace_events", ["agent_run_id", "sequence"])
    op.create_index("ix_trace_events_event_type", "trace_events", ["event_type"])

    op.create_table(
        "eval_scores",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("harness_candidate_id", sa.String(), sa.ForeignKey("harness_candidates.id"), nullable=False),
        sa.Column("dataset_split", sa.String(), nullable=False),
        sa.Column("metric", sa.String(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("n_cases", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("evaluated_at", sa.DateTime(), nullable=False),
        sa.Column("run_id", sa.String(), sa.ForeignKey("agent_runs.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_eval_scores_harness_candidate_id", "eval_scores", ["harness_candidate_id"])
    op.create_index("ix_eval_scores_candidate_split", "eval_scores", ["harness_candidate_id", "dataset_split"])
    op.create_index("ix_eval_scores_metric", "eval_scores", ["metric"])

    op.create_table(
        "approval_items",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("item_type", sa.String(), nullable=False),
        sa.Column("item_id", sa.String(), nullable=True),
        sa.Column("item_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("reviewer_notes", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_approval_items_item_type", "approval_items", ["item_type"])
    op.create_index("ix_approval_items_status", "approval_items", ["status"])
    op.create_index("ix_approval_items_status_type", "approval_items", ["status", "item_type"])


def downgrade() -> None:
    op.drop_table("approval_items")
    op.drop_table("eval_scores")
    op.drop_table("trace_events")
    op.drop_table("tool_calls")
    op.drop_table("agent_runs")
    op.drop_table("harness_candidates")
    op.drop_table("skills")
    op.drop_table("applications")
    op.drop_table("application_packets")
    op.drop_table("people")
    op.drop_table("events")
    op.drop_table("articles")
    op.drop_table("jobs")
    op.drop_table("company_sources")
    op.drop_table("companies")
