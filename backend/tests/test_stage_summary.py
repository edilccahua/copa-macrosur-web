"""
Tests del resumen de presentación de una fecha (`GET /stages/{slug}/summary`).

La ficha `/fechas/[slug]` consume este endpoint: en UNA llamada recibe las
cifras de la jornada, el podio por categoría, el podio de equipos, los
segmentos Strava, los checkpoints, los premios y los extremos. La página no
recalcula nada y no tiene datos literales (specs/03 §0.2, §1.2).

Las cifras de referencia son las del PDF oficial de cada fecha
(INTEGRIDAD-DATOS.md §4):
  La Joya Extreme : 225 inscripciones, 198 con tiempo, 667 puntos.
  Z Xtreme 2026   : 167 inscripciones, 112 con tiempo, 555 puntos.
"""
import hashlib
import json
from datetime import date as date_cls
from typing import List, Optional

import pytest
from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from backend.app.models.entities import (
    Category,
    Checkpoint,
    RaceStatusEnum,
    Rider,
    SpecialAward,
    Stage,
    StageEntry,
    StageStatusEnum,
    StravaEffort,
    StravaSegment,
    Team,
)
from backend.app.services.stage_summary_service import (
    compute_category_podium,
    compute_stage_awards,
    compute_stage_checkpoints,
    compute_stage_stats,
    compute_stage_strava,
    compute_stage_team_podium,
)

# Escala de puntos de specs/01 §3.1, escrita aquí a mano (no importada del
# servicio) para que el generador de datos y la implementación no compartan
# código: un test no puede cazar un error de escala si ambos la comparten.
SCALE_10 = [10, 9, 8, 7, 6, 5, 4, 3, 2, 1]


def _points_for_rank(rank: int) -> int:
    """Puntos de un puesto dentro de su categoría (specs/01 §3.1)."""
    if rank <= 0:
        return 0
    if rank <= len(SCALE_10):
        return SCALE_10[rank - 1]
    return 1

# --------------------------------------------------------------------------
# Helpers de siembra
# --------------------------------------------------------------------------


async def _seed_categories(session: AsyncSession, codes: List[str]) -> List[Category]:
    """Crea (o reutiliza) las categorías por `short_code` y las devuelve."""
    created: List[Category] = []
    for code in codes:
        existing = (
            await session.exec(select(Category).where(Category.short_code == code))
        ).first()
        if existing is None:
            existing = Category(short_code=code, name=code)
            session.add(existing)
            await session.flush()
        created.append(existing)
    return created


async def _seed_team(session: AsyncSession, name: str) -> Team:
    existing = (await session.exec(select(Team).where(Team.name == name))).first()
    if existing is None:
        existing = Team(name=name, slug=name.lower().replace(" ", "-"))
        session.add(existing)
        await session.flush()
    return existing


