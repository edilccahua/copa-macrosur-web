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
from typing import Dict, List, Optional, Any

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
from backend.app.services.strava_selection import (
    filter_efforts,
    is_full_route,
    is_measured_on_stage,
    select_segments,
)
from backend.app.services.special_prizes_service import clean_display_name
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
from backend.app.services.standings_service import scope_of_category

# Escala de puntos de specs/01 §3.1: 1°=10 … 10°=1, 11°+=1, DNF/DNS/DSQ=0.
_POINTS_TOP10 = [10, 9, 8, 7, 6, 5, 4, 3, 2, 1]

# La E-BIKE no compite por el titulo de la fecha: el E-BIKE OPEN tiene su
# propio leaderboard, pero un e-bike no puede ser el scratch de MTB.
E_BIKE_SHORT_CODE = "EBK"

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

    # El ganador es el de mayor VELOCIDAD sobre la distancia realmente
    # recorrida: en un circuito por vueltas no todos completan lo mismo, y el
    # tiempo más bajo puede ser el de quien dio menos vueltas.
    winner_rows = (
        await session.exec(
            select(StageEntry.finish_elapsed_ms, StageEntry.laps)
            .join(Category, StageEntry.category_id == Category.id)
            .where(
                StageEntry.stage_id == stage_id,
                StageEntry.finish_elapsed_ms.is_not(None),
                StageEntry.race_status == RaceStatusEnum.FINISHED,
                # La E-BIKE no entra en la pugna por el titulo de la fecha.
                Category.short_code != E_BIKE_SHORT_CODE,
            )
        )
    ).all()

    def _speed(row) -> float:
        elapsed = int(row[0] or 0)
        per_lap = float(stage.distance_km or 0)
        if elapsed <= 0 or per_lap <= 0:
            return 0.0
        laps = max(1, int(row[1] or 1))
        return (per_lap * laps) / (elapsed / 3_600_000)

    winner = max(winner_rows, key=_speed) if winner_rows else None
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
    # Una fecha sin ruta publicada (la Fecha 4) no tiene cifras: `None`, no 0.
    distance_km_per_lap = (
        round(float(stage.distance_km), 2) if stage.distance_km is not None else None
    )
    distance_km_total = (
        round(float(stage.distance_km) * laps, 2)
        if stage.distance_km is not None
        else None
    )
    elevation_m_per_lap = stage.elevation_gain_m
    elevation_m_total = (
        int(stage.elevation_gain_m) * laps if stage.elevation_gain_m is not None else None
    )

    winner_avg_speed_kmh: Optional[float] = None
    if (
        winner_time_ms
        and winner_time_ms > 0
        and stage.distance_km is not None
        and stage.distance_km > 0
    ):
        winner_distance_km = float(stage.distance_km) * max(1, winner_laps)
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
        distance_km_per_lap=distance_km_per_lap,
        distance_km_total=distance_km_total,
        elevation_m_per_lap=elevation_m_per_lap,
        elevation_m_total=elevation_m_total,
        laps=laps,
        winner_time_ms=winner_time_ms,
        winner_avg_speed_kmh=winner_avg_speed_kmh,
        categories_count=categories,
        official_results=stage.official_results,
        official_points=stage.official_points,
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
                group=scope_of_category(category.short_code),
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
                # Medallas de la jornada: los puestos 1º, 2º y 3º del podio.
                func.sum(func.cast(StageEntry.category_rank == 1, Integer)),
                func.sum(func.cast(StageEntry.category_rank == 2, Integer)),
                func.sum(func.cast(StageEntry.category_rank == 3, Integer)),
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
            "first_places": int(golds or 0),
            "second_places": int(silvers or 0),
            "third_places": int(bronzes or 0),
        }
        for team_id, team_name, team_slug, points, riders, best_rank, golds, silvers, bronzes in rows
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
                first_places=entry["first_places"],
                second_places=entry["second_places"],
                third_places=entry["third_places"],
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
            first_places=current.first_places + entry["first_places"],
            second_places=current.second_places + entry["second_places"],
            third_places=current.third_places + entry["third_places"],
        )

    return sorted(merged.values(), key=lambda t: (-t.points, t.team_name))[:3]


