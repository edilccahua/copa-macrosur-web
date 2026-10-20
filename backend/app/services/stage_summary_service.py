"""
Servicio de resumen de una fecha — la fuente de datos de `/fechas/[slug]`.

Agrega, en una sola pasada de consulta, todo lo que la ficha de una carrera
muestra: cifras de la jornada, podio por categoría, podio de equipos, segmentos
Strava con sus mejores tiempos, checkpoints, premios y los extremos (scratch /
farolito).

Reglas de dominio (specs/01 §3.1, specs/03 §1.2):
  · `Stage.distance_km` y `Stage.elevation_gain_m` son **POR VUELTA**. Los
    totales de carrera se derivan multiplicando por `Stage.laps`. Una fecha
    disputada sin vueltas tiene `laps = 1` y ambos coinciden.
  · El puesto de un corredor es `StageEntry.category_rank`, ya calculado por el
    motor de scoring: el PDF oficial manda y aquí no se recalcula.
  · Una fecha no disputada no tiene cifras: los agregados返回 `None`, no 0.
"""
from typing import Dict, List, Optional

from sqlalchemy import Integer, func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from backend.app.models.entities import (
    Category,
    Checkpoint,
    RaceStatusEnum,
    Rider,
    RouteSummit,
    SpecialAward,
    Stage,
    StageEntry,
    StageStatusEnum,
    StravaEffort,
    StravaSegment,
    Team,
)
from backend.app.models.schemas import (
    AwardSummaryRead,
    CategoryPodiumRead,
    CheckpointRead,
    MountainTitleRead,
    PodiumEntryRead,
    RouteProfileRead,
    StageStatsRead,
    StravaEffortRead,
    StravaSegmentSummaryRead,
    SummitRead,
    TeamPodiumRead,
)
from backend.app.services.pdf_service import format_ms_to_time
from backend.app.services.route_profile_service import build_route_profile

# Escala de puntos de specs/01 §3.1: 1°=10 … 10°=1, 11°+=1, DNF/DNS/DSQ=0.
_POINTS_TOP10 = [10, 9, 8, 7, 6, 5, 4, 3, 2, 1]

# Cuántos efforts de Strava se exponen por segmento (specs/03 §1.2 punto 5).
_STRAVA_TOP_N = 10


def _points_for_position(position: int) -> int:
    """Puntos de un puesto según la escala de specs/01 §3.1."""
    if position <= 0:
        return 0
    if position <= len(_POINTS_TOP10):
        return _POINTS_TOP10[position - 1]
    return 1


def _normalize_team_name(name: str) -> str:
    """Une el club partido por un salto de línea.

    El PDF oficial corta los nombres largos entre líneas, así que
    'CLUB ORIGINAL BIKES AREQUIPA-' + 'PERÚ' es UN club, no dos
    (INTEGRIDAD-DATOS.md §2.2, caso 3). La misma normalización vive en
    `excel_service.resolve_or_create_team`; aquí se usa solo para agrupar.
    """
    cleaned = " ".join(name.split())
    if cleaned.endswith("-"):
        cleaned = cleaned[:-1]
    return cleaned.strip()


def _merge_split_team_names(names: List[str]) -> Dict[str, str]:
    """Mapea cada nombre de club a la forma canónica del club.

    Un club partido por el PDF queda con un guion pegado al final
    ('CLUB ORIGINAL BIKES AREQUIPA-') y su continuación en la línea siguiente
    ('CLUB ORIGINAL BIKES AREQUIPA-PERÚ'). Ambos son el mismo club: el que
    tiene el guion es un prefijo del otro (INTEGRIDAD-DATOS.md §2.2, caso 3).

    Solo se fusiona cuando el nombre corto termina en guion, que es la marca
    del corte de línea del PDF: dos clubes distintos que comparten prefijo
    ('TEAM COLCA BIKE' y 'TEAM COLCA BIKE 2') no se tocan.

    Devuelve `{nombre_original: nombre_canonico}`.
    """
    canonical: Dict[str, str] = {name: name for name in names}
    # Del más largo al más corto: el nombre completo es el canónico.
    for name in sorted(names, key=len, reverse=True):
        for other in names:
            if other == name or not other.endswith("-"):
                continue
            if len(other) < len(name) and name.startswith(other):
                canonical[other] = name
    return canonical