async def _seed_stage_with_results(
    session: AsyncSession,
    *,
    slug: str = "la-joya-extreme",
    stage_number: int = 1,
    name: str = "Fecha 1: La Joya Extreme",
    title: str = "La Joya Extreme",
    short_name: str = "La Joya",
    start_location: str = "Vía de Evitamiento, La Joya",
    start_time: str = "08:00 AM",
    date: str = "2026-05-17",
    # ...
    distance_km: float = 40.85,
    elevation_gain_m: int = 384,
    laps: int = 1,
    entries: int = 0,
    finishers: int = 0,
    points: int = 0,
    categories: int = 0,
) -> Stage:
    """Crea una etapa con `entries` inscripciones, `finishers` con tiempo.

    Los puntos se reparten de 10 en 10 entre loselar-finishers, de forma que
    `points` es la suma de `StageEntry.points_earned` de la etapa.
    """
    stage = Stage(
        stage_number=stage_number,
        name=name,
        title=title,
        short_name=short_name,
        slug=slug,
        date=date_cls.fromisoformat(date),
        status=StageStatusEnum.FINISHED if entries else StageStatusEnum.UPCOMING,
        start_location=start_location,
        start_time=start_time,
        distance_km=distance_km,
        elevation_gain_m=elevation_gain_m,
        laps=laps,
    )
    session.add(stage)
    await session.flush()

    cats: List[Category] = []
    if categories:
        cats = await _seed_categories(session, [f"CAT{i:02d}" for i in range(categories)])

    team = await _seed_team(session, "TEAM COLCA BIKE")

    # Reparto de puntos: 10, 9, 8, ... 1 y luego 1 para el resto (escala de
    # specs/01 §3.1). Los primeros `finishers` llevan tiempo y posición.
    remaining = points
    # El DNI es único en toda la tabla: se deriva de un hash de (slug, índice)
    # para que 225 corredores y varias etapas en el mismo test no colisionen.
    #
    # Los puntos siguen la escala de specs/01 §3.1 POR CATEGORÍA: 1°=10 …
    # 10°=1 y 11°+=1. El `category_rank` también es por categoría, no global.
    rank_by_category: dict[int, int] = {}
    for i in range(entries):
        category = cats[i % len(cats)] if cats else None
        digest = hashlib.md5(f"{slug}:{i}".encode()).hexdigest()
        rider = Rider(
            dni=str(int(digest[:12], 16) % 100_000_000).zfill(8),
            full_name=f"CICLISTA {i:03d}",
            slug=f"{slug}-ciclista-{i:03d}",
            team_id=team.id,
        )
        session.add(rider)
        await session.flush()

        finished = i < finishers
        if finished:
            cat_id = category.id if category else 0
            rank_by_category[cat_id] = rank_by_category.get(cat_id, 0) + 1
            rank = rank_by_category[cat_id]
            earned = _points_for_rank(rank)
            if remaining <= 0:
                earned = 0
            else:
                earned = min(earned, remaining)
                remaining -= earned
            elapsed = 3_600_000 + i * 60_000
            status = RaceStatusEnum.FINISHED
        else:
            earned = 0
            elapsed = None
            rank = None
            status = RaceStatusEnum.REGISTERED

        session.add(
            StageEntry(
                stage_id=stage.id,
                rider_id=rider.id,
                category_id=category.id if category else None,
                team_id=team.id,
                bib_number=i + 1,
                race_status=status,
                finish_elapsed_ms=elapsed,
                category_rank=rank,
                overall_rank=rank,
                points_earned=earned,
            )
        )

    await session.commit()
    await session.refresh(stage)
    return stage


# --------------------------------------------------------------------------
# Task 0.1 — el API sirve los campos que la BD persiste
# --------------------------------------------------------------------------


async def test_stage_api_exposes_persisted_fields(async_session, client):
    """El API expone los campos de etapa que la BD persiste.

    Antes, el servidor llevaba horas sin recargar y servía un modelo viejo
    (sin title/short_name/start_location/start_time): la página leía
    `undefined` y caía a un mock local. Este test fija ese contrato.
    """
    await _seed_stage_with_results(async_session, entries=0, categories=0)

    res = await client.get("/api/v1/stages/la-joya-extreme/summary")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["stage"]["title"] == "La Joya Extreme"
    assert body["stage"]["short_name"] == "La Joya"
    assert body["stage"]["start_location"] == "Vía de Evitamiento, La Joya"
    assert body["stage"]["start_time"] == "08:00 AM"
    assert body["stage"]["slug"] == "la-joya-extreme"


async def test_seed_helper_creates_entries(async_session):
    """El helper deja la BD en el estado que el resto de tests asume."""
    stage = await _seed_stage_with_results(
        async_session, entries=225, finishers=198, points=667, categories=11
    )
    assert stage.id is not None
    total = await async_session.exec(
        select(func.count())
        .select_from(StageEntry)
        .where(StageEntry.stage_id == stage.id)
    )
    assert total.one() == 225


# --------------------------------------------------------------------------
# Task 1.1 — estadísticas de jornada
# --------------------------------------------------------------------------


