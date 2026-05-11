"""Database session dependency for FastAPI routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ask_bpl_orchestrator.db.session import get_db_session


async def _session_dependency() -> AsyncSession:
    async for session in get_db_session():
        return session


async def session_dependency() -> AsyncSession:
    async for session in get_db_session():
        yield session


DbSessionDep = Annotated[AsyncSession, Depends(session_dependency)]
