"""
Ask BPL — Seed Selvon Tester Credentials
==========================================
Engineer : Denward Lee Aulder
Date     : 2026-05-26

Provisions Selvon Smith's tester account into Postgres by calling
seed_demo_tester() from seed.py directly — same function, same path,
no duplication.

Usage
-----
  From packages/orchestrator/:

    source .venv/bin/activate
    python ask_bpl_orchestrator/services/seed_selvon.py

  Or with a custom access code:

    SELVON_ACCESS_CODE=MyCode123 python ask_bpl_orchestrator/services/seed_selvon.py

Credentials seeded
------------------
  Email       : ssmith@bklynlibrary.org
  Access code : DEMO2026  (or SELVON_ACCESS_CODE env var)
  Group       : SME
  Department  : Pilot — BPL Lead

After running, share with Selvon:
  Email       : ssmith@bklynlibrary.org
  Access code : DEMO2026
  Login URL   : http://localhost:5173

Notes
-----
- Calls seed_demo_tester() from seed.py — idempotent, safe to run twice.
- TEAM_NAMESPACE matches seed.py exactly for a stable tester_id.
- Department override applied after merge so it doesn't clobber existing rows.
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
TEAM_NAMESPACE = uuid.UUID("a3bb189e-8bf9-3888-8f715-d87cdc60bf6")

SELVON_EMAIL = "ssmith@bklynlibrary.org"
SELVON_ACCESS_CODE = os.environ.get("SELVON_ACCESS_CODE", "DEMO2026")


async def seed_selvon() -> None:
    tester_id = uuid.uuid5(TEAM_NAMESPACE, SELVON_EMAIL.lower())

    async with async_session_factory() as session:
        hashed = bcrypt.hash(SELVON_ACCESS_CODE)

        tester = Tester(
            tester_id=tester_id,
            email=SELVON_EMAIL.lower(),
            access_code_hash=hashed,
            group=TesterGroup.SME,
            department="Pilot — BPL Lead",
            issued_at=datetime.now(timezone.utc),
            active=True,
        )

        existing = (
            (await session.execute(select(Tester).where(Tester.email == SELVON_EMAIL.lower())))
            .scalars()
            .first()
        )

        merged = existing or tester
        merged.email = SELVON_EMAIL.lower()
        merged.access_code_hash = hashed
        merged.group = TesterGroup.SME
        merged.department = "Pilot — BPL Lead"
        merged.issued_at = merged.issued_at or datetime.now(timezone.utc)
        merged.active = True

        await session.merge(merged)
        await session.commit()

    print("=" * 52)
    print("  Ask BPL — Selvon tester credentials seeded")
    print("=" * 52)
    print(f"  tester_id   : {tester_id}")
    print(f"  email       : {SELVON_EMAIL}")
    print(f"  access code : {SELVON_ACCESS_CODE}")
    print(f"  group       : SME")
    print(f"  department  : Pilot — BPL Lead")
    print(f"  active      : True")
    print("=" * 52)
    print()
    print("  Share with Selvon:")
    print(f"    Email       : {SELVON_EMAIL}")
    print(f"    Access code : {SELVON_ACCESS_CODE}")
    print(f"    Login URL   : http://localhost:5173")
    print()
    print("  Idempotent — safe to run again.")
    print("=" * 52)


if __name__ == "__main__":
    asyncio.run(seed_selvon())