async def test_stage_stats_match_official_numbers(async_session):
    """Las estadísticas de la Fecha 1 coinciden con el PDF oficial.

    INTEGRIDAD-DATOS.md §4: 225 inscripciones, 198 con tiempo, 667 puntos.
    """
    stage = await _seed_stage_with_results(
        async_session, entries=225, finishers=198, points=667, categories=11
    )
    stats = await compute_stage_stats(async_session, stage.id)
    assert stats.entries_total == 225
    assert stats.finishers == 198
    assert stats.non_finishers == 27
    assert stats.points_total == 667
    assert stats.categories_count == 11


async def test_summary_undisputed_stage_has_null_stats(async_session):
    """F3 no tiene inscripciones: las estadísticas son null, no ceros falsos."""
    stage = await _seed_stage_with_results(
        async_session,
        slug="vuelta-a-los-poblados",
        stage_number=3,
        entries=0,
        finishers=0,
        points=0,
        categories=0,
    )
    stats = await compute_stage_stats(async_session, stage.id)
    assert stats.entries_total == 0
    assert stats.finishers == 0
    assert stats.points_total == 0
    assert stats.winner_time_ms is None
    assert stats.winner_avg_speed_kmh is None


async def test_summary_lap_circuit_exposes_per_lap_and_total(async_session):
    """F2 es un circuito por vueltas: se exponen ambos, sin mezclarlos.

    En `stages`, `distance_km` y `elevation_gain_m` son POR VUELTA.
    """
    stage = await _seed_stage_with_results(
        async_session,
        slug="z-xtreme-2026",
        stage_number=2,
        distance_km=11.83,
        elevation_gain_m=280,
        laps=3,
        entries=10,
        finishers=8,
        points=44,
        categories=2,
    )
    stats = await compute_stage_stats(async_session, stage.id)
    assert stats.laps == 3
    assert stats.distance_km_per_lap == 11.83
    assert stats.distance_km_total == pytest.approx(35.49)
    assert stats.elevation_m_per_lap == 280
    assert stats.elevation_m_total == 840


async def test_stage_stats_computes_winner_speed(async_session):
    """La velocidad del ganador sale del tiempo mínimo y la distancia total."""
    stage = await _seed_stage_with_results(
        async_session,
        distance_km=40.85,
        entries=3,
        finishers=3,
        points=27,
        categories=1,
    )
    stats = await compute_stage_stats(async_session, stage.id)
    assert stats.winner_time_ms == 3_600_000  # 1 h del primer finisher
    # 40.85 km en 1 h = 40.85 km/h
    assert stats.winner_avg_speed_kmh == pytest.approx(40.85, abs=0.01)


# --------------------------------------------------------------------------
# Task 1.2 — podio por categoría
# --------------------------------------------------------------------------


async def test_category_podium_returns_top3_per_category(async_session):
    """Cada categoría devuelve su top-3 con tiempo, puntos y club."""
    stage = await _seed_stage_with_results(
        async_session, entries=30, finishers=30, points=300, categories=5
    )
    podium = await compute_category_podium(async_session, stage.id)
    assert len(podium) == 5
    for cat in podium:
        assert len(cat.entries) == 3
        assert [e.rank for e in cat.entries] == [1, 2, 3]
        assert all(e.formatted_time for e in cat.entries)
        assert all(e.points_earned > 0 for e in cat.entries)
        assert all(e.rider_slug for e in cat.entries)


async def test_category_podium_is_empty_for_undisputed_stage(async_session):
    """Una fecha sin resultados no inventa podios."""
    stage = await _seed_stage_with_results(
        async_session, slug="vuelta-a-los-poblados", stage_number=3, entries=0
    )
    assert await compute_category_podium(async_session, stage.id) == []


# --------------------------------------------------------------------------
# Task 1.3 — podio de equipos de la jornada
# --------------------------------------------------------------------------