async def load_stage_strava_data(
    session: AsyncSession, stage_id: int
) -> tuple[List[StravaSegment], List[StravaEffort], List[int]]:
    """Los segmentos, los intentos y los corredores inscritos de la fecha.

    `compute_stage_strava` y `compute_stage_mountain_titles` necesitan EXACTAMENTE
    lo mismo. Cargarlo una vez y compartirlo evita cuatro consultas de sobra en
    cada ficha de fecha (y dos en la portada, que también los necesita).
    """
    segments = (
        await session.exec(
            select(StravaSegment)
            .where(StravaSegment.stage_id == stage_id)
            .order_by(StravaSegment.id)
        )
    ).all()

    efforts: List[StravaEffort] = []
    if segments:
        efforts = (
            await session.exec(
                select(StravaEffort)
                .where(StravaEffort.segment_id.in_([segment.id for segment in segments]))
                .order_by(StravaEffort.segment_id, StravaEffort.elapsed_time_sec)
            )
        ).all()

    # Los corredores inscritos en esta fecha: un intento de un corredor que
    # no compitio no es de esta carrera.
    stage_rider_ids = (
        await session.exec(
            select(StageEntry.rider_id).where(StageEntry.stage_id == stage_id)
        )
    ).all()
    rider_ids = [r for r in stage_rider_ids if r is not None]

    return segments, efforts, rider_ids


