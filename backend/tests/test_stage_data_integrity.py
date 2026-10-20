"""
Reglas de integridad de los datos de una fecha.

Cuatro reglas que el sitio NO puede incumplir (20-Oct-2026):

1. **Un solo desnivel por carrera.** La cabecera de la ficha y el perfil de
   altimetría no pueden decir dos cifras distintas. Manda la de la RUTA
   OFICIAL (la del GPX a resolución completa), no la que sale de la traza
   simplificada a 500 puntos.
2. **Una fecha sin ruta no afirma cifras.** La Fecha 4 (Quequeña Xtreme III) no
   tiene GPX, ni ruta de Strava, ni póster: su distancia y su desnivel son
   `None`, no 0 ni 45 km inventados.
3. **Lo que recalcula el motor se documenta.** El PDF oficial de Z Xtreme no
   imprime el 6º lugar de OPEN DAMAS: publica 554 puntos y el motor reparte
   555 al rellenar el hueco. Las dos cifras se exponen.
4. **La escala de premios vive en la BD.** En dólares, por categoría y por
   ámbito (por fecha 70/50/30, acumulada 300/200/100).
"""
import datetime
import os

import pytest
from sqlmodel import select

from backend.app.models.entities import (
    PrizeTier,
    Stage,
    StageStatusEnum,
    Category,
    StageEntry,
    Rider,
    RaceStatusEnum,
)
from backend.app.models.schemas import StageStatsRead
from backend.app.services.route_profile_service import build_route_profile
from backend.app.services.stage_summary_service import (
    compute_stage_route_profile,
    compute_stage_stats,
)

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RACES_DIR = os.path.join(REPO_ROOT, "races")


# ── 1. Un solo desnivel ─────────────────────────────────────────────────────


def test_profile_uses_the_official_gain_not_the_simplified_trace():
    """La traza simplificada pierde desnivel: manda la cifra oficial."""
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [-71.0, -16.0, 1000.0, 0.0],
                        [-71.1, -16.0, 1100.0, 5.0],
                        [-71.2, -16.0, 1050.0, 10.0],
                    ],
                },
            }
        ],
    }
    # Sin cifra oficial: sale de la traza.
    from_trace = build_route_profile(geojson, stage_laps=1)
    assert from_trace is not None
    assert from_trace["elevation_gain_m"] == 100

    # Con cifra oficial: manda ella (la traza simplificada se queda corta).
    with_official = build_route_profile(geojson, stage_laps=1, official_gain_m=384)
    assert with_official is not None
    assert with_official["elevation_gain_m"] == 384
    # El descenso no tiene cifra oficial: sigue saliendo de la traza.
    assert with_official["elevation_loss_m"] == 50


@pytest.mark.asyncio
async def test_stage_profile_uses_the_stage_official_gain(async_session):
    """La ficha y el perfil muestran la MISMA cifra de desnivel."""
    stage = Stage(
        stage_number=90,
        name="Fecha de prueba",
        slug="fecha-de-prueba",
        date=datetime.date(2026, 5, 17),
        status=StageStatusEnum.FINISHED,
        distance_km=40.85,
        elevation_gain_m=384,
        laps=1,
        route_geojson={
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [
                            [-71.0, -16.0, 1000.0, 0.0],
                            [-71.1, -16.0, 1100.0, 5.0],
                            [-71.2, -16.0, 1050.0, 10.0],
                        ],
                    },
                }
            ],
        },
    )
    async_session.add(stage)
    await async_session.commit()

    profile = await compute_stage_route_profile(async_session, stage)
    assert profile is not None
    assert profile.elevation_gain_m == stage.elevation_gain_m == 384

    stats = await compute_stage_stats(async_session, stage.id)
    assert stats.elevation_m_total == 384


# ── 2. Una fecha sin ruta no afirma cifras ─────────────────────────────────


@pytest.mark.asyncio
async def test_a_stage_without_route_has_no_figures(async_session):
    """Sin ruta no hay distancia ni desnivel: `None`, nunca 0."""
    stage = Stage(
        stage_number=91,
        name="Fecha sin ruta",
        slug="fecha-sin-ruta",
        date=datetime.date(2026, 12, 13),
        status=StageStatusEnum.UPCOMING,
        distance_km=None,
        elevation_gain_m=None,
        laps=1,
    )
    async_session.add(stage)
    await async_session.commit()

    stats = await compute_stage_stats(async_session, stage.id)
    assert stats.distance_km_per_lap is None
    assert stats.distance_km_total is None
    assert stats.elevation_m_per_lap is None
    assert stats.elevation_m_total is None
    # Sin distancia no hay velocidad: tampoco 0 km/h.
    assert stats.winner_avg_speed_kmh is None
    # Y no hay perfil que dibujar.
    assert await compute_stage_route_profile(async_session, stage) is None


