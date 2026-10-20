from typing import List, Dict, Any, Optional
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select
from backend.app.models.entities import (
    StageEntry, RaceStatusEnum, ChampionshipStanding,
    TeamStageStanding, TeamChampionshipStanding, Rider, Category, Team
)


def calculate_points_for_rank(rank: Optional[int], race_status: RaceStatusEnum) -> int:
    """
    Escala oficial de 10 puntos (specs/01 §3.1):
    1°: 10, 2°: 9, 3°: 8, 4°: 7, 5°: 6, 6°: 5, 7°: 4, 8°: 3, 9°: 2, 10°: 1
    11° en adelante: 1 pt por completar
    DNF, DNS, DSQ o sin clasificar: 0 pts
    """
    if race_status != RaceStatusEnum.FINISHED or rank is None or rank <= 0:
        return 0
    if rank == 1:
        return 10
    elif rank == 2:
        return 9
    elif rank == 3:
        return 8
    elif rank == 4:
        return 7
    elif rank == 5:
        return 6
    elif rank == 6:
        return 5
    elif rank == 7:
        return 4
    elif rank == 8:
        return 3
    elif rank == 9:
        return 2
    elif rank >= 10:
        return 1
    return 0


async def merge_duplicate_entries(session: AsyncSession, stage_id: int) -> int:
    """
    Fusiona identidades duplicadas dentro de una misma fecha: si un mismo Rider quedó
    con más de un StageEntry (distintos dorsales/categorías por datos sucios de origen),
    conserva el MEJOR resultado (menor finish_elapsed_ms; si no hay tiempo, menor dorsal)
    y elimina el resto. Devuelve el número de entradas fusionadas (eliminadas).
    """
    stmt = select(StageEntry).where(StageEntry.stage_id == stage_id)
    entries = (await session.exec(stmt)).all()

    by_rider: Dict[int, List[StageEntry]] = {}
    for e in entries:
        by_rider.setdefault(e.rider_id, []).append(e)

    merged = 0
    for _rider_id, group in by_rider.items():
        if len(group) <= 1:
            continue
        group.sort(key=lambda e: (
            e.finish_elapsed_ms if e.finish_elapsed_ms is not None else 10 ** 15,
            e.bib_number,
        ))
        for loser in group[1:]:
            await session.delete(loser)
            merged += 1

    if merged:
        await session.commit()
    return merged


async def recalculate_stage_ranks(session: AsyncSession, stage_id: int) -> None:
    """
    Ordena los finalistas por categoría en una fecha por tiempo neto (finish_elapsed_ms ASC)
    y asigna puestos y puntos de esa fecha.
    """
    stmt = (
        select(StageEntry)
        .where(StageEntry.stage_id == stage_id)
        .order_by(StageEntry.category_id, StageEntry.finish_elapsed_ms)
    )
    result = await session.exec(stmt)
    entries = result.all()

    # Agrupar por categoría
    by_category: Dict[int, List[StageEntry]] = {}
    for entry in entries:
        by_category.setdefault(entry.category_id, []).append(entry)

    for cat_id, cat_entries in by_category.items():
        # Separar terminados de no terminados
        finished = [e for e in cat_entries if e.race_status == RaceStatusEnum.FINISHED and e.finish_elapsed_ms is not None]
        finished.sort(key=lambda x: x.finish_elapsed_ms)

        for rank, entry in enumerate(finished, start=1):
            entry.category_rank = rank
            entry.points_earned = calculate_points_for_rank(rank, entry.race_status)
            session.add(entry)

        # No terminados
        not_finished = [e for e in cat_entries if e.race_status != RaceStatusEnum.FINISHED or e.finish_elapsed_ms is None]
        for entry in not_finished:
            entry.category_rank = None
            entry.points_earned = 0
            session.add(entry)

    await session.commit()


