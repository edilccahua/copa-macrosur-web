import datetime
import pytest
from backend.app.models.entities import Category, Stage, StageEntry, Rider, Team, RaceStatusEnum, PaymentStatusEnum
from backend.app.services.standings_service import compute_standings


@pytest.mark.asyncio
async def test_date_mode_todos_orders_by_finish_time(async_session):
    """
    En modo FECHA con categoría 'TODOS' (category_id is None):
    El orden oficial (scratch) es por tiempo de llegada (finish_elapsed_ms ASC),
    incluso si corredores de distintas categorías tienen los mismos puntos (10 pts).
    """
    s = async_session

    cat_elite = Category(name="ELITE", short_code="ELI", aliases=["ELITE"])
    cat_master = Category(name="MASTER A", short_code="MSA", aliases=["MASTER A"])
    s.add_all([cat_elite, cat_master])
    await s.flush()

    stage = Stage(stage_number=1, name="Fecha 1: La Joya Extreme", slug="f1",
                  date=datetime.date(2026, 5, 17), status="FINISHED")
    s.add(stage)
    await s.flush()

    r1 = Rider(dni="11111111", full_name="CORREDOR RAPIDO", slug="rapido")
    r2 = Rider(dni="22222222", full_name="CORREDOR LENTO", slug="lento")
    s.add_all([r1, r2])
    await s.flush()

    # Ambos ganaron su categoría (10 puntos cada uno), pero r1 hizo 1h y r2 hizo 2h
    e1 = StageEntry(
        stage_id=stage.id, rider_id=r1.id, category_id=cat_elite.id,
        bib_number=10, payment_status=PaymentStatusEnum.PAID,
        race_status=RaceStatusEnum.FINISHED, finish_elapsed_ms=3600000,
        points_earned=10, category_rank=1
    )
    e2 = StageEntry(
        stage_id=stage.id, rider_id=r2.id, category_id=cat_master.id,
        bib_number=20, payment_status=PaymentStatusEnum.PAID,
        race_status=RaceStatusEnum.FINISHED, finish_elapsed_ms=7200000,
        points_earned=10, category_rank=1
    )
    s.add_all([e1, e2])
    await s.commit()

    # 1. En modo FECHA con category_id=None (TODOS): r1 (más rápido) debe ser 1º
    rows_date_all = await compute_standings(s, stage_limit=stage.id, mode="fecha", category_id=None, scope="COMBINED")
    assert len(rows_date_all) == 2
    assert rows_date_all[0]["rider_name"] == "CORREDOR RAPIDO"
    assert rows_date_all[0]["current_rank"] == 1
    assert rows_date_all[1]["rider_name"] == "CORREDOR LENTO"
    assert rows_date_all[1]["current_rank"] == 2

    # 2. En modo ACUMULADO: el desempate por puntos aplica
    rows_accum = await compute_standings(s, stage_limit=stage.id, mode="acumulado", category_id=None, scope="COMBINED")
    assert len(rows_accum) == 2
    assert rows_accum[0]["rider_name"] == "CORREDOR RAPIDO"  # desempata por tiempo al tener mismos puntos