# ── 3. Lo que recalcula el motor se documenta ──────────────────────────────


@pytest.mark.asyncio
async def test_stats_expose_the_official_figures_of_the_pdf(async_session):
    """Las cifras PUBLICADAS en el PDF se exponen junto a las recalculadas."""
    stage = Stage(
        stage_number=92,
        name="Z Xtreme",
        slug="z-xtreme-test",
        date=datetime.date(2026, 8, 23),
        status=StageStatusEnum.FINISHED,
        distance_km=11.83,
        elevation_gain_m=280,
        laps=3,
        official_results=112,
        official_points=554,
    )
    async_session.add(stage)
    await async_session.flush()

    category = Category(name="ELITE", short_code="ELI", aliases=["ELITE"])
    async_session.add(category)
    await async_session.flush()

    rider = Rider(full_name="CARINA MAMANI", slug="carina-mamani", dni="40851640", gender="F")
    async_session.add(rider)
    await async_session.flush()

    async_session.add(
        StageEntry(
            stage_id=stage.id,
            rider_id=rider.id,
            category_id=category.id,
            bib_number=202,
            race_status=RaceStatusEnum.FINISHED,
            finish_elapsed_ms=8_033_000,
            category_rank=6,
            points_earned=5,
        )
    )
    await async_session.commit()

    stats = await compute_stage_stats(async_session, stage.id)
    # Lo que recalcula el motor.
    assert stats.points_total == 5
    # Lo que publicó el PDF: un punto menos, porque no imprimió el 6º lugar.
    assert stats.official_points == 554
    assert stats.official_results == 112
    # Y las dos cifras conviven: la página puede explicarlas.
    assert stats.official_points != stats.points_total


# ── 4. La escala de premios vive en la BD ──────────────────────────────────


@pytest.mark.asyncio
async def test_prize_tiers_are_in_the_database(async_session):
    """La escala de premios: por fecha 100/50/30 y acumulada por agrupación."""
    from backend.app.seed import seed_prize_tiers

    await seed_prize_tiers(async_session)
    tiers = (await async_session.exec(select(PrizeTier))).all()
    by_scope: dict[str, list] = {}
    for tier in tiers:
        by_scope.setdefault(tier.scope, []).append(tier)

    assert sorted(t.amount_usd for t in by_scope["FECHA"]) == [30, 50, 100]
    assert all(t.currency == "USD" for t in tiers)
    # El premio es por categoría: hay un peldaño para cada puesto de 1 a 3.
    assert sorted(t.position for t in by_scope["FECHA"]) == [1, 2, 3]
    # El acumulado es POR AGRUPACIÓN: PRO, NORMAL y EQUIPOS.
    acumulados = [t for t in tiers if t.scope == "ACUMULADO"]
    assert sorted(t.position for t in acumulados) == [1, 1, 1, 2, 2, 2, 3, 3, 3]
    assert {t.group_key for t in acumulados} == {"PRO", "NORMAL", "EQUIPOS"}
    for group, montos in (("PRO", [300, 200, 100]), ("NORMAL", [300, 200, 100]), ("EQUIPOS", [500, 400, 300])):
        fila = sorted(
            (t for t in acumulados if t.group_key == group), key=lambda t: t.position
        )
        assert [t.amount_usd for t in fila] == montos


@pytest.mark.asyncio
async def test_prizes_endpoint_returns_the_scale(async_session, client):
    """La API expone la escala para que la página no la escriba a mano."""
    from backend.app.seed import seed_prize_tiers

    await seed_prize_tiers(async_session)
    await async_session.commit()

    res = await client.get("/api/v1/public/prizes")
    assert res.status_code == 200, res.text
    body = res.json()
    assert len(body) == 12
    fecha = {t["position"]: t["amount_usd"] for t in body if t["scope"] == "FECHA"}
    assert fecha == {1: 100, 2: 50, 3: 30}
    equipos = {
        t["position"]: t["amount_usd"] for t in body if t.get("group_key") == "EQUIPOS"
    }
    assert equipos == {1: 500, 2: 400, 3: 300}
