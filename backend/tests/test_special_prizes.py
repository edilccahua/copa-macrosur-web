"""Premio CLARO a la remontada (specs/03 §1.7).

Regla: terminó todas las fechas disputadas; gana la mayor subida de puestos
en su categoría entre la primera y la última. Provisional hasta la cuarta.
"""
from datetime import date

import pytest

from backend.app.models.entities import (
    Category,
    GenderEnum,
    RaceStatusEnum,
    Rider,
    Stage,
    StageEntry,
    StageStatusEnum,
)
from backend.app.services.special_prizes_service import compute_claro_remontada


async def make_category(session, name: str, code: str) -> Category:
    cat = Category(name=name, short_code=code)
    session.add(cat)
    await session.commit()
    await session.refresh(cat)
    return cat


async def make_stage(session, number: int) -> Stage:
    stage = Stage(
        stage_number=number,
        name=f"Fecha {number}",
        slug=f"fecha-{number}",
        date=date(2026, 1 + number, 1),
        status=StageStatusEnum.FINISHED,
    )
    session.add(stage)
    await session.commit()
    await session.refresh(stage)
    return stage


async def make_rider(session, name: str, dni: str) -> Rider:
    rider = Rider(
        dni=dni,
        full_name=name,
        slug=name.lower().replace(" ", "-").replace("-", ""),
        gender=GenderEnum.M,
    )
    session.add(rider)
    await session.commit()
    await session.refresh(rider)
    return rider


async def add_entry(
    session,
    stage: Stage,
    rider: Rider,
    category: Category,
    rank: int,
    bib: int,
) -> StageEntry:
    entry = StageEntry(
        stage_id=stage.id,
        rider_id=rider.id,
        category_id=category.id,
        bib_number=bib,
        race_status=RaceStatusEnum.FINISHED,
        finish_elapsed_ms=rank * 60_000,
        category_rank=rank,
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


@pytest.mark.asyncio
async def test_remontada_requires_all_disputed_stages_and_picks_biggest_gain(
    async_session,
):
    cat = await make_category(async_session, "ELITE", "ELI")
    f1 = await make_stage(async_session, 1)
    f2 = await make_stage(async_session, 2)

    a = await make_rider(async_session, "JUAN PEREZ-", "10000001")
    b = await make_rider(async_session, "PEDRO GOMEZ", "10000002")
    c = await make_rider(async_session, "LUIS SOLO UNO", "10000003")

    # A sube 15 puestos; B sube 2; C solo corrió la primera fecha.
    await add_entry(async_session, f1, a, cat, rank=20, bib=1)
    await add_entry(async_session, f2, a, cat, rank=5, bib=1)
    await add_entry(async_session, f1, b, cat, rank=10, bib=2)
    await add_entry(async_session, f2, b, cat, rank=8, bib=2)
    await add_entry(async_session, f1, c, cat, rank=5, bib=3)

    data = await compute_claro_remontada(async_session)

    assert data["title"] == "Premio CLARO"
    assert data["amount_usd"] == 100
    assert data["stages_counted"] == 2
    assert data["total_stages"] == 4
    assert data["provisional"] is True

    winner = data["winner"]
    assert winner is not None
    assert winner["rider_name"] == "JUAN PEREZ"  # sin el guion del PDF
    assert winner["first_rank"] == 20
    assert winner["last_rank"] == 5
    assert winner["positions_gained"] == 15
    assert winner["first_stage_number"] == 1
    assert winner["last_stage_number"] == 2


@pytest.mark.asyncio
async def test_remontada_without_positive_gain_has_no_winner(async_session):
    cat = await make_category(async_session, "MASTER A", "MSA")
    f1 = await make_stage(async_session, 1)
    f2 = await make_stage(async_session, 2)

    rider = await make_rider(async_session, "BAJA PUESTOS", "10000010")
    await add_entry(async_session, f1, rider, cat, rank=3, bib=10)
    await add_entry(async_session, f2, rider, cat, rank=12, bib=10)

    data = await compute_claro_remontada(async_session)
    assert data["winner"] is None


@pytest.mark.asyncio
async def test_remontada_is_not_provisional_after_four_stages(async_session):
    cat = await make_category(async_session, "ELITE", "ELI")
    stages = [await make_stage(async_session, n) for n in range(1, 5)]
    rider = await make_rider(async_session, "REMONTADA TOTAL", "10000020")

    for stage, rank in zip(stages, [30, 20, 10, 4]):
        await add_entry(async_session, stage, rider, cat, rank=rank, bib=7)

    data = await compute_claro_remontada(async_session)

    assert data["stages_counted"] == 4
    assert data["provisional"] is False
    assert data["winner"]["positions_gained"] == 26


@pytest.mark.asyncio
async def test_remontada_endpoint(client, async_session):
    cat = await make_category(async_session, "ELITE", "ELI")
    f1 = await make_stage(async_session, 1)
    f2 = await make_stage(async_session, 2)
    rider = await make_rider(async_session, "ENDPOINT RIDER", "10000030")
    await add_entry(async_session, f1, rider, cat, rank=15, bib=1)
    await add_entry(async_session, f2, rider, cat, rank=2, bib=1)

    res = await client.get("/api/v1/public/remontada")

    assert res.status_code == 200
    body = res.json()
    assert body["winner"]["rider_name"] == "ENDPOINT RIDER"
    assert body["winner"]["positions_gained"] == 13