async def test_team_podium_ranks_by_points_of_that_stage(async_session):
    """El podio de equipos suma solo los puntos de ESA fecha, no el acumulado.

    12 finishers repartidos en 2 categorías → 6 por categoría → la escala de
    specs/01 §3.1 da 10+9+8+7+6+5 = 45 por categoría, 90 en total.
    """
    stage = await _seed_stage_with_results(
        async_session, entries=12, finishers=12, points=1000, categories=2
    )
    podium = await compute_stage_team_podium(async_session, stage.id)
    assert len(podium) == 1
    assert podium[0].team_name == "TEAM COLCA BIKE"
    assert podium[0].points == 90
    assert podium[0].riders_counted == 12
    assert [p.points for p in podium] == sorted([p.points for p in podium], reverse=True)


async def test_summary_team_podium_has_no_duplicated_clubs(async_session):
    """'CLUB ORIGINAL BIKES AREQUIPA-PERÚ' es UN equipo, no dos."""
    stage = await _seed_stage_with_results(
        async_session, entries=6, finishers=6, points=60, categories=1
    )
    await _seed_team(async_session, "CLUB ORIGINAL BIKES AREQUIPA-")
    await _seed_team(async_session, "CLUB ORIGINAL BIKES AREQUIPA-PERÚ")
    await async_session.commit()

    podium = await compute_stage_team_podium(async_session, stage.id)
    names = [p.team_name for p in podium]
    assert len(names) == len(set(names)), f"equipos duplicados: {names}"


# --------------------------------------------------------------------------
# Task 1.4 — Strava, checkpoints y premios
# --------------------------------------------------------------------------


async def test_stage_checkpoints_are_ordered_with_finish_last(async_session):
    """Los checkpoints van de la Partida a la Meta, en orden."""
    stage = await _seed_stage_with_results(async_session, entries=1, finishers=1, points=10, categories=1)
    session = async_session
    for name, order, km, finish in [
        ("Partida", 0, 0.0, False),
        ("Control Intermedio Cumbre", 1, 20.425, False),
        ("Meta Final", 99, 40.85, True),
    ]:
        session.add(
            Checkpoint(
                stage_id=stage.id,
                name=name,
                order_index=order,
                distance_from_start_km=km,
                is_finish_line=finish,
            )
        )
    await session.commit()

    cps = await compute_stage_checkpoints(session, stage.id)
    assert [c.name for c in cps] == ["Partida", "Control Intermedio Cumbre", "Meta Final"]
    assert cps[-1].is_finish_line is True
    assert cps[0].distance_from_start_km == 0.0


async def test_summary_upcoming_stage_has_empty_collections(async_session):
    """F3 no tiene segmentos Strava ni premios: las listas van vacías, no None."""
    stage = await _seed_stage_with_results(
        async_session, slug="vuelta-a-los-poblados", stage_number=3, entries=0
    )
    assert await compute_stage_strava(async_session, stage.id) == []
    assert await compute_stage_awards(async_session, stage.id) == []


async def test_strava_summary_exposes_top10_and_kom(async_session):
    """Cada segmento trae sus 10 mejores y el KOM marcado."""
    stage = await _seed_stage_with_results(async_session, entries=1, finishers=1, points=10, categories=1)
    session = async_session
    segment = StravaSegment(
        stage_id=stage.id,
        strava_segment_id="41448847",
        name="La Joya Xtreme 26",
        distance_m=38800.0,
        average_grade=-1.6,
    )
    session.add(segment)
    await session.flush()

    for i in range(12):
        session.add(
            StravaEffort(
                segment_id=segment.id,
                athlete_name_raw=f"ATHLETE {i:02d}",
                elapsed_time_sec=4000 + i * 60,
                is_kom_qom=1 if i == 0 else 0,
            )
        )
    await session.commit()

    segs = await compute_stage_strava(session, stage.id)
    assert len(segs) == 1
    la_joya = segs[0]
    assert la_joya.name == "La Joya Xtreme 26"
    assert la_joya.distance_km == 38.8
    assert len(la_joya.efforts) == 10
    assert la_joya.kom is not None
    assert la_joya.kom.is_kom_qom is True
    assert la_joya.kom.athlete_name == "ATHLETE 00"
    times = [e.elapsed_time_sec for e in la_joya.efforts]
    assert times == sorted(times)


