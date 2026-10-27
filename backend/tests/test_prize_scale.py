"""La escala de premios: lo que dice la BD es lo que se paga.

La escala cambió varias veces en la edición 2026 (70→100 por fecha, el
acumulado pasó de "por categoría" a "por agrupación" y se añadió el premio
de equipos). El seed tiene que ser un UPSERT: si la tabla ya tenía filas,
antes se iba sin hacer nada y la BD se quedaba con la escala vieja para
siempre. Estos tests blinden que la BD refleje la escala vigente y que
repetir el seed sea idempotente.
"""
import pytest
from sqlmodel import select

from backend.app.models.entities import PrizeTier
from backend.app.seed import seed_prize_tiers

# La escala de la edición 2026: (scope, group_key) -> {puesto: USD}
ESCALA_2026 = {
    ("FECHA", "ELITE"): {1: 70, 2: 0, 3: 0},
    ("FECHA", None): {1: 50, 2: 0, 3: 0},
    ("ACUMULADO", "PRO"): {1: 300, 2: 200, 3: 100},
    ("ACUMULADO", "NORMAL"): {1: 300, 2: 200, 3: 100},
    ("ACUMULADO", "EQUIPOS"): {1: 500, 2: 400, 3: 300},
}


async def _leer(session):
    tiers = (await session.exec(select(PrizeTier))).all()
    escala = {}
    for t in tiers:
        escala.setdefault((t.scope, t.group_key), {})[t.position] = t.amount_usd
    return escala, tiers


@pytest.mark.asyncio
async def test_la_escala_de_la_edicion_2026_queda_sembrada(async_session):
    await seed_prize_tiers(async_session)
    escala, tiers = await _leer(async_session)

    assert escala == ESCALA_2026
    assert len(tiers) == 15


@pytest.mark.asyncio
async def test_el_seed_es_idempotente(async_session):
    await seed_prize_tiers(async_session)
    await seed_prize_tiers(async_session)
    escala, tiers = await _leer(async_session)

    assert escala == ESCALA_2026
    assert len(tiers) == 15


@pytest.mark.asyncio
async def test_el_seed_actualiza_una_escala_vieja(async_session):
    """La escala vieja (70/50/30 y el acumulado por categoría) se corrige."""
    async_session.add_all(
        [
            PrizeTier(scope="FECHA", position=1, amount_usd=70, label="1er puesto de cada categoría"),
            PrizeTier(scope="FECHA", position=2, amount_usd=50, label="2do puesto de cada categoría"),
            PrizeTier(scope="FECHA", position=3, amount_usd=30, label="3er puesto de cada categoría"),
            PrizeTier(scope="ACUMULADO", position=1, amount_usd=300, label="Campeón de cada categoría"),
            PrizeTier(scope="ACUMULADO", position=2, amount_usd=200, label="Subcampeón de cada categoría"),
            PrizeTier(scope="ACUMULADO", position=3, amount_usd=100, label="Tercer puesto de cada categoría"),
        ]
    )
    await async_session.commit()

    await seed_prize_tiers(async_session)
    escala, tiers = await _leer(async_session)

    assert escala == ESCALA_2026
    assert len(tiers) == 15


@pytest.mark.asyncio
async def test_la_api_publica_el_group_key(client, async_session):
    """`GET /public/prizes` dice a qué agrupación pertenece cada fila."""
    await seed_prize_tiers(async_session)

    res = await client.get("/api/v1/public/prizes")
    assert res.status_code == 200
    filas = res.json()
    assert filas, "la API debe devolver la escala"

    por_clave = {(f["scope"], f["group_key"], f["position"]): f["amount_usd"] for f in filas}
    for (scope, group), puestos in ESCALA_2026.items():
        for position, amount in puestos.items():
            assert por_clave[(scope, group, position)] == amount

    equipos = [f for f in filas if f["group_key"] == "EQUIPOS"]
    assert {f["amount_usd"] for f in equipos} == {500, 400, 300}