async def compute_stage_stats(session: AsyncSession, stage_id: int) -> StageStatsRead:
    """Cifras de la jornada: inscripciones, finalizados, puntos y tiempos.

    `distance_km` y `elevation_gain_m` de `Stage` son por vuelta; aquí se
    exponen las dos lecturas (por vuelta y total) para que la página no los
    mezcle.
    """
    stage = (await session.exec(select(Stage).where(Stage.id == stage_id))).first()
    if stage is None:
        raise ValueError(f"Stage {stage_id} no existe")

    totals = (
        await session.exec(
            select(
                func.count(StageEntry.id),
                func.sum(
                    func.cast(StageEntry.finish_elapsed_ms.is_not(None), Integer)
                ),
                func.coalesce(func.sum(StageEntry.points_earned), 0),
            ).where(StageEntry.stage_id == stage_id)
        )
    ).first()
    entries_total = int(totals[0] or 0) if totals else 0
    finishers = int(totals[1] or 0) if totals else 0
    points_total = int(totals[2] or 0) if totals else 0

    # Un único aggregate devuelve el escalar directo en SQLModel, no una tupla.
    winner = (
        await session.exec(
            select(StageEntry.finish_elapsed_ms, StageEntry.laps)
            .where(
                StageEntry.stage_id == stage_id,
                StageEntry.finish_elapsed_ms.is_not(None),
            )
            .order_by(StageEntry.finish_elapsed_ms)
            .limit(1)
        )
    ).first()
    winner_time_ms = int(winner[0]) if winner and winner[0] is not None else None
    # En un circuito por vueltas no todos completan la misma cantidad: la
    # velocidad del ganador se calcula sobre las vueltas que ÉL hizo, no sobre
    # el máximo de vueltas de la fecha.
    winner_laps = int(winner[1]) if winner and winner[1] else 1

    categories_count = (
        await session.exec(
            select(func.count(func.distinct(StageEntry.category_id))).where(
                StageEntry.stage_id == stage_id
            )
        )
    ).first()
    categories = int(categories_count or 0)

    laps = max(1, stage.laps or 1)
    distance_km_total = round(stage.distance_km * laps, 2)
    elevation_m_total = stage.elevation_gain_m * laps

    winner_avg_speed_kmh: Optional[float] = None
    if winner_time_ms and winner_time_ms > 0 and stage.distance_km > 0:
        winner_distance_km = stage.distance_km * max(1, winner_laps)
        hours = winner_time_ms / 3_600_000
        winner_avg_speed_kmh = round(winner_distance_km / hours, 2)

    # Los no finalizados son los que compitieron y no llegaron a meta. En una
    # fecha que todavía no se disputa, `REGISTERED` significa "aún no compite"
    # y no es un abandono.
    disputed = stage.status == StageStatusEnum.FINISHED
    non_finishers = max(0, entries_total - finishers) if disputed else 0

    return StageStatsRead(
        entries_total=entries_total,
        finishers=finishers,
        non_finishers=non_finishers,
        points_total=points_total,
        distance_km_per_lap=stage.distance_km,
        distance_km_total=distance_km_total,
        elevation_m_per_lap=stage.elevation_gain_m,
        elevation_m_total=elevation_m_total,
        laps=laps,
        winner_time_ms=winner_time_ms,
        winner_avg_speed_kmh=winner_avg_speed_kmh,
        categories_count=categories,
    )


async def compute_category_podium(
    session: AsyncSession, stage_id: int
) -> List[CategoryPodiumRead]:
    """Top-3 de cada categoría, ordenado por `category_rank`.

    No recalcula puestos: `StageEntry.category_rank` es la autoridad
    (specs/01 §1.5.2, erratas documentadas en INTEGRIDAD-DATOS.md §5).
    """
    rows = (
        await session.exec(
            select(StageEntry, Category, Rider, Team)
            .join(Category, StageEntry.category_id == Category.id)
            .join(Rider, StageEntry.rider_id == Rider.id)
            .outerjoin(Team, StageEntry.team_id == Team.id)
            .where(
                StageEntry.stage_id == stage_id,
                StageEntry.category_rank.is_not(None),
                StageEntry.category_rank <= 3,
            )
            .order_by(Category.id, StageEntry.category_rank)
        )
    ).all()

    by_category: dict[int, CategoryPodiumRead] = {}
    for entry, category, rider, team in rows:
        bucket = by_category.get(category.id)
        if bucket is None:
            bucket = CategoryPodiumRead(
                category_id=category.id,
                category_name=category.name,
                short_code=category.short_code,
                entries=[],
            )
            by_category[category.id] = bucket
        bucket.entries.append(
            PodiumEntryRead(
                rank=int(entry.category_rank or 0),
                bib_number=entry.bib_number,
                rider_name=rider.full_name,
                rider_slug=rider.slug,
                team_name=team.name if team else "LIBRE",
                team_slug=team.slug if team else None,
                formatted_time=format_ms_to_time(entry.finish_elapsed_ms or 0)
                if entry.finish_elapsed_ms
                else "-",
                points_earned=entry.points_earned or 0,
            )
        )

    return list(by_category.values())


