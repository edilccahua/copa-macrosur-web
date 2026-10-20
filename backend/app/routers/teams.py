from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select

from backend.app.core.db import get_session
from backend.app.models.entities import Team, TeamChampionshipStanding, Rider, StageEntry, Category
from backend.app.services.pdf_service import format_ms_to_time

router = APIRouter(prefix="/teams", tags=["Teams"])


@router.get("")
async def list_teams(session: AsyncSession = Depends(get_session)):
    stmt = (
        select(Team, TeamChampionshipStanding)
        .outerjoin(TeamChampionshipStanding, Team.id == TeamChampionshipStanding.team_id)
        .order_by(TeamChampionshipStanding.current_rank.asc())
    )
    res = await session.exec(stmt)
    output = []
    for team, stand in res.all():
        output.append({
            "id": team.id,
            "name": team.name,
            "slug": team.slug,
            "logo_url": team.logo_url,
            "current_rank": stand.current_rank if stand else None,
            "rank_delta": stand.rank_delta if stand else 0,
            "total_points": stand.total_points if stand else 0,
            "first_places_count": stand.first_places_count if stand else 0,
            "second_places_count": stand.second_places_count if stand else 0,
            "third_places_count": stand.third_places_count if stand else 0
        })
    return output


@router.get("/{slug}")
async def get_team_profile(slug: str, session: AsyncSession = Depends(get_session)):
    """La ficha pública de un equipo.

    La plantilla se resuelve con DOS consultas en vez de dos por corredor:
    antes, por cada corredor de la plantilla se ejecutaba la MISMA consulta
    de sus inscripciones dos veces (una para los puntos y otra para las
    categorías).
    """
    # El equipo y su clasificación acumulada salen en la misma consulta.
    stmt = (
        select(Team, TeamChampionshipStanding)
        .outerjoin(TeamChampionshipStanding, Team.id == TeamChampionshipStanding.team_id)
        .where(Team.slug == slug)
    )
    fila = (await session.exec(stmt)).first()
    if fila is None:
        raise HTTPException(status_code=404, detail="Equipo no encontrado.")
    team, stand = fila

    # Plantilla de ciclistas del equipo con sus puntos y sus categorías: una
    # sola consulta, con `JOIN` a las inscripciones y a su categoría.
    #
    # El `OUTER JOIN` conserva a los corredores del equipo que todavía no
    # han corrido ninguna fecha (aparecen con 0 puntos y sin categorías).
    stmt_plantilla = (
        select(Rider, StageEntry, Category)
        .outerjoin(StageEntry, StageEntry.rider_id == Rider.id)
        .outerjoin(Category, StageEntry.category_id == Category.id)
        .where(Rider.team_id == team.id)
        .order_by(Rider.id, StageEntry.id)
    )
    plantilla = (await session.exec(stmt_plantilla)).all()

    # Se agrupa en Python: una fila por corredor, con la suma de sus puntos y
    # el conjunto de sus categorías.
    roster = []
    puntos_por_corredor: dict[int, int] = {}
    categorias_por_corredor: dict[int, List[str]] = {}
    for rider, entry, cat in plantilla:
        if rider.id not in puntos_por_corredor:
            puntos_por_corredor[rider.id] = 0
            categorias_por_corredor[rider.id] = []
            roster.append(rider)
        # Una inscripción sin categoría no computa: es lo que hacía el JOIN
        # interior de antes (y evita que un dato roto altere los puntos).
        if entry is not None and cat is not None:
            puntos_por_corredor[rider.id] += entry.points_earned or 0
            if cat.name not in categorias_por_corredor[rider.id]:
                categorias_por_corredor[rider.id].append(cat.name)

    plantilla_final = []
    for rider in roster:
        plantilla_final.append({
            "rider_id": rider.id,
            "full_name": rider.full_name,
            "slug": rider.slug,
            "gender": rider.gender,
            # Las categorías se ordenan por nombre: antes salían en el orden
            # arbitrario de un `set`, que cambiaba en cada arranque del
            # proceso.
            "categories": sorted(categorias_por_corredor[rider.id]),
            "points_contributed": puntos_por_corredor[rider.id]
        })

    return {
        "team": {
            "id": team.id,
            "name": team.name,
            "slug": team.slug,
            "logo_url": team.logo_url,
            "description": team.description
        },
        "standing": {
            "current_rank": stand.current_rank if stand else None,
            "previous_rank": stand.previous_rank if stand else None,
            "rank_delta": stand.rank_delta if stand else 0,
            "total_points": stand.total_points if stand else 0,
            "first_places": stand.first_places_count if stand else 0,
            "second_places": stand.second_places_count if stand else 0,
            "third_places": stand.third_places_count if stand else 0,
            "total_riders_participations": stand.total_riders_participations if stand else 0,
            "total_elapsed_ms": stand.total_elapsed_ms if stand else 0,
            "formatted_total_time": format_ms_to_time(stand.total_elapsed_ms) if stand else "-"
        },
        "roster": plantilla_final
    }
