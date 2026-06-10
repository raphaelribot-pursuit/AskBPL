"""
Ask BPL — Seed Lee Aulder Tester Credentials
==========================================
Engineer : Denward Lee Aulder
Date     : 2026-06-08

Provisions Lee Aulder's tester account into Postgres for Demo Day.
Lee Aulder is roleplaying as a new BPL employee in the Office of Technology
logging into the staff intranet for the first time.

Usage
-----
  From packages/orchestrator/:

    source .venv/bin/activate
    python ask_bpl_orchestrator/services/seed_laulder.py

  Or with a custom access code:

    LAULDER_ACCESS_CODE=MyCode123 python ask_bpl_orchestrator/services/seed_laulder.py

Credentials seeded
------------------
  Email       : laulder@bklynlibrary.org
  Access code : DEMO2026  (or LAULDER_ACCESS_CODE env var)
  Group       : non_expert
  Department  : New Hire — Office of Technology

After running, share with tester:
  Email       : laulder@bklynlibrary.org
  Access code : DEMO2026
  Login URL   : http://localhost:5173

Notes
-----
- Idempotent, safe to run multiple times.
- TEAM_NAMESPACE matches seed.py exactly for a stable tester_id.
- Department set to "New Hire — Office of Technology" for demo day scenario.
- At activation this seam swaps to BPL Entra ID (TRD-AUTH-5).
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone

from passlib.hash import bcrypt
from sqlalchemy import select

from ask_bpl_orchestrator.db.models import Tester, TesterGroup
from ask_bpl_orchestrator.db.session import async_session_factory

# Must match TEAM_NAMESPACE in seed.py exactly
TEAM_NAMESPACE = uuid.UUID("a3bb189e-8bf9-3888-9f71-5d87cdc60bf6")

LAULDER_EMAIL = "laulder@bklynlibrary.org"
LAULDER_ACCESS_CODE = os.environ.get("LAULDER_ACCESS_CODE", "DEMO2026")


async def seed_laulder() -> None:
    tester_id = uuid.uuid5(TEAM_NAMESPACE, LAULDER_EMAIL.lower())

    async with async_session_factory() as session:
        hashed = bcrypt.hash(LAULDER_ACCESS_CODE)

        tester = Tester(
            tester_id=tester_id,
            email=LAULDER_EMAIL.lower(),
            access_code_hash=hashed,
            group=TesterGroup.non_expert,
            department="New Hire — Office of Technology",
            issued_at=datetime.now(timezone.utc),
            active=True,
        )

        existing = (
            (await session.execute(select(Tester).where(Tester.email == LAULDER_EMAIL.lower())))
            .scalars()
            .first()
        )

        merged = existing or tester
        merged.email = LAULDER_EMAIL.lower()
        merged.access_code_hash = hashed
        merged.group = TesterGroup.non_expert
        merged.department = "New Hire — Office of Technology"
        merged.issued_at = merged.issued_at or datetime.now(timezone.utc)
        merged.active = True

        await session.merge(merged)
        await session.commit()

    print("=" * 56)
    print("  Ask BPL — Lee Aulder tester credentials seeded")
    print("=" * 56)
    print(f"  tester_id   : {tester_id}")
    print(f"  email       : {LAULDER_EMAIL}")
    print(f"  access code : {LAULDER_ACCESS_CODE}")
    print(f"  group       : non_expert")
    print(f"  department  : New Hire — Office of Technology")
    print(f"  active      : True")
    print("=" * 56)
    print()
    print("  Share with tester (Demo Day):")
    print(f"    Email       : {LAULDER_EMAIL}")
    print(f"    Access code : {LAULDER_ACCESS_CODE}")
    print(f"    Login URL   : http://localhost:5173")
    print()
    print("  Idempotent — safe to run again.")
    print("=" * 56)


if __name__ == "__main__":
    asyncio.run(seed_laulder())
