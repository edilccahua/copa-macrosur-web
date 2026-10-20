from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select

from backend.app.core.db import get_session
from backend.app.models.entities import Rider, StageEntry, Stage, ChampionshipStanding, Category, Team
from backend.app.services.pdf_service import format_ms_to_time

router = APIRouter(prefix="/riders", tags=["Riders"])


@router.get("")
async def search_riders(
    q: Optional[str] = Query(None, description="Búsqueda por nombre o DNI"),
    limit: int = Query(50, ge=1, le=1000, description="Máximo de resultados"),
    session: AsyncSession = Depends(get_session)
):
    # El equipo del corredor se trae en la MISMA consulta: recargarlo por
    # cada fila era un N+1 (con 50 resultados, 50 consultas de más).
    stmt = (
        select(Rider, Team)
        .outerjoin(Team, Rider.team_id == Team.id)
        .order_by(Rider.id)
    )
    if q:
        stmt = stmt.where(Rider.full_name.ilike(f"%{q}%") | Rider.dni.ilike(f"%{q}%"))
    stmt = stmt.limit(limit)
    riders = (await session.exec(stmt)).all()

    output = []
    for r, team in riders:
        output.append({
            "id": r.id,
            "full_name": r.full_name,
            "slug": r.slug,
            "team_name": team.name if team else "LIBRE",
            "gender": r.gender
        })
    return output


@router.get("/{slug}")
async def get_rider_profile(slug: str, session: AsyncSession = Depends(get_session)):
    """La ficha pública de un corredor.

    Las tres consultas que necesita el perfil (corredor y equipo, clasificación
    acumulada con su categoría, e historial de fechas) se hacen UNA cada una:
    antes el `refresh` del corredor cargaba el equipo y las clasificaciones
    por separado, y la categoría de cada clasificación se pedía con un
    `SELECT` POR FILA (un N+1).
    """
    # El corredor y su equipo salen juntos: el `team` del corredor es la
    # relación que se proyectaba fila a fila.
    stmt = (
        select(Rider, Team)
        .outerjoin(Team, Rider.team_id == Team.id)
        .where(Rider.slug == slug)
    )
    fila = (await session.exec(stmt)).first()
    if fila is None:
        raise HTTPException(status_code=404, detail="Ciclista no encontrado.")
    rider, team = fila

    # Enmascarar DNI: ej. '***4567'
    masked_dni = f"***{rider.dni[-4:]}" if len(rider.dni) >= 4 else "***"

    # Historial de participaciones en etapas
    stmt_entries = (
        select(StageEntry, Stage, Category)
        .join(Stage, StageEntry.stage_id == Stage.id)
        .join(Category, StageEntry.category_id == Category.id)
        .where(StageEntry.rider_id == rider.id)
        .order_by(Stage.stage_number)
    )
    entries_res = await session.exec(stmt_entries)

    history = []
    for entry, stage, cat in entries_res.all():
        history.append({
            "stage_number": stage.stage_number,
            "stage_name": stage.name,
            "stage_slug": stage.slug,
            "category_name": cat.name,
            "bib_number": entry.bib_number,
            "status": entry.race_status,
            "rank": entry.category_rank,
            "elapsed_ms": entry.finish_elapsed_ms,
            "formatted_time": format_ms_to_time(entry.finish_elapsed_ms or 0) if entry.finish_elapsed_ms else "-",
            "points_earned": entry.points_earned
        })

    # Ranking individual acumulado: la categoría de cada fila viene en la
    # misma consulta (antes era un `SELECT` por cada clasificación).
    stmt_standings = (
        select(ChampionshipStanding, Category)
        .outerjoin(Category, ChampionshipStanding.category_id == Category.id)
        .where(ChampionshipStanding.rider_id == rider.id)
        .order_by(ChampionshipStanding.id)
    )
    standings_res = await session.exec(stmt_standings)

    standings_info = []
    for st, cat in standings_res.all():
        standings_info.append({
            "category_name": cat.name if cat else "",
            "total_points": st.total_points,
            "current_rank": st.current_rank,
            "rank_delta": st.rank_delta,
            "first_places_count": st.first_places_count,
            "total_elapsed_ms": st.total_elapsed_ms,
            "formatted_total_time": format_ms_to_time(st.total_elapsed_ms)
        })

    return {
        "rider": {
            "id": rider.id,
            "full_name": rider.full_name,
            "slug": rider.slug,
            "masked_dni": masked_dni,
            "team_name": team.name if team else "LIBRE",
            "team_slug": team.slug if team else None,
            "gender": rider.gender,
            "avatar_url": rider.avatar_url
        },
        "standings": standings_info,
        "history": history
    }
