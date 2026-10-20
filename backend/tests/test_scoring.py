import pytest
import datetime
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from backend.app.models.entities import (
    Rider, Category, Stage, StageEntry, RaceStatusEnum, GenderEnum,
    ChampionshipStanding, Team, TeamChampionshipStanding
)
from backend.app.services.scoring import (
    calculate_points_for_rank, recalculate_stage_ranks,
    recalculate_championship_standings, recalculate_team_standings,
    merge_duplicate_entries
)


def test_calculate_points_scale():
    # 1° al 10° lugar
    assert calculate_points_for_rank(1, RaceStatusEnum.FINISHED) == 10
    assert calculate_points_for_rank(2, RaceStatusEnum.FINISHED) == 9
    assert calculate_points_for_rank(3, RaceStatusEnum.FINISHED) == 8
    assert calculate_points_for_rank(10, RaceStatusEnum.FINISHED) == 1
    # 11° en adelante: 1 punto de persistencia
    assert calculate_points_for_rank(11, RaceStatusEnum.FINISHED) == 1
    assert calculate_points_for_rank(45, RaceStatusEnum.FINISHED) == 1
    # DNF, DNS, DSQ -> 0 puntos
    assert calculate_points_for_rank(1, RaceStatusEnum.DNF) == 0
    assert calculate_points_for_rank(5, RaceStatusEnum.DNS) == 0
    assert calculate_points_for_rank(2, RaceStatusEnum.DSQ) == 0


@pytest.mark.asyncio
async def test_recalculate_stage_ranks_and_uci_tiebreaker(async_session: AsyncSession):
    # 1. Crear categoría y etapa
    cat = Category(name="Elite Varones", short_code="ELI-M")
    stage1 = Stage(stage_number=1, name="Fecha 1", slug="f1", date=datetime.date(2026, 3, 15))
    stage2 = Stage(stage_number=2, name="Fecha 2", slug="f2", date=datetime.date(2026, 4, 15))
    async_session.add_all([cat, stage1, stage2])
    await async_session.commit()

    # 2. Crear 2 corredores
    r1 = Rider(dni="11111111", full_name="Ciclista A", slug="ciclista-a", gender=GenderEnum.M)
    r2 = Rider(dni="22222222", full_name="Ciclista B", slug="ciclista-b", gender=GenderEnum.M)
    async_session.add_all([r1, r2])
    await async_session.commit()

    # En Fecha 1: R1 gana (10 pts, 1h), R2 sale segundo (9 pts, 1h 05m)
    e1_s1 = StageEntry(stage_id=stage1.id, rider_id=r1.id, category_id=cat.id, bib_number=1, finish_elapsed_ms=3600000, race_status=RaceStatusEnum.FINISHED)
    e2_s1 = StageEntry(stage_id=stage1.id, rider_id=r2.id, category_id=cat.id, bib_number=2, finish_elapsed_ms=3900000, race_status=RaceStatusEnum.FINISHED)
    async_session.add_all([e1_s1, e2_s1])
    await async_session.commit()

    await recalculate_stage_ranks(async_session, stage1.id)
    await recalculate_championship_standings(async_session)

    # Verificar Fecha 1
    st1 = (await async_session.exec(select(ChampionshipStanding).where(ChampionshipStanding.rider_id == r1.id))).first()
    st2 = (await async_session.exec(select(ChampionshipStanding).where(ChampionshipStanding.rider_id == r2.id))).first()
    assert st1.current_rank == 1
    assert st1.total_points == 10
    assert st2.current_rank == 2
    assert st2.total_points == 9

    # En Fecha 2: R2 gana (10 pts), R1 sale segundo (9 pts) -> Empate en 19 puntos
    # Desempate UCI: R2 debe quedar 1° por haber obtenido mejor puesto en la última fecha disputada
    e1_s2 = StageEntry(stage_id=stage2.id, rider_id=r1.id, category_id=cat.id, bib_number=1, finish_elapsed_ms=4000000, race_status=RaceStatusEnum.FINISHED)
    e2_s2 = StageEntry(stage_id=stage2.id, rider_id=r2.id, category_id=cat.id, bib_number=2, finish_elapsed_ms=3500000, race_status=RaceStatusEnum.FINISHED)
    async_session.add_all([e1_s2, e2_s2])
    await async_session.commit()

    await recalculate_stage_ranks(async_session, stage2.id)
    await recalculate_championship_standings(async_session)

    st1_after = (await async_session.exec(select(ChampionshipStanding).where(ChampionshipStanding.rider_id == r1.id))).first()
    st2_after = (await async_session.exec(select(ChampionshipStanding).where(ChampionshipStanding.rider_id == r2.id))).first()

    assert st1_after.total_points == 19
    assert st2_after.total_points == 19
    # R2 ganó la última fecha, por lo que desempata a su favor
    assert st2_after.current_rank == 1
    assert st1_after.current_rank == 2