async def compute_stage_team_podium(
    session: AsyncSession, stage_id: int
) -> List[TeamPodiumRead]:
    """Top-3 equipos por puntos sumados en ESTA fecha.

    No es el acumulado del campeonato: son los puntos de la jornada, que es lo
    que define el podio de la carrera (specs/03 §1.2 punto 3).
    """
    rows = (
        await session.exec(
            select(
                Team.id,
                Team.name,
                Team.slug,
                func.coalesce(func.sum(StageEntry.points_earned), 0),
                # Solo los corredores que SUMARON puntos: un corredor con 0
                # puntos no puntuó y no cuenta como corredor del podio.
                func.sum(
                    func.cast(StageEntry.points_earned > 0, Integer)
                ),
                func.min(StageEntry.category_rank),
            )
            .join(StageEntry, StageEntry.team_id == Team.id)
            .where(StageEntry.stage_id == stage_id)
            .group_by(Team.id, Team.name, Team.slug)
            .having(func.coalesce(func.sum(StageEntry.points_earned), 0) > 0)
            .order_by(func.coalesce(func.sum(StageEntry.points_earned), 0).desc())
        )
    ).all()

    raw = [
        {
            "team_id": team_id,
            "team_name": team_name,
            "team_slug": team_slug,
            "points": int(points or 0),
            "riders_counted": int(riders or 0),
            "best_rank": int(best_rank) if best_rank is not None else 999,
        }
        for team_id, team_name, team_slug, points, riders, best_rank in rows
    ]

    # Un club partido por salto de línea puede aparecer dos veces ('...PERÚ' y
    # '...PERÚ' con el guion de la línea anterior): se fusionan sumando sus
    # puntos (INTEGRIDAD-DATOS.md §2.2, caso 3).
    canonical = _merge_split_team_names([t["team_name"] for t in raw])

    merged: Dict[str, TeamPodiumRead] = {}
    for entry in raw:
        name = canonical.get(entry["team_name"], entry["team_name"])
        key = name.casefold()
        if key not in merged:
            merged[key] = TeamPodiumRead(
                team_id=entry["team_id"],
                team_name=name,
                team_slug=entry["team_slug"],
                points=entry["points"],
                riders_counted=entry["riders_counted"],
                best_rank=entry["best_rank"],
            )
            continue
        current = merged[key]
        merged[key] = TeamPodiumRead(
            team_id=current.team_id,
            team_name=current.team_name,
            team_slug=current.team_slug,
            points=current.points + entry["points"],
            riders_counted=current.riders_counted + entry["riders_counted"],
            best_rank=min(current.best_rank, entry["best_rank"]),
        )

    return sorted(merged.values(), key=lambda t: (-t.points, t.team_name))[:3]