async def recalculate_championship_standings(session: AsyncSession) -> None:
    """
    Recalcula la tabla acumulada individual por categoría aplicando el desempate UCI:
    1. total_points DESC
    2. first_places_count DESC
    3. last_stage_rank ASC
    4. total_elapsed_ms ASC
    """
    # Obtener todas las inscripciones finalizadas ordenadas por fecha/stage
    stmt = (
        select(StageEntry)
        .where(StageEntry.race_status == RaceStatusEnum.FINISHED)
        .order_by(StageEntry.category_id, StageEntry.stage_id)
    )
    result = await session.exec(stmt)
    entries = result.all()

    # Clave: (rider_id, category_id)
    rider_cat_data: Dict[tuple, Dict[str, Any]] = {}

    for entry in entries:
        key = (entry.rider_id, entry.category_id)
        if key not in rider_cat_data:
            rider_cat_data[key] = {
                "rider_id": entry.rider_id,
                "category_id": entry.category_id,
                "total_points": 0,
                "first_places_count": 0,
                "last_stage_rank": None,
                "last_stage_id": 0,
                "total_elapsed_ms": 0,
                "stages_completed": 0,
            }

        data = rider_cat_data[key]
        data["total_points"] += entry.points_earned
        if entry.category_rank == 1:
            data["first_places_count"] += 1
        data["total_elapsed_ms"] += (entry.finish_elapsed_ms or 0)
        data["stages_completed"] += 1

        # Registrar el puesto de la última fecha disputada
        if entry.stage_id >= data["last_stage_id"]:
            data["last_stage_id"] = entry.stage_id
            data["last_stage_rank"] = entry.category_rank

    # Agrupar por categoría para clasificar
    by_category: Dict[int, List[Dict[str, Any]]] = {}
    for data in rider_cat_data.values():
        by_category.setdefault(data["category_id"], []).append(data)

    # Criterio de desempate UCI
    for cat_id, riders_list in by_category.items():
        riders_list.sort(
            key=lambda x: (
                -x["total_points"],
                -x["first_places_count"],
                x["last_stage_rank"] if x["last_stage_rank"] is not None else 999999,
                x["total_elapsed_ms"]
            )
        )

        for rank, item in enumerate(riders_list, start=1):
            stmt_stand = select(ChampionshipStanding).where(
                ChampionshipStanding.rider_id == item["rider_id"],
                ChampionshipStanding.category_id == cat_id
            )
            stand_res = await session.exec(stmt_stand)
            standing = stand_res.first()

            if not standing:
                standing = ChampionshipStanding(
                    rider_id=item["rider_id"],
                    category_id=cat_id,
                    current_rank=rank,
                    previous_rank=None,
                    rank_delta=0
                )
            else:
                standing.previous_rank = standing.current_rank
                standing.rank_delta = (standing.previous_rank - rank) if standing.previous_rank else 0
                standing.current_rank = rank

            standing.total_points = item["total_points"]
            standing.first_places_count = item["first_places_count"]
            standing.last_stage_rank = item["last_stage_rank"]
            standing.total_elapsed_ms = item["total_elapsed_ms"]
            standing.stages_completed = item["stages_completed"]

            session.add(standing)

    # Limpieza de clasificaciones obsoletas: si un corredor dejó de tener resultados
    # (p.ej. se corrigió un dorsal o se retiró de una categoría), su fila debe
    # desaparecer para que la tabla refleje exactamente la realidad de la BD.
    valid_pairs = set(rider_cat_data.keys())
    stmt_all_stand = select(ChampionshipStanding)
    all_stands = (await session.exec(stmt_all_stand)).all()
    for st in all_stands:
        if (st.rider_id, st.category_id) not in valid_pairs:
            await session.delete(st)

    await session.commit()


