from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select

from backend.app.core.db import get_session
from backend.app.models.entities import (
    Stage, StageEntry, RaceStatusEnum, SpecialAward, StravaSegment, StravaEffort, Category, Rider, Team
)
from backend.app.services.pdf_service import format_ms_to_time
from backend.app.services.stage_summary_service import (
    compute_category_podium,
    compute_stage_awards,
    compute_stage_checkpoints,
    compute_stage_extremes,
    compute_stage_mountain_titles,
    compute_stage_route_profile,
    compute_stage_stats,
    compute_stage_strava,
    compute_stage_summits,
    compute_stage_team_podium,
)

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


@router.get("/{slug}/summary")
async def get_stage_summary(slug: str, session: AsyncSession = Depends(get_session)):
    """
    Agregado de presentación de una fecha para la ficha `/fechas/[slug]`.

    Devuelve en UNA llamada todo lo que la página muestra: cifras de la
    jornada, podio por categoría, podio de equipos de la jornada, segmentos
    Strava con sus mejores tiempos, checkpoints, premios con su ganador y los
    extremos (scratch / farolito). La página no recalcula nada.
    """
    stmt = select(Stage).where(Stage.slug == slug)
    stage = (await session.exec(stmt)).first()
    if not stage:
        raise HTTPException(status_code=404, detail="Etapa no encontrada.")

    # Fechas vecinas en el calendario, para la navegación prev/next.
    prev_stage = (
        await session.exec(
            select(Stage)
            .where(Stage.stage_number < stage.stage_number)
            .order_by(Stage.stage_number.desc())
        )
    ).first()
    next_stage = (
        await session.exec(
            select(Stage)
            .where(Stage.stage_number > stage.stage_number)
            .order_by(Stage.stage_number)
        )
    ).first()

    mountain_titles = await compute_stage_mountain_titles(session, stage.id)

    return {
        "stage": stage,
        "stats": await compute_stage_stats(session, stage.id),
        "podium": await compute_category_podium(session, stage.id),
        "teams": await compute_stage_team_podium(session, stage.id),
        "strava": await compute_stage_strava(session, stage.id),
        "checkpoints": await compute_stage_checkpoints(session, stage.id),
        "awards": await compute_stage_awards(session, stage.id),
        "extremes": await compute_stage_extremes(session, stage.id),
        "route_profile": await compute_stage_route_profile(session, stage),
        "summits": await compute_stage_summits(session, stage.id),
        "kom": mountain_titles["kom"],
        "qom": mountain_titles["qom"],
        "navigation": {
            "prev_slug": prev_stage.slug if prev_stage else None,
            "prev_name": prev_stage.title or prev_stage.name if prev_stage else None,
            "next_slug": next_stage.slug if next_stage else None,
            "next_name": next_stage.title or next_stage.name if next_stage else None,
        },
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
        .order_by(
            StageEntry.category_id,
            StageEntry.category_rank.is_(None),
            StageEntry.category_rank.asc()
        )
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

    # Finalistas primero (por puesto), no finalistas al final
    for cat_name, rows in by_category.items():
        rows.sort(key=lambda r: (r["rank"] is None, r["rank"] if r["rank"] is not None else 9999))

    return {
        "stage": stage,
        "categories": by_category
    }
