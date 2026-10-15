from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select

from backend.app.core.db import get_session
from backend.app.models.entities import (
    Stage, StageEntry, RaceStatusEnum, SpecialAward, StravaSegment, StravaEffort, Category, Rider, Team
)
from backend.app.services.pdf_service import format_ms_to_time

router = APIRouter(prefix="/stages", tags=["Stages"])


@router.get("")
async def list_stages(session: AsyncSession = Depends(get_session)):
    stmt = select(Stage).order_by(Stage.stage_number)
    stages = (await session.exec(stmt)).all()
    return stages


@router.get("/{slug}")
async def get_stage_by_slug(slug: str, session: AsyncSession = Depends(get_session)):
    stmt = select(Stage).where(Stage.slug == slug)
    stage = (await session.exec(stmt)).first()
    if not stage:
        raise HTTPException(status_code=404, detail="Etapa no encontrada.")

    # Premios especiales
    stmt_aw = select(SpecialAward).where(SpecialAward.stage_id == stage.id)
    awards = (await session.exec(stmt_aw)).all()

    # Segmentos Strava
    stmt_seg = select(StravaSegment).where(StravaSegment.stage_id == stage.id)
    segments = (await session.exec(stmt_seg)).all()
    seg_list = []
    for s in segments:
        stmt_eff = select(StravaEffort).where(StravaEffort.segment_id == s.id).order_by(StravaEffort.elapsed_time_sec)
        efforts = (await session.exec(stmt_eff)).all()
        seg_list.append({
            "segment_id": s.id,
            "strava_segment_id": s.strava_segment_id,
            "name": s.name,
            "distance_m": s.distance_m,
            "average_grade": s.average_grade,
            "efforts": [
                {
                    "athlete_name": e.athlete_name_raw,
                    "elapsed_time_sec": e.elapsed_time_sec,
                    "formatted_time": f"{e.elapsed_time_sec // 60}m {e.elapsed_time_sec % 60:02d}s",
                    "is_kom_qom": e.is_kom_qom
                } for e in efforts
            ]
        })

    # Estadísticas de extremos
    stmt_scratch = (
        select(StageEntry)
        .where(StageEntry.stage_id == stage.id, StageEntry.race_status == RaceStatusEnum.FINISHED, StageEntry.finish_elapsed_ms.is_not(None))
        .order_by(StageEntry.finish_elapsed_ms.asc())
    )
    scratch_entry = (await session.exec(stmt_scratch)).first()

    stmt_farolito = (
        select(StageEntry)
        .where(StageEntry.stage_id == stage.id, StageEntry.race_status == RaceStatusEnum.FINISHED, StageEntry.finish_elapsed_ms.is_not(None))
        .order_by(StageEntry.finish_elapsed_ms.desc())
    )
    farolito_entry = (await session.exec(stmt_farolito)).first()

    scratch_data = None
    if scratch_entry:
        await session.refresh(scratch_entry, ["rider", "category", "team"])
        scratch_data = {
            "bib_number": scratch_entry.bib_number,
            "rider_name": scratch_entry.rider.full_name if scratch_entry.rider else "",
            "category_name": scratch_entry.category.name if scratch_entry.category else "",
            "team_name": scratch_entry.team.name if scratch_entry.team else "LIBRE",
            "elapsed_ms": scratch_entry.finish_elapsed_ms,
            "formatted_time": format_ms_to_time(scratch_entry.finish_elapsed_ms or 0)
        }

    farolito_data = None
    if farolito_entry:
        await session.refresh(farolito_entry, ["rider", "category", "team"])
        farolito_data = {
            "bib_number": farolito_entry.bib_number,
            "rider_name": farolito_entry.rider.full_name if farolito_entry.rider else "",
            "category_name": farolito_entry.category.name if farolito_entry.category else "",
            "team_name": farolito_entry.team.name if farolito_entry.team else "LIBRE",
            "elapsed_ms": farolito_entry.finish_elapsed_ms,
            "formatted_time": format_ms_to_time(farolito_entry.finish_elapsed_ms or 0)
        }

    return {
        "stage": stage,
        "awards": awards,
        "strava_segments": seg_list,
        "extremes": {
            "scratch": scratch_data,
            "farolito": farolito_data
        }
    }


@router.get("/{slug}/results")
async def get_stage_results(slug: str, session: AsyncSession = Depends(get_session)):
    stmt = select(Stage).where(Stage.slug == slug)
    stage = (await session.exec(stmt)).first()
    if not stage:
        raise HTTPException(status_code=404, detail="Etapa no encontrada.")

    stmt_entries = (
        select(StageEntry)
        .where(StageEntry.stage_id == stage.id)
        .order_by(StageEntry.category_id, StageEntry.category_rank)
    )
    entries = (await session.exec(stmt_entries)).all()

    by_category: Dict[str, List[Dict[str, Any]]] = {}
    for e in entries:
        await session.refresh(e, ["rider", "category", "team"])
        cat_name = e.category.name if e.category else "Sin Categoría"
        by_category.setdefault(cat_name, []).append({
            "bib_number": e.bib_number,
            "rider_name": e.rider.full_name if e.rider else "",
            "rider_slug": e.rider.slug if e.rider else "",
            "team_name": e.team.name if e.team else "LIBRE",
            "team_slug": e.team.slug if e.team else None,
            "rank": e.category_rank,
            "status": e.race_status,
            "elapsed_ms": e.finish_elapsed_ms,
            "formatted_time": format_ms_to_time(e.finish_elapsed_ms or 0) if e.finish_elapsed_ms else "-",
            "points_earned": e.points_earned
        })

    return {
        "stage": stage,
        "categories": by_category
    }
