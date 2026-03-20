"""
Tests for db/models.py.

Uses SQLite in-memory so no Postgres/Docker is required.
Run: .venv/bin/pytest tests/test_db_models.py -v
"""

import hashlib
from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, create_engine

import db.models  # noqa: registers all table metadata


@pytest.fixture(scope="function")
def engine():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    yield eng
    SQLModel.metadata.drop_all(eng)


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        yield s


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_company(session, name="Acme", domain="acme.com"):
    from db.models import Company
    now = datetime.utcnow()
    c = Company(name=name, domain=domain, ats_type="greenhouse", priority=3,
                created_at=now, updated_at=now)
    session.add(c)
    session.commit()
    session.refresh(c)
    return c


def _job_hash(company_name: str, title: str, location: str) -> str:
    raw = f"{company_name.lower()}|{title.lower()}|{(location or '').lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _make_job(session, company_id, url="https://acme.com/jobs/1", title="SWE New Grad",
              location="New York", hash_suffix=""):
    from db.models import Job
    now = datetime.utcnow()
    j = Job(
        company_id=company_id,
        title=title,
        url=url,
        location=location,
        description_text="Build things.",
        source_type="greenhouse",
        discovered_at=now,
        normalized_hash=_job_hash("Acme" + hash_suffix, title, location),
        status="new",
        created_at=now,
        updated_at=now,
    )
    session.add(j)
    session.commit()
    session.refresh(j)
    return j


# ---------------------------------------------------------------------------
# Company tests
# ---------------------------------------------------------------------------

def test_create_company(session):
    company = _make_company(session)
    assert company.id is not None
    assert company.name == "Acme"
    assert company.domain == "acme.com"
    assert company.priority == 3
    assert isinstance(company.created_at, datetime)


def test_company_domain_unique(session):
    _make_company(session, name="Acme", domain="acme.com")
    with pytest.raises((IntegrityError, Exception)):
        _make_company(session, name="Acme2", domain="acme.com")


def test_company_source_created(session):
    from db.models import CompanySource
    company = _make_company(session)
    now = datetime.utcnow()
    src = CompanySource(
        company_id=company.id,
        source_type="careers_page",
        url="https://acme.com/careers",
        confidence=1.0,
        created_at=now,
        updated_at=now,
    )
    session.add(src)
    session.commit()
    session.refresh(src)
    assert src.id is not None
    assert src.company_id == company.id


# ---------------------------------------------------------------------------
# Job tests
# ---------------------------------------------------------------------------

def test_create_job(session):
    company = _make_company(session)
    job = _make_job(session, company.id)
    assert job.id is not None
    assert job.company_id == company.id
    assert job.status == "new"
    assert job.title == "SWE New Grad"


def test_update_job_status(session):
    company = _make_company(session)
    job = _make_job(session, company.id)

    job.status = "reviewed"
    job.updated_at = datetime.utcnow()
    session.add(job)
    session.commit()
    session.refresh(job)

    assert job.status == "reviewed"


def test_job_url_unique_constraint(session):
    company = _make_company(session)
    _make_job(session, company.id, url="https://acme.com/jobs/1")
    with pytest.raises((IntegrityError, Exception)):
        _make_job(session, company.id, url="https://acme.com/jobs/1", hash_suffix="2")


def test_job_normalized_hash_unique_constraint(session):
    company = _make_company(session)
    _make_job(session, company.id, url="https://acme.com/jobs/1", title="SWE New Grad",
              location="New York")
    # Same title + location → same hash → should fail even with different URL
    from db.models import Job
    now = datetime.utcnow()
    dup = Job(
        company_id=company.id,
        title="SWE New Grad",
        url="https://acme.com/jobs/999",
        location="New York",
        description_text="Different page, same role.",
        source_type="linkedin",
        discovered_at=now,
        normalized_hash=_job_hash("Acme", "SWE New Grad", "New York"),
        status="new",
        created_at=now,
        updated_at=now,
    )
    session.add(dup)
    with pytest.raises((IntegrityError, Exception)):
        session.commit()


# ---------------------------------------------------------------------------
# Application packet + approval item tests
# ---------------------------------------------------------------------------

def test_application_packet_approval_workflow(session):
    from db.models import ApplicationPacket, ApprovalItem
    company = _make_company(session)
    job = _make_job(session, company.id)
    now = datetime.utcnow()

    packet = ApplicationPacket(
        job_id=job.id,
        cover_letter="I am excited to apply.",
        unsupported_claims=[],
        validation_status="passed",
        approval_status="pending",
        created_at=now,
        updated_at=now,
    )
    session.add(packet)
    session.commit()
    session.refresh(packet)
    assert packet.approval_status == "pending"

    item = ApprovalItem(
        item_type="application_packet",
        item_id=packet.id,
        status="pending",
        created_at=now,
        updated_at=now,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    assert item.status == "pending"

    # Approve
    item.status = "approved"
    item.reviewed_at = datetime.utcnow()
    item.reviewer_notes = "Looks good."
    session.add(item)
    session.commit()
    session.refresh(item)
    assert item.status == "approved"


# ---------------------------------------------------------------------------
# HarnessCandidate + EvalScore tests
# ---------------------------------------------------------------------------

def test_harness_candidate_and_eval_score(session):
    from db.models import HarnessCandidate, EvalScore
    now = datetime.utcnow()

    candidate = HarnessCandidate(
        domain="job_discovery",
        name="v0",
        version="0.1.0",
        file_path="harnesses/job_discovery/v0.py",
        status="experimental",
        created_at=now,
        updated_at=now,
    )
    session.add(candidate)
    session.commit()
    session.refresh(candidate)
    assert candidate.id is not None

    score = EvalScore(
        harness_candidate_id=candidate.id,
        dataset_split="search",
        metric="job_recall",
        score=0.82,
        n_cases=40,
        evaluated_at=now,
        created_at=now,
    )
    session.add(score)
    session.commit()
    session.refresh(score)
    assert score.score == pytest.approx(0.82)
    assert score.dataset_split == "search"


# ---------------------------------------------------------------------------
# AgentRun + ToolCall + TraceEvent tests
# ---------------------------------------------------------------------------

def test_agent_run_trace(session):
    from db.models import AgentRun, ToolCall, TraceEvent
    company = _make_company(session)
    now = datetime.utcnow()

    run = AgentRun(
        run_type="company_scan",
        started_at=now,
        status="running",
        company_id=company.id,
        created_at=now,
        updated_at=now,
    )
    session.add(run)
    session.commit()
    session.refresh(run)

    call = ToolCall(
        agent_run_id=run.id,
        sequence=0,
        tool_name="query_greenhouse_jobs",
        input_data={"company": "Acme"},
        output_data={"jobs": []},
        started_at=now,
        duration_ms=120,
        success=True,
        created_at=now,
    )
    session.add(call)

    event = TraceEvent(
        agent_run_id=run.id,
        sequence=1,
        event_type="prompt",
        payload={"text": "Score these jobs..."},
        timestamp=now,
        created_at=now,
    )
    session.add(event)
    session.commit()

    session.refresh(run)
    assert run.status == "running"

    run.status = "completed"
    run.finished_at = datetime.utcnow()
    run.summary_metrics = {"jobs_found": 3}
    session.add(run)
    session.commit()
    session.refresh(run)
    assert run.status == "completed"
    assert run.summary_metrics["jobs_found"] == 3