async def compute_stage_strava(
    session: AsyncSession, stage_id: int
) -> List[StravaSegmentSummaryRead]:
    """Segmentos Strava de la fecha con sus 10 mejores tiempos y el KOM.

    El flag `is_kom_qom` de la BD es la autoridad del KOM (specs/02 §4).
    """
    segments = (
        await session.exec(
            select(StravaSegment)
            .where(StravaSegment.stage_id == stage_id)
            .order_by(StravaSegment.id)
        )
    ).all()
    if not segments:
        return []

    # Los esfuerzos de TODOS los segmentos se cargan de una vez: consultarlos
    # uno por uno es un N+1 (una consulta extra por cada segmento).
    segment_ids = [segment.id for segment in segments]
    efforts = (
        await session.exec(
            select(StravaEffort)
            .where(StravaEffort.segment_id.in_(segment_ids))
            .order_by(StravaEffort.segment_id, StravaEffort.elapsed_time_sec)
        )
    ).all()

    by_segment: Dict[int, List[StravaEffort]] = {}
    for effort in efforts:
        by_segment.setdefault(effort.segment_id, []).append(effort)

    summaries: List[StravaSegmentSummaryRead] = []
    for segment in segments:
        effort_reads = [
            StravaEffortRead(
                athlete_name=effort.athlete_name_raw or "—",
                elapsed_time_sec=int(effort.elapsed_time_sec or 0),
                formatted_time=format_ms_to_time(int(effort.elapsed_time_sec or 0) * 1000),
                is_kom_qom=bool(effort.is_kom_qom),
            )
            for effort in by_segment.get(segment.id, [])
        ]

        # El KOM es el effort que la BD marca como tal. Si ninguno lo está,
        # no hay KOM: no se inventa un récord oficial (el mejor tiempo sigue
        # visible en `efforts`).
        kom = next((e for e in effort_reads if e.is_kom_qom), None)

        summaries.append(
            StravaSegmentSummaryRead(
                strava_segment_id=str(segment.strava_segment_id or ""),
                name=segment.name or "",
                distance_m=float(segment.distance_m or 0),
                average_grade=float(segment.average_grade or 0),
                distance_km=round(float(segment.distance_m or 0) / 1000, 2),
                efforts=effort_reads[:_STRAVA_TOP_N],
                kom=kom,
                kind=segment.kind or "FLAT",
                location=segment.location,
                elevation_min_m=segment.elevation_min_m,
                elevation_max_m=segment.elevation_max_m,
            )
        )

    return summaries


async def compute_stage_mountain_titles(
    session: AsyncSession, stage_id: int
) -> Dict[str, Any]:
    """El King of the Mountain y la Queen of the Mountain de la fecha.

    El **KOM** es el segmento de **subida** más empinado: la pendiente media
    positiva más alta y, a igualdad, el más largo. El **QOM** es el de
    **bajada** más empinada: la pendiente media negativa más pronunciada y, a
    igualdad, el más largo.

    El corredor que acompaña a cada título es el más rápido de ese segmento.
    """
    segments = (
        await session.exec(
            select(StravaSegment)
            .where(StravaSegment.stage_id == stage_id)
            .order_by(StravaSegment.id)
        )
    ).all()
    if not segments:
        return {"kom": None, "qom": None}

    segment_ids = [segment.id for segment in segments]
    efforts = (
        await session.exec(
            select(StravaEffort)
            .where(StravaEffort.segment_id.in_(segment_ids))
            .order_by(StravaEffort.segment_id, StravaEffort.elapsed_time_sec)
        )
    ).all()

    best_effort: Dict[int, StravaEffort] = {}
    for effort in efforts:
        if effort.segment_id not in best_effort:
            best_effort[effort.segment_id] = effort

    def _title(segment: StravaSegment) -> Optional[MountainTitleRead]:
        effort = best_effort.get(segment.id)
        if effort is None:
            return None
        seconds = int(effort.elapsed_time_sec or 0)
        return MountainTitleRead(
            strava_segment_id=str(segment.strava_segment_id or ""),
            segment_name=segment.name or "",
            location=segment.location,
            distance_km=round(float(segment.distance_m or 0) / 1000, 2),
            average_grade=float(segment.average_grade or 0),
            elevation_min_m=segment.elevation_min_m,
            elevation_max_m=segment.elevation_max_m,
            athlete_name=effort.athlete_name_raw or "—",
            formatted_time=format_ms_to_time(seconds * 1000),
            elapsed_time_sec=seconds,
        )

    climbs = [s for s in segments if float(s.average_grade or 0) > 0]
    descents = [s for s in segments if float(s.average_grade or 0) < 0]

    kom_segment = None
    if climbs:
        kom_segment = max(
            climbs,
            key=lambda s: (float(s.average_grade or 0), float(s.distance_m or 0)),
        )
    qom_segment = None
    if descents:
        qom_segment = min(
            descents,
            key=lambda s: (float(s.average_grade or 0), -float(s.distance_m or 0)),
        )

    return {
        "kom": _title(kom_segment) if kom_segment else None,
        "qom": _title(qom_segment) if qom_segment else None,
    }


async def compute_stage_summits(
    session: AsyncSession, stage_id: int
) -> List[SummitRead]:
    """Las cimas de la ruta: los «puertos» del perfil de etapa."""
    rows = (
        await session.exec(
            select(RouteSummit)
            .where(RouteSummit.stage_id == stage_id)
            .order_by(RouteSummit.distance_km)
        )
    ).all()
    return [
        SummitRead(
            name=summit.name,
            category=summit.category or "",
            distance_km=summit.distance_km,
            elevation_m=summit.elevation_m,
            climb_gain_m=summit.climb_gain_m,
            avg_grade_pct=summit.avg_grade_pct,
            max_grade_pct=summit.max_grade_pct,
            lat=summit.lat,
            lon=summit.lon,
            name_source=summit.name_source or "geo",
        )
        for summit in rows
    ]


