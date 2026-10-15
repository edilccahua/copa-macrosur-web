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
    stmt = select(Team).where(Team.slug == slug)
    team = (await session.exec(stmt)).first()
    if not team:
        raise HTTPException(status_code=404, detail="Equipo no encontrado.")

    # Standing
    stmt_stand = select(TeamChampionshipStanding).where(TeamChampionshipStanding.team_id == team.id)
    stand = (await session.exec(stmt_stand)).first()

    # Plantilla de ciclistas activos
    stmt_riders = select(Rider).where(Rider.team_id == team.id)
    riders = (await session.exec(stmt_riders)).all()

    roster = []
    for r in riders:
        # Puntos sumados por el corredor
        stmt_entries = select(StageEntry, Category).join(Category).where(StageEntry.rider_id == r.id)
        entries_res = await session.exec(stmt_entries)
        r_points = sum(e.points_earned for e, c in entries_res.all())
        cats = list({c.name for e, c in (await session.exec(stmt_entries)).all()})

        roster.append({
            "rider_id": r.id,
            "full_name": r.full_name,
            "slug": r.slug,
            "gender": r.gender,
            "categories": cats,
            "points_contributed": r_points
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
        "roster": roster
    }