@pytest.mark.asyncio
async def test_recalculate_team_standings_olympic(async_session: AsyncSession):
    team_a = Team(name="Team Alpha", slug="team-alpha")
    team_b = Team(name="Team Beta", slug="team-beta")
    cat = Category(name="Open", short_code="OPN")
    stage = Stage(stage_number=1, name="Fecha 1", slug="f1", date=datetime.date(2026, 3, 15))
    async_session.add_all([team_a, team_b, cat, stage])
    await async_session.commit()

    r1 = Rider(dni="33333333", full_name="Alpha Rider 1", slug="a1", team_id=team_a.id)
    r2 = Rider(dni="44444444", full_name="Beta Rider 1", slug="b1", team_id=team_b.id)
    async_session.add_all([r1, r2])
    await async_session.commit()

    # R1 gana para Team Alpha (1° puesto, 10 pts)
    # R2 sale 2° para Team Beta (2° puesto, 9 pts)
    e1 = StageEntry(stage_id=stage.id, rider_id=r1.id, team_id=team_a.id, category_id=cat.id, bib_number=10, finish_elapsed_ms=3600000, category_rank=1, points_earned=10, race_status=RaceStatusEnum.FINISHED)
    e2 = StageEntry(stage_id=stage.id, rider_id=r2.id, team_id=team_b.id, category_id=cat.id, bib_number=20, finish_elapsed_ms=3700000, category_rank=2, points_earned=9, race_status=RaceStatusEnum.FINISHED)
    async_session.add_all([e1, e2])
    await async_session.commit()

    await recalculate_team_standings(async_session, stage.id)

    ts_a = (await async_session.exec(select(TeamChampionshipStanding).where(TeamChampionshipStanding.team_id == team_a.id))).first()
    ts_b = (await async_session.exec(select(TeamChampionshipStanding).where(TeamChampionshipStanding.team_id == team_b.id))).first()

    assert ts_a.current_rank == 1
    assert ts_a.total_points == 10
    assert ts_a.first_places_count == 1
    assert ts_b.current_rank == 2
    assert ts_b.total_points == 9
    assert ts_b.second_places_count == 1


@pytest.mark.asyncio
async def test_merge_duplicate_entries_keeps_best_time(async_session: AsyncSession):
    cat = Category(name="Master D", short_code="MSD")
    stage = Stage(stage_number=2, name="Fecha 2", slug="f2", date=datetime.date(2026, 6, 1))
    async_session.add_all([cat, stage])
    await async_session.commit()

    rider = Rider(dni="99999999", full_name="GUSTAVO OVIEDO", slug="gustavo-oviedo-9999")
    async_session.add(rider)
    await async_session.commit()

    # Mismo rider listado dos veces (dorsal 108 con tiempo, dorsal 241 sin tiempo)
    e_best = StageEntry(stage_id=stage.id, rider_id=rider.id, category_id=cat.id, bib_number=108,
                        finish_elapsed_ms=4277000, race_status=RaceStatusEnum.FINISHED)
    e_dup = StageEntry(stage_id=stage.id, rider_id=rider.id, category_id=cat.id, bib_number=241,
                       finish_elapsed_ms=None, race_status=RaceStatusEnum.REGISTERED)
    async_session.add_all([e_best, e_dup])
    await async_session.commit()

    merged = await merge_duplicate_entries(async_session, stage.id)
    assert merged == 1

    entries = (await async_session.exec(
        select(StageEntry).where(StageEntry.stage_id == stage.id)
    )).all()
    assert len(entries) == 1
    assert entries[0].bib_number == 108
    assert entries[0].finish_elapsed_ms == 4277000