async def compute_stage_route_profile(
    session: AsyncSession, stage: Stage
) -> Optional[RouteProfileRead]:
    """El perfil de altimetría de la ruta, con su traza punto a punto.

    Sale de la geometría real (`route_geojson`), no de multiplicar la
    distancia por las vueltas: en un circuito por vueltas la geometría es de
    UNA vuelta y `geometry_covers_full_stage` lo avisa.
    """
    profile = build_route_profile(stage.route_geojson, stage_laps=stage.laps or 1)
    if profile is None:
        return None
    return RouteProfileRead(**profile)


async def compute_stage_checkpoints(
    session: AsyncSession, stage_id: int
) -> List[CheckpointRead]:
    """Checkpoints de la fecha: Partida, intermedios y Meta, en orden."""
    rows = (
        await session.exec(
            select(Checkpoint)
            .where(Checkpoint.stage_id == stage_id)
            .order_by(Checkpoint.order_index)
        )
    ).all()
    return [
        CheckpointRead(
            name=cp.name,
            order_index=cp.order_index,
            distance_from_start_km=cp.distance_from_start_km,
            is_finish_line=cp.is_finish_line,
        )
        for cp in rows
    ]


async def compute_stage_awards(
    session: AsyncSession, stage_id: int
) -> List[AwardSummaryRead]:
    """Premios de la fecha con su ganador resuelto desde `winner_rider_id`."""
    awards = (
        await session.exec(
            select(SpecialAward)
            .where(SpecialAward.stage_id == stage_id)
            .order_by(SpecialAward.id)
        )
    ).all()
    if not awards:
        return []

    winner_ids = [a.winner_rider_id for a in awards if a.winner_rider_id]
    names: dict[int, str] = {}
    if winner_ids:
        riders = (
            await session.exec(select(Rider).where(Rider.id.in_(winner_ids)))
        ).all()
        names = {r.id: r.full_name for r in riders}

    return [
        AwardSummaryRead(
            title=award.title or "",
            sponsor_name=award.sponsor_name,
            sponsor_logo_url=award.sponsor_logo_url,
            prize_description=award.prize_description,
            metric_value=award.metric_value,
            winner_name=names.get(award.winner_rider_id) if award.winner_rider_id else None,
        )
        for award in awards
    ]


async def compute_stage_extremes(
    session: AsyncSession, stage_id: int
) -> dict:
    """Scratch (tiempo mínimo) y farolito (tiempo máximo) de la jornada.

    Devuelve claves siempre presentes: `scratch` o `farolito` pueden ser
    `None` si la fecha no tiene ese extremo (una fecha con un solo finisher,
    por ejemplo). La ficha debe renderizar lo que haya, sin asumir que ambos
    existen.
    """
    scratch_entry = (
        await session.exec(
            select(StageEntry)
            .where(
                StageEntry.stage_id == stage_id,
                StageEntry.race_status == RaceStatusEnum.FINISHED,
                StageEntry.finish_elapsed_ms.is_not(None),
            )
            .order_by(StageEntry.finish_elapsed_ms)
        )
    ).first()

    farolito_entry = (
        await session.exec(
            select(StageEntry)
            .where(
                StageEntry.stage_id == stage_id,
                StageEntry.race_status == RaceStatusEnum.FINISHED,
                StageEntry.finish_elapsed_ms.is_not(None),
            )
            .order_by(StageEntry.finish_elapsed_ms.desc())
        )
    ).first()

    async def _to_read(entry) -> Optional[PodiumEntryRead]:
        if entry is None:
            return None
        await session.refresh(entry, ["rider", "category", "team"])
        return PodiumEntryRead(
            rank=entry.category_rank or 0,
            bib_number=entry.bib_number,
            rider_name=entry.rider.full_name if entry.rider else "",
            rider_slug=entry.rider.slug if entry.rider else "",
            team_name=entry.team.name if entry.team else "LIBRE",
            team_slug=entry.team.slug if entry.team else None,
            formatted_time=format_ms_to_time(entry.finish_elapsed_ms or 0),
            points_earned=entry.points_earned or 0,
        )

    return {
        "scratch": await _to_read(scratch_entry),
        "farolito": await _to_read(farolito_entry),
    }