async def recalculate_team_standings(session: AsyncSession, stage_id: Optional[int] = None) -> None:
    """
    Recalcula la clasificación de equipos por fecha y acumulada con desempate Olímpico:
    1. total_points DESC
    2. first_places_count DESC (oros)
    3. second_places_count DESC (platas)
    4. third_places_count DESC (bronces)
    5. total_riders_participations DESC
    6. total_elapsed_ms ASC
    """
    # 1. Puntos por fecha (TeamStageStanding)
    stmt_stages = select(StageEntry).where(
        StageEntry.team_id.is_not(None),
        StageEntry.race_status == RaceStatusEnum.FINISHED
    )
    if stage_id:
        stmt_stages = stmt_stages.where(StageEntry.stage_id == stage_id)

    res = await session.exec(stmt_stages)
    entries = res.all()

    # (stage_id, team_id) -> stats
    stage_teams: Dict[tuple, Dict[str, Any]] = {}
    for entry in entries:
        if not entry.team_id:
            continue
        key = (entry.stage_id, entry.team_id)
        if key not in stage_teams:
            stage_teams[key] = {
                "stage_id": entry.stage_id,
                "team_id": entry.team_id,
                "points_earned": 0,
                "first_places_count": 0,
                "second_places_count": 0,
                "riders_scored_count": 0
            }
        st = stage_teams[key]
        st["points_earned"] += entry.points_earned
        if entry.points_earned > 0:
            st["riders_scored_count"] += 1
        if entry.category_rank == 1:
            st["first_places_count"] += 1
        elif entry.category_rank == 2:
            st["second_places_count"] += 1

    for key, data in stage_teams.items():
        stmt_ts = select(TeamStageStanding).where(
            TeamStageStanding.stage_id == data["stage_id"],
            TeamStageStanding.team_id == data["team_id"]
        )
        ts_res = await session.exec(stmt_ts)
        ts = ts_res.first()
        if not ts:
            ts = TeamStageStanding(**data)
        else:
            ts.points_earned = data["points_earned"]
            ts.first_places_count = data["first_places_count"]
            ts.second_places_count = data["second_places_count"]
            ts.riders_scored_count = data["riders_scored_count"]
        session.add(ts)

    await session.commit()

    # 2. Copa de Equipos Acumulada (TeamChampionshipStanding)
    stmt_all = select(StageEntry).where(
        StageEntry.team_id.is_not(None),
        StageEntry.race_status == RaceStatusEnum.FINISHED
    )
    all_res = await session.exec(stmt_all)
    all_entries = all_res.all()

    teams_accum: Dict[int, Dict[str, Any]] = {}
    for entry in all_entries:
        t_id = entry.team_id
        if not t_id:
            continue
        if t_id not in teams_accum:
            teams_accum[t_id] = {
                "team_id": t_id,
                "total_points": 0,
                "first_places_count": 0,
                "second_places_count": 0,
                "third_places_count": 0,
                "total_riders_participations": 0,
                "total_elapsed_ms": 0
            }
        ta = teams_accum[t_id]
        ta["total_points"] += entry.points_earned
        if entry.category_rank == 1:
            ta["first_places_count"] += 1
        elif entry.category_rank == 2:
            ta["second_places_count"] += 1
        elif entry.category_rank == 3:
            ta["third_places_count"] += 1
        ta["total_riders_participations"] += 1
        ta["total_elapsed_ms"] += (entry.finish_elapsed_ms or 0)

    # Ordenar según desempate olímpico
    teams_sorted = list(teams_accum.values())
    teams_sorted.sort(
        key=lambda x: (
            -x["total_points"],
            -x["first_places_count"],
            -x["second_places_count"],
            -x["third_places_count"],
            -x["total_riders_participations"],
            x["total_elapsed_ms"]
        )
    )

    for rank, data in enumerate(teams_sorted, start=1):
        stmt_tc = select(TeamChampionshipStanding).where(TeamChampionshipStanding.team_id == data["team_id"])
        tc_res = await session.exec(stmt_tc)
        tc = tc_res.first()
        if not tc:
            tc = TeamChampionshipStanding(
                team_id=data["team_id"],
                current_rank=rank,
                previous_rank=None,
                rank_delta=0
            )
        else:
            tc.previous_rank = tc.current_rank
            tc.rank_delta = (tc.previous_rank - rank) if tc.previous_rank else 0
            tc.current_rank = rank

        tc.total_points = data["total_points"]
        tc.first_places_count = data["first_places_count"]
        tc.second_places_count = data["second_places_count"]
        tc.third_places_count = data["third_places_count"]
        tc.total_riders_participations = data["total_riders_participations"]
        tc.total_elapsed_ms = data["total_elapsed_ms"]

        session.add(tc)

    await session.commit()
