#!/usr/bin/env python3
"""Add a demo user to the production database.

Usage:
    DATABASE_URL="postgresql+asyncpg://..." python scripts/add_demo_user.py

Or set DATABASE_URL, DEMO_EMAIL, and DEMO_PASSWORD in the environment and run:
    python scripts/add_demo_user.py
"""

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

from passlib.hash import bcrypt
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Add the orchestrator package to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "packages", "orchestrator"))

from ask_bpl_orchestrator.db.models import Tester, TesterGroup

TEAM_NAMESPACE = uuid.UUID("a3bb189e-8bf9-3888-8f715-d87cdc60bf6")

async def add_demo_user(database_url: str, *, email: str, password: str) -> None:
    """Add the demo user to the database."""
    # Convert postgres:// to postgresql+asyncpg:// if needed
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif database_url.startswith("postgresql://") and "+asyncpg" not in database_url:
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(database_url, echo=False)
    async_session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    tester_id = uuid.uuid5(TEAM_NAMESPACE, email.lower())
    hashed = bcrypt.hash(password)

    async with async_session_factory() as session:
        # Check if user already exists
        result = await session.execute(
            select(Tester).where(Tester.email == email.lower())
        )
        existing = result.scalars().first()

        if existing:
            print(f"User {email} already exists. Updating password...")
            existing.access_code_hash = hashed
            existing.active = True
            await session.merge(existing)
        else:
            print(f"Creating new user {email}...")
            tester = Tester(
                tester_id=tester_id,
                email=email.lower(),
                access_code_hash=hashed,
                group=TesterGroup.SME,
                department="Pilot",
                issued_at=datetime.now(timezone.utc),
                active=True,
            )
            session.add(tester)

        await session.commit()
        print(f"✅ Demo user created/updated successfully!")
        print(f"   Email: {email}")


def main() -> None:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    demo_email = os.environ.get("DEMO_EMAIL", "").strip()
    demo_password = os.environ.get("DEMO_PASSWORD", "").strip()
    if not database_url:
        print("ERROR: DATABASE_URL environment variable is required.")
        print()
        print("Get the connection string from Render Dashboard:")
        print("  1. Go to https://dashboard.render.com")
        print("  2. Click on 'askbpl-db' database")
        print("  3. Copy the 'External Database URL'")
        print()
        print("Then run:")
        print('  DATABASE_URL="postgresql://..." python scripts/add_demo_user.py')
        sys.exit(1)
    if not demo_email or not demo_password:
        print("ERROR: DEMO_EMAIL and DEMO_PASSWORD environment variables are required.")
        sys.exit(1)

    asyncio.run(add_demo_user(database_url, email=demo_email, password=demo_password))


if __name__ == "__main__":
    main()
