"""Build-team internal API (TRD §11) — also mounted at ``/v1/internal``."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from ask_bpl_orchestrator.api.routes_admin import aggregate_summary, guard_admin
from ask_bpl_orchestrator.api.session_dep import DbSessionDep
from ask_bpl_orchestrator.db.models import Chunk, Document, RoutingRule, Session
from ask_bpl_orchestrator.ingest.batch import ingest_manifest

router = APIRouter(prefix="/internal", tags=["internal"], dependencies=[Depends(guard_admin)])


class IngestRequest(BaseModel):
    manifest_path: str = Field(
        default="sample_corpus/corpus_manifest.yaml",
        description="Repo-relative path to corpus manifest YAML",
    )


class RoutingApprovalBody(BaseModel):
    selvon_approved: bool = True


@router.get("/corpus")
async def corpus_status(db: DbSessionDep) -> dict:
    docs = (await db.execute(select(Document).order_by(Document.title))).scalars().all()
    chunk_count = int((await db.execute(select(func.count()).select_from(Chunk))).scalar_one() or 0)
    page_count = int((await db.execute(select(func.coalesce(func.sum(Document.page_count), 0)))).scalar_one() or 0)
    last_ingest = (
        await db.execute(select(func.max(Document.ingested_at)).select_from(Document))
    ).scalar_one()

    return {
        "doc_count": len(docs),
        "page_count": page_count,
        "chunk_count": chunk_count,
        "last_ingest_at": last_ingest.isoformat() if last_ingest else None,
        "documents": [
            {
                "document_id": str(d.document_id),
                "title": d.title,
                "version": d.version,
                "policy_type": d.policy_type,
                "ingest_status": d.ingest_status.value,
                "last_ingested_at": d.ingested_at.isoformat() if d.ingested_at else None,
                "page_count": d.page_count,
            }
            for d in docs
        ],
    }


@router.get("/sessions")
async def list_sessions(db: DbSessionDep, limit: int = 100) -> dict:
    cap = max(1, min(limit, 500))
    rows = (
        await db.execute(
            select(Session)
            .order_by(Session.started_at.desc())
            .limit(cap)
        )
    ).scalars().all()

    return {
        "sessions": [
            {
                "session_id": str(s.session_id),
                "tester_id": str(s.tester_id) if s.tester_id else None,
                "attribution_mode": s.attribution_mode.value,
                "started_at": s.started_at.isoformat(),
                "expires_at": s.expires_at.isoformat(),
            }
            for s in rows
        ],
    }


@router.get("/readout")
async def weekly_readout(db: DbSessionDep) -> dict:
    """Aggregated metrics for Selvon-facing summaries (TRD-LOG-5)."""
    return await aggregate_summary(db)


@router.post("/ingest")
async def trigger_ingest(body: IngestRequest, background_tasks: BackgroundTasks) -> dict:
    manifest = Path(body.manifest_path)
    if not manifest.is_file():
        repo_root = Path(__file__).resolve().parents[2]
        manifest = repo_root / body.manifest_path
    if not manifest.is_file():
        raise HTTPException(status_code=404, detail="manifest not found")

    async def _run() -> None:
        await ingest_manifest(manifest.resolve())

    def _run_sync() -> None:
        asyncio.run(_run())

    background_tasks.add_task(_run_sync)
    return {"status": "accepted", "manifest": str(manifest.resolve())}


@router.get("/routing")
async def routing_config(db: DbSessionDep) -> dict:
    stmt = (
        select(RoutingRule)
        .options(selectinload(RoutingRule.team), selectinload(RoutingRule.policy_type_row))
        .order_by(RoutingRule.policy_type, RoutingRule.priority)
    )
    rules = (await db.execute(stmt)).scalars().all()
    return {
        "rules": [
            {
                "rule_id": str(r.rule_id),
                "policy_type": r.policy_type,
                "policy_display_name": r.policy_type_row.display_name if r.policy_type_row else r.policy_type,
                "team_id": str(r.team_id),
                "team_name": r.team.name,
                "contact_hint": r.team.contact_hint,
                "priority": r.priority,
                "selvon_approved": r.selvon_approved,
                "approved_at": r.approved_at.isoformat() if r.approved_at else None,
            }
            for r in rules
        ],
        "pending_approval_count": sum(1 for r in rules if not r.selvon_approved),
    }


@router.patch("/routing/{rule_id}/approval")
async def set_routing_approval(rule_id: str, body: RoutingApprovalBody, db: DbSessionDep) -> dict:
    import uuid as uuid_mod

    try:
        rid = uuid_mod.UUID(rule_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid rule_id") from exc

    rule = await db.get(RoutingRule, rid)
    if rule is None:
        raise HTTPException(status_code=404, detail="rule not found")

    rule.selvon_approved = body.selvon_approved
    rule.approved_at = datetime.now(timezone.utc) if body.selvon_approved else None
    await db.commit()
    return {"rule_id": rule_id, "selvon_approved": rule.selvon_approved}