async def test_awards_resolve_winner_name(async_session):
    """El premio expone el ganador resuelto desde `winner_rider_id`."""
    stage = await _seed_stage_with_results(async_session, entries=2, finishers=2, points=19, categories=1)
    session = async_session
    winner = (
        await session.exec(select(Rider).where(Rider.full_name == "CICLISTA 000"))
    ).first()
    session.add(
        SpecialAward(
            stage_id=stage.id,
            title="Rey de la Montaña (KOM)",
            sponsor_name="Kúspide Performance",
            sponsor_logo_url="/images/rey_montana.jpg",
            prize_description="S/ 500 + Maillot de Lunares de Líder Escalador",
            metric_value="Mejor tiempo en el sector de ascenso Cumbre",
            winner_rider_id=winner.id if winner else None,
        )
    )
    await session.commit()

    awards = await compute_stage_awards(session, stage.id)
    assert len(awards) == 1
    assert awards[0].title == "Rey de la Montaña (KOM)"
    assert awards[0].sponsor_name == "Kúspide Performance"
    assert awards[0].winner_name == "CICLISTA 000"


# --------------------------------------------------------------------------
# Task 1.5 — el endpoint `/summary`
# --------------------------------------------------------------------------


async def test_summary_endpoint_shape_and_404(async_session, client):
    """El endpoint devuelve las nueve claves del agregado y 404 si no existe."""
    await _seed_stage_with_results(
        async_session, entries=30, finishers=30, points=300, categories=5
    )
    res = await client.get("/api/v1/stages/la-joya-extreme/summary")
    assert res.status_code == 200, res.text
    body = res.json()
    for key in (
        "stage",
        "stats",
        "podium",
        "teams",
        "strava",
        "checkpoints",
        "awards",
        "extremes",
        "navigation",
    ):
        assert key in body, f"falta la clave {key}"

    missing = await client.get("/api/v1/stages/no-existe/summary")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Etapa no encontrada."


async def test_summary_endpoint_navigation_has_neighbours(async_session, client):
    """La navegación apunta a la fecha anterior y a la siguiente."""
    await _seed_stage_with_results(
        async_session, slug="la-joya-extreme", stage_number=1, entries=1, finishers=1, points=10, categories=1
    )
    await _seed_stage_with_results(
        async_session,
        slug="z-xtreme-2026",
        stage_number=2,
        name="Fecha 2: Kúspide Z Xtreme III",
        title="Kúspide Z Xtreme — 3ra Edición",
        short_name="Z Xtreme",
        entries=1,
        finishers=1,
        points=10,
        categories=1,
    )
    await _seed_stage_with_results(
        async_session,
        slug="vuelta-a-los-poblados",
        stage_number=3,
        title="El Retorno a los Poblados 2",
        short_name="Poblados",
        entries=0,
    )

    res = await client.get("/api/v1/stages/z-xtreme-2026/summary")
    assert res.status_code == 200
    nav = res.json()["navigation"]
    assert nav["prev_slug"] == "la-joya-extreme"
    assert nav["next_slug"] == "vuelta-a-los-poblados"


async def test_summary_endpoint_extremes_may_be_independent(async_session, client):
    """Una fecha con un solo finisher produce un extremo y el otro en None.

    La ficha renderiza cada extremo con su propia guardia: no puede pasar
    que falte uno y la página reviente (el bug original accesses
    `stage.farolito.name` sin comprobar).
    """
    stage = await _seed_stage_with_results(
        async_session, entries=1, finishers=1, points=10, categories=1
    )
    session = async_session
    entry = (
        await session.exec(select(StageEntry).where(StageEntry.stage_id == stage.id))
    ).first()
    entry.race_status = RaceStatusEnum.FINISHED
    await session.commit()

    res = await client.get("/api/v1/stages/la-joya-extreme/summary")
    assert res.status_code == 200
    extremes = res.json()["extremes"]
    assert set(extremes.keys()) == {"scratch", "farolito"}
    assert extremes["scratch"] is not None
    assert extremes["scratch"]["formatted_time"]