async def compute_stage_strava(
    session: AsyncSession,
    stage: Stage,
    *,
    segments: Optional[List[StravaSegment]] = None,
    efforts: Optional[List[StravaEffort]] = None,
    rider_ids: Optional[List[int]] = None,
) -> List[StravaSegmentSummaryRead]:
    """Segmentos Strava de la fecha con sus 10 mejores tiempos y el KOM.

    Se aplican las tres reglas de `strava_selection`:
      1. solo cuentan los intentos **medidos en la fecha de la carrera**;
      2. solo cuentan los intentos de corredores **inscritos en esa fecha**;
      3. se descarta el segmento que cubre la carrera entera (es la ruta) y
         se muestran los cinco mas relevantes.

    El flag `is_kom_qom` de la BD es la autoridad del KOM (specs/02 §4).

    `segments`, `efforts` y `rider_ids` se pueden pasar ya cargados (ver
    `load_stage_strava_data`): la ficha de la fecha los usa dos veces y no
    tiene que leerlos dos veces.

    OJO: los tres parámetros son **todo o nada**. Si falta UNO solo, se
    recargan los tres desde la base de datos (lo que hace el `if` de abajo):
    pasar sólo `segments=` no ahorra nada, desperdicia una consulta y
    además invalida lo que el llamante ya había cargado.
    """
    if segments is None or efforts is None or rider_ids is None:
        segments, efforts, rider_ids = await load_stage_strava_data(session, stage.id)
    if not segments:
        return []

    by_segment: Dict[int, List[StravaEffort]] = {}
    for effort in efforts:
        by_segment.setdefault(effort.segment_id, []).append(effort)

    stage_date = stage.date.isoformat() if stage.date else None
    stage_distance_km = float(stage.distance_km or 0) * max(1, stage.laps or 1)

    summaries: List[StravaSegmentSummaryRead] = []
    for segment in segments:
        segment_efforts = by_segment.get(segment.id, [])
        relevant = filter_efforts(
            [
                {
                    "measured_on": effort.measured_on,
                    "rider_id": effort.rider_id,
                    "athlete_name_raw": effort.athlete_name_raw,
                    "elapsed_time_sec": effort.elapsed_time_sec,
                    "is_kom_qom": effort.is_kom_qom,
                }
                for effort in segment_efforts
            ],
            stage_date=stage_date,
            stage_rider_ids=rider_ids,
        )
        # Los efforts filtrados conservan el orden por tiempo (la consulta
        # viene ordenada por elapsed_time_sec).
        effort_reads = [
            StravaEffortRead(
                athlete_name=effort["athlete_name_raw"] or "—",
                elapsed_time_sec=int(effort["elapsed_time_sec"] or 0),
                formatted_time=format_ms_to_time(int(effort["elapsed_time_sec"] or 0) * 1000),
                is_kom_qom=bool(effort["is_kom_qom"]),
            )
            for effort in relevant
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

    selected = select_segments(
        [summary.model_dump() for summary in summaries],
        stage_distance_km=stage_distance_km,
    )
    by_id = {summary.strava_segment_id: summary for summary in summaries}
    return [by_id[item["strava_segment_id"]] for item in selected if item["strava_segment_id"] in by_id]


async def compute_stage_mountain_titles(
    session: AsyncSession,
    stage: Stage,
    *,
    segments: Optional[List[StravaSegment]] = None,
    efforts: Optional[List[StravaEffort]] = None,
    rider_ids: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """Los cuatro títulos de montaña de la fecha.

    · **KOM** (King of the Mountain): el escalador **varón** más rápido en la
      subida más empinada de la jornada.
    · **QOM** (Queen of the Mountain): la escaladora **mujer** más rápida en esa
      misma subida. El QOM nunca sale de un varón: se resuelve por el género del
      atleta.
    · **El Kamikaze**: el varón más rápido en el descenso más pronunciado.
    · **La Kamikaze**: la mujer más rápida en ese mismo descenso.

    Se aplican las mismas reglas que en los segmentos: el corredor que
    acompaña a cada título es el más rápido **de la fecha de la carrera** y
    de un corredor que compitió en ella. Si el tramo no tiene intentos de la
    jornada se recurre al mejor intento registrado **del mismo género**. El
    segmento que cubre la carrera entera no puede ser un título: es la ruta.

    `segments`, `efforts` y `rider_ids` se pueden pasar ya cargados (ver
    `load_stage_strava_data`): son los mismos datos que necesita
    `compute_stage_strava`, y la ficha de la fecha los usa de las dos formas.

    OJO: los tres parámetros son **todo o nada**. Si falta UNO solo, se
    recargan los tres desde la base de datos: pasar sólo `segments=` no
    ahorra nada, desperdicia una consulta y además invalida lo que el
    llamante ya había cargado.
    """
    empty = {
        "kom": None,
        "qom": None,
        "kamikaze_male": None,
        "kamikaze_female": None,
    }
    if segments is None or efforts is None or rider_ids is None:
        segments, efforts, rider_ids = await load_stage_strava_data(session, stage.id)
    if not segments:
        return empty

    stage_distance_km = float(stage.distance_km or 0) * max(1, stage.laps or 1)
    # El segmento que cubre la carrera entera es la ruta, no un título.
    candidates = [
        segment
        for segment in segments
        if not is_full_route(
            round(float(segment.distance_m or 0) / 1000, 2), stage_distance_km
        )
    ]
    if not candidates:
        return empty

    stage_date = stage.date.isoformat() if stage.date else None

    # El género del intento viene de Strava; si falta, se deduce del corredor
    # inscrito al que está enlazado.
    rider_gender = {
        rider_id: gender
        for rider_id, gender in (
            await session.exec(select(Rider.id, Rider.gender))
        ).all()
    }

    def _gender_of(effort: StravaEffort) -> Optional[str]:
        if effort.athlete_gender in ("M", "F"):
            return effort.athlete_gender
        gender = rider_gender.get(effort.rider_id) if effort.rider_id else None
        if hasattr(gender, "value"):
            gender = gender.value
        return gender if gender in ("M", "F") else None

    def _read_title(segment: StravaSegment, effort: StravaEffort) -> MountainTitleRead:
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

    climbs = [s for s in candidates if float(s.average_grade or 0) > 0]
    descents = [s for s in candidates if float(s.average_grade or 0) < 0]

    def _has_race_day(segment: StravaSegment) -> bool:
        """¿Alguien cronometró este tramo el día de la carrera?"""
        return any(
            effort.segment_id == segment.id
            and is_measured_on_stage(effort.measured_on, stage_date)
            for effort in efforts
        )

    # La subida y el descenso que definen la jornada: el más empinado y, a
    # igualdad de pendiente, el más largo. Se prefiere un tramo que tenga
    # intentos de la fecha: si el descenso más empinado solo guarda tiempos de
    # hace años, el título sería de otra carrera.
    climb_segment = None
    if climbs:
        climb_segment = max(
            climbs,
            key=lambda s: (
                _has_race_day(s),
                float(s.average_grade or 0),
                float(s.distance_m or 0),
            ),
        )
    descent_segment = None
    if descents:
        descent_segment = max(
            descents,
            key=lambda s: (
                _has_race_day(s),
                -float(s.average_grade or 0),
                float(s.distance_m or 0),
            ),
        )

    def _title(
        segment: Optional[StravaSegment], gender: str
    ) -> Optional[MountainTitleRead]:
        """El título de un segmento para un género, con su corredor más rápido.

        Se prefiere el intento **de la fecha de la carrera**. Si el tramo no
        tiene ninguno de ese género (una bajada que ninguna dama cronometró ese
        día), se recurre al mejor intento registrado del mismo género: el
        título existe y el intento es real, aunque no sea de nuestra jornada.
        """
        if segment is None:
            return None
        efforts_of_segment = [
            effort
            for effort in efforts
            if effort.segment_id == segment.id and _gender_of(effort) == gender
        ]
        if not efforts_of_segment:
            return None

        same_day = [
            effort
            for effort in efforts_of_segment
            if is_measured_on_stage(effort.measured_on, stage_date)
            and (effort.rider_id is None or not rider_ids or effort.rider_id in rider_ids)
        ]
        pool = same_day or efforts_of_segment
        best = min(pool, key=lambda e: e.elapsed_time_sec or 0)
        return _read_title(segment, best)

    return {
        "kom": _title(climb_segment, "M"),
        "qom": _title(climb_segment, "F"),
        "kamikaze_male": _title(descent_segment, "M"),
        "kamikaze_female": _title(descent_segment, "F"),
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

    El perfil sale de la geometría real (`route_geojson`), no de multiplicar la
    distancia por las vueltas: en un circuito por vueltas la geometría es de
    UNA vuelta y `geometry_covers_full_stage` lo avisa.

    El desnivel que muestra es el de la RUTA OFICIAL (`Stage.elevation_gain_m`),
    no el que sale de la traza simplificada a 500 puntos: la simplificación
    pierde unos treinta metros de subida y la ficha mostraba las dos cifras
    (cabecera +384 m, perfil +359 m). Con un solo desnivel, manda el oficial.
    """
    profile = build_route_profile(
        stage.route_geojson,
        stage_laps=stage.laps or 1,
        official_gain_m=stage.elevation_gain_m,
    )
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
        names = {r.id: clean_display_name(r.full_name) for r in riders}

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
    session: AsyncSession, stage: Stage
) -> dict:
    """Scratch (el más rápido) y farolito (el más lento) de la jornada.

    Dos reglas que no son obvias:

    · **La categoría E-BIKE OPEN no compite por el título.** Un e-bike no es un
      scratch de MTB: el E-BIKE OPEN sigue con su propio leaderboard, pero
      no puede ser el ganador de la fecha.
    · **El criterio es la VELOCIDAD, no el tiempo.** En un circuito por
      vueltas no todos completan lo mismo: el tiempo más bajo puede ser el
      de quien dio menos vueltas. Se compara la velocidad sobre la
      distancia REALMENTE recorrida (`StageEntry.laps`).

    Devuelve claves siempre presentes: `scratch` o `farolito` pueden ser
    `None` si la fecha no tiene ese extremo. La ficha debe renderizar lo que
    haya, sin asumir que ambos existen.
    """
    entries = (
        await session.exec(
            select(StageEntry, Rider, Category, Team)
            .join(Category, StageEntry.category_id == Category.id)
            .outerjoin(Rider, StageEntry.rider_id == Rider.id)
            .outerjoin(Team, StageEntry.team_id == Team.id)
            .where(
                StageEntry.stage_id == stage.id,
                StageEntry.race_status == RaceStatusEnum.FINISHED,
                StageEntry.finish_elapsed_ms.is_not(None),
                # La E-BIKE no entra en la pugna por el titulo de la fecha.
                Category.short_code != E_BIKE_SHORT_CODE,
            )
        )
    ).all()

    if not entries:
        return {"scratch": None, "farolito": None}

    per_lap_km = float(stage.distance_km or 0)

    def _speed(fila) -> float:
        """Velocidad media (km/h) sobre la distancia realmente recorrida."""
        entry = fila[0]
        elapsed = entry.finish_elapsed_ms or 0
        if elapsed <= 0:
            return 0.0
        distance_km = per_lap_km * max(1, entry.laps or 1)
        return (distance_km / (elapsed / 3_600_000)) if distance_km > 0 else 0.0

    scratch_entry = max(entries, key=_speed)
    farolito_entry = min(entries, key=_speed)

    def _to_read(fila) -> Optional[PodiumEntryRead]:
        if fila is None:
            return None
        entry, rider, _category, team = fila
        return PodiumEntryRead(
            rank=entry.category_rank or 0,
            bib_number=entry.bib_number,
            rider_name=rider.full_name if rider else "",
            rider_slug=rider.slug if rider else "",
            team_name=team.name if team else "LIBRE",
            team_slug=team.slug if team else None,
            formatted_time=format_ms_to_time(entry.finish_elapsed_ms or 0),
            points_earned=entry.points_earned or 0,
        )

    return {
        "scratch": _to_read(scratch_entry),
        "farolito": _to_read(farolito_entry),
    }
