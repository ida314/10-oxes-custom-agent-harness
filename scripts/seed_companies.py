"""Seed 5 target companies into the database."""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
from sqlmodel import Session, create_engine, SQLModel
import db.models  # noqa: registers all tables

load_dotenv()

COMPANIES = [
    {
        "name": "Google",
        "domain": "google.com",
        "ats_type": "greenhouse",
        "careers_url": "https://careers.google.com/jobs/results/",
        "priority": 1,
        "notes": "Large new-grad SWE cohort. STEP program for interns. Roles tagged by team.",
    },
    {
        "name": "Datadog",
        "domain": "datadoghq.com",
        "ats_type": "greenhouse",
        "careers_url": "https://www.datadoghq.com/careers/",
        "priority": 2,
        "notes": "University hire cohort. Go and Python stack. Strong eng blog signal.",
    },
    {
        "name": "Ramp",
        "domain": "ramp.com",
        "ats_type": "greenhouse",
        "careers_url": "https://ramp.com/careers",
        "priority": 2,
        "notes": "High-growth fintech. TypeScript/Python/Go stack. Fast ownership culture.",
    },
    {
        "name": "Jane Street",
        "domain": "janestreet.com",
        "ats_type": "custom",
        "careers_url": "https://www.janestreet.com/join-jane-street/open-positions/",
        "priority": 1,
        "notes": "Highly selective. OCaml-first. Longer posting windows (180-day staleness).",
    },
    {
        "name": "Stripe",
        "domain": "stripe.com",
        "ats_type": "greenhouse",
        "careers_url": "https://stripe.com/jobs/listing",
        "priority": 1,
        "notes": "University hire 2026 cohort. Ruby/Go/Scala stack. Correctness-first culture.",
    },
]

COMPANY_SOURCES = [
    ("google.com", "careers_page", "https://careers.google.com/jobs/results/"),
    ("google.com", "engineering_blog", "https://developers.googleblog.com/"),
    ("datadoghq.com", "careers_page", "https://www.datadoghq.com/careers/"),
    ("datadoghq.com", "engineering_blog", "https://www.datadoghq.com/blog/engineering/"),
    ("ramp.com", "careers_page", "https://ramp.com/careers"),
    ("ramp.com", "engineering_blog", "https://engineering.ramp.com/"),
    ("janestreet.com", "careers_page", "https://www.janestreet.com/join-jane-street/open-positions/"),
    ("janestreet.com", "engineering_blog", "https://blog.janestreet.com/"),
    ("stripe.com", "careers_page", "https://stripe.com/jobs/listing"),
    ("stripe.com", "engineering_blog", "https://stripe.com/blog/engineering"),
]


def seed(database_url: str) -> None:
    engine = create_engine(database_url, echo=False)
    SQLModel.metadata.create_all(engine)

    from db.models import Company, CompanySource

    with Session(engine) as session:
        domain_to_id: dict[str, str] = {}

        for data in COMPANIES:
            existing = session.query(Company).filter_by(domain=data["domain"]).first()
            if existing:
                print(f"  skip (exists): {data['name']}")
                domain_to_id[data["domain"]] = existing.id
                continue

            now = datetime.utcnow()
            company = Company(
                name=data["name"],
                domain=data["domain"],
                ats_type=data.get("ats_type"),
                careers_url=data.get("careers_url"),
                priority=data.get("priority", 5),
                notes=data.get("notes"),
                created_at=now,
                updated_at=now,
            )
            session.add(company)
            session.flush()
            domain_to_id[data["domain"]] = company.id
            print(f"  inserted: {data['name']} ({company.id})")

        for domain, source_type, url in COMPANY_SOURCES:
            company_id = domain_to_id.get(domain)
            if not company_id:
                continue
            existing = (
                session.query(CompanySource)
                .filter_by(company_id=company_id, source_type=source_type, url=url)
                .first()
            )
            if existing:
                continue
            now = datetime.utcnow()
            source = CompanySource(
                company_id=company_id,
                source_type=source_type,
                url=url,
                confidence=1.0,
                created_at=now,
                updated_at=now,
            )
            session.add(source)

        session.commit()
    print("Seed complete.")


if __name__ == "__main__":
    db_url = os.getenv("DATABASE_URL", "postgresql://career_agent:career_agent@localhost:5432/career_agent")
    print(f"Seeding: {db_url}")
    seed(db_url)
