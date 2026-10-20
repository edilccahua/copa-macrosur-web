"""
Tests del motor de clasificación por ámbito y fecha (`standings_service`).

Cubre:
  - El ranking COMBINADO (PRO + NORMAL pooled) tiene un único puesto general.
  - El corte "a la fecha N" solo suma los resultados de las fechas <= N.
  - La diferencia al líder es la brecha de tiempo acumulado.
  - La DELTA compara contra la fecha anterior (y marca "NUEVO" a quien debuta).
  - El filtro por categoría devuelve el ranking de esa categoría con su puesto.
  - Los equipos se acumulan a la fecha con sus medallas.
"""
import datetime

import pytest
from sqlmodel import select

from backend.app.models.entities import (
    Category, Stage, StageEntry, Rider, Team, RaceStatusEnum, PaymentStatusEnum,
)
from backend.app.services.standings_service import (
    SCOPE_GROUPS, SCOPE_LABELS, compute_standings, compute_team_standings,
)


STAGE_1 = dict(stage_number=1, name="Fecha 1: La Joya Extreme", slug="f1",
               date=datetime.date(2026, 5, 17), status="FINISHED")
STAGE_2 = dict(stage_number=2, name="Fecha 2: Z Xtreme 2026", slug="f2",
               date=datetime.date(2026, 8, 23), status="FINISHED")


def ms(h, m, s=0):
    return ((h * 3600) + (m * 60) + s) * 1000


@pytest.fixture
async def world(async_session):
    """Dos fechas, tres categorías (ELITE/MASTER A/MASTER B) y cuatro corredores."""
    s = async_session

    cats = {}
    for name, code in (("ELITE", "ELI"), ("MASTER A", "MSA"), ("MASTER B", "MSB")):
        c = Category(name=name, short_code=code, aliases=[name])
        s.add(c)
        await s.flush()
        cats[code] = c

    team_a = Team(name="TEAM ALPHA", slug="team-alpha")
    team_b = Team(name="TEAM BETA", slug="team-beta")
    s.add_all([team_a, team_b])
    await s.flush()

    stages = {}
    for st in (STAGE_1, STAGE_2):
        stage = Stage(**st)
        s.add(stage)
        await s.flush()
        stages[stage.stage_number] = stage

    riders = {}
    for dni, name, team in (("10000001", "ALEX ALPHA", team_a),
                            ("10000002", "BETA BRAVO", team_b),
                            ("10000003", "GAMMA GOLF", team_a),
                            ("10000004", "DELTA DELTA", team_b),
                            ("10000005", "EPSILON ECHO", team_b)):
        r = Rider(dni=dni, full_name=name, slug=name.lower().replace(" ", "-"), team_id=team.id)
        s.add(r)
        await s.flush()
        riders[dni] = r

    # Fecha 1: ALEX gana ELITE(10), BETA gana MASTER A(10), GAMMA gana MASTER B(10)
    entries = [
        (riders["10000001"], stages[1], cats["ELI"], team_a, 11, ms(1, 0, 0), 1, 10),
        (riders["10000002"], stages[1], cats["MSA"], team_b, 12, ms(1, 2, 0), 1, 10),
        (riders["10000003"], stages[1], cats["MSB"], team_a, 13, ms(1, 4, 0), 1, 10),
        (riders["10000004"], stages[1], cats["MSB"], team_b, 14, ms(1, 6, 0), 2, 9),
        # Fecha 2: GAMMA debuta en MASTER A y lo gana; EPSILON debuta en la fecha 2
        (riders["10000003"], stages[2], cats["MSA"], team_a, 15, ms(2, 0, 0), 1, 10),
        (riders["10000001"], stages[2], cats["ELI"], team_a, 16, ms(2, 3, 0), 2, 9),
        (riders["10000005"], stages[2], cats["MSB"], team_b, 17, ms(2, 8, 0), 3, 8),
    ]
    for rider, stage, cat, team, bib, elapsed, rank, points in entries:
        s.add(StageEntry(
            stage_id=stage.id, rider_id=rider.id, category_id=cat.id, team_id=team.id,
            bib_number=bib, payment_status=PaymentStatusEnum.PAID,
            race_status=RaceStatusEnum.FINISHED, finish_elapsed_ms=elapsed,
            category_rank=rank, points_earned=points,
        ))
    await s.commit()
    return dict(session=s, cats=cats, teams=(team_a, team_b), stages=stages, riders=riders)


# --- Ámbitos -----------------------------------------------------------------

def test_scope_groups_cover_every_official_category():
    assert SCOPE_GROUPS["PRO"] == ["ELI", "MSA", "MSB", "MSC"]
    assert SCOPE_GROUPS["NORMAL"] == ["TOV", "TMV", "MSD", "OPD", "DMM", "JUV"]
    assert SCOPE_GROUPS["E-MTB"] == ["EBK"]
    assert set(SCOPE_LABELS) == {"PRO", "NORMAL", "E-MTB"}


# --- Ranking combinado -------------------------------------------------------

@pytest.mark.asyncio
async def test_scope_ranks_all_its_categories_in_a_single_table(world):
    rows = await compute_standings(world["session"], stage_limit=None, scope="PRO")
    by_name = {r["rider_name"]: r for r in rows}

    # GAMMA: 10 + 10 = 20 pts | ALEX: 10 + 9 = 19 | BETA: 10 | DELTA: 9 | EPSILON: 8
    assert by_name["ALEX ALPHA"]["total_points"] == 19
    assert by_name["BETA BRAVO"]["total_points"] == 10
    assert by_name["GAMMA GOLF"]["total_points"] == 20

    # GAMMA gana el combinado (20 pts) -> el primero de la tabla
    assert rows[0]["rider_name"] == "GAMMA GOLF"
    assert rows[0]["current_rank"] == 1
    assert rows[0]["gap_to_leader_ms"] == 0

    # El líder por puntos puede ser más lento que otro: la diferencia lleva signo
    assert by_name["ALEX ALPHA"]["current_rank"] == 2
    assert by_name["ALEX ALPHA"]["gap_to_leader_ms"] == -60000
    assert by_name["ALEX ALPHA"]["formatted_gap"] == "-00:01:00"


@pytest.mark.asyncio
async def test_scope_keeps_the_rank_inside_each_category(world):
    rows = await compute_standings(world["session"], stage_limit=None, scope="PRO")
    by_name = {r["rider_name"]: r for r in rows}
    assert by_name["ALEX ALPHA"]["category_rank"] == 1
    assert by_name["ALEX ALPHA"]["category_name"] == "ELITE"
    assert by_name["BETA BRAVO"]["category_rank"] == 1
    assert by_name["BETA BRAVO"]["category_name"] == "MASTER A"


@pytest.mark.asyncio
async def test_scope_pro_only_includes_pro_categories(world):
    rows = await compute_standings(world["session"], stage_limit=None, scope="PRO")
    assert {r["category_name"] for r in rows} <= {"ELITE", "MASTER A", "MASTER B"}
    assert len(rows) == 5


@pytest.mark.asyncio
async def test_unknown_scope_does_not_filter_categories(world):
    """Un ámbito desconocido no debe dejar la tabla vacía."""
    rows = await compute_standings(world["session"], stage_limit=None, scope="X")
    assert len(rows) == 5


# --- Corte por fecha ---------------------------------------------------------

@pytest.mark.asyncio
async def test_stage_limit_cuts_the_accumulated_totals(world):
    rows = await compute_standings(world["session"], stage_limit=1, scope="PRO")
    by_name = {r["rider_name"]: r for r in rows}
    assert by_name["ALEX ALPHA"]["total_points"] == 10
    assert by_name["ALEX ALPHA"]["stages_completed"] == 1
    assert by_name["GAMMA GOLF"]["total_points"] == 10


@pytest.mark.asyncio
async def test_delta_compares_against_the_previous_stage(world):
    rows = await compute_standings(world["session"], stage_limit=2, scope="PRO")
    by_name = {r["rider_name"]: r for r in rows}
    # Tras la fecha 1 el orden (10 pts, 1 victoria, menor tiempo) era
    # ALEX 1º, BETA 2º, GAMMA 3º, DELTA 4º.
    # Con la fecha 2: GAMMA 20 pts 1º, ALEX 19 pts 2º, BETA 3º, DELTA 4º, EPSILON 5º.
    assert by_name["GAMMA GOLF"]["previous_rank"] == 3
    assert by_name["GAMMA GOLF"]["rank_delta"] == 2      # subió 2 puestos
    assert by_name["ALEX ALPHA"]["previous_rank"] == 1
    assert by_name["ALEX ALPHA"]["rank_delta"] == -1     # bajó 1 puesto
    assert by_name["DELTA DELTA"]["rank_delta"] == 0

    # Quien debuta en la fecha 2 se marca como NUEVO (sin puesto anterior)
    assert by_name["EPSILON ECHO"]["previous_rank"] is None
    assert by_name["EPSILON ECHO"]["is_debut"] is True
    assert by_name["GAMMA GOLF"]["is_debut"] is False


@pytest.mark.asyncio
async def test_first_stage_has_no_delta(world):
    rows = await compute_standings(world["session"], stage_limit=1, scope="PRO")
    assert all(r["rank_delta"] == 0 for r in rows)
    assert all(r["previous_rank"] is None for r in rows)
    # En la primera fecha no hay debut: nadie "debuta" cuando no hay fecha previa.
    assert all(r["is_debut"] is False for r in rows)


# --- Filtro por categoría ----------------------------------------------------

@pytest.mark.asyncio
async def test_category_filter_returns_only_that_category(world):
    cat_id = world["cats"]["MSA"].id
    rows = await compute_standings(world["session"], stage_limit=None,
                                    scope="PRO", category_id=cat_id)
    assert {r["category_name"] for r in rows} == {"MASTER A"}
    assert all(r["current_rank"] == r["category_rank"] for r in rows)


@pytest.mark.asyncio
async def test_standings_context_lists_stages_and_categories(world):
    """El contexto alimenta los selectores de la página: fechas y catálogo de categorías."""
    from backend.app.services.standings_service import standings_context

    ctx = await standings_context(world["session"], stage_limit=None)
    assert [s["stage_number"] for s in ctx["stages"]] == [1, 2]
    assert ctx["selected_stage_id"] == 2
    assert ctx["stages_counted"] == 2
    assert len(ctx["categories"]) == 3
    assert {c["short_code"] for c in ctx["categories"]} == {"ELI", "MSA", "MSB"}
    assert ctx["groups"]["PRO"] == ["ELI", "MSA", "MSB", "MSC"]


# --- Equipos -----------------------------------------------------------------

@pytest.mark.asyncio
async def test_team_standings_accumulate_points_to_the_selected_stage(world):
    rows = await compute_team_standings(world["session"], stage_limit=1)
    by_name = {r["team_name"]: r for r in rows}
    # Fecha 1: TEAM ALPHA = 10 (ALEX) + 10 (GAMMA) = 20 | TEAM BETA = 10 + 9 = 19
    assert by_name["TEAM ALPHA"]["total_points"] == 20
    assert by_name["TEAM BETA"]["total_points"] == 19
    assert by_name["TEAM ALPHA"]["current_rank"] == 1
    assert by_name["TEAM ALPHA"]["gap_to_leader_ms"] == 0
    assert by_name["TEAM BETA"]["gap_to_leader_ms"] == ms(1, 4, 0) - ms(1, 0, 0)


@pytest.mark.asyncio
async def test_team_standings_cut_by_stage(world):
    rows = await compute_team_standings(world["session"], stage_limit=2)
    by_name = {r["team_name"]: r for r in rows}
    # Fecha 2: ALPHA = 20 + 10 (GAMMA) + 9 (ALEX) = 39
    #          BETA  = 19 (10 + 9) + 8 (EPSILON) = 27
    assert by_name["TEAM ALPHA"]["total_points"] == 39
    assert by_name["TEAM BETA"]["total_points"] == 27


# --- Modo "fecha" (una sola carrera, sin acumulado) --------------------------
#
# El modo "fecha" NO es un acumulado con otro corte: es la clasificación de la
# CARRERA exacta. Solo cuentan sus puntos y su tiempo, y no hay DELTA porque no
# existe una clasificación previa con la que compararse.

@pytest.mark.asyncio
async def test_fecha_mode_counts_only_that_stage(world):
    stage2 = world["stages"][2].id
    rows = await compute_standings(world["session"], stage_limit=stage2, scope="PRO",
                                    mode="fecha")
    by_name = {r["rider_name"]: r for r in rows}

    # Fecha 2: GAMMA 10 (1º MASTER A), ALEX 9 (2º ELITE), EPSILON 8 (3º MASTER B).
    assert by_name["GAMMA GOLF"]["total_points"] == 10
    assert by_name["ALEX ALPHA"]["total_points"] == 9
    assert by_name["EPSILON ECHO"]["total_points"] == 8

    # El tiempo también es el de esa carrera, no el acumulado.
    assert by_name["ALEX ALPHA"]["total_elapsed_ms"] == ms(2, 3, 0)
    assert by_name["ALEX ALPHA"]["stages_completed"] == 1

    # Quien no corrió esa fecha no aparece en la tabla.
    assert "BETA BRAVO" not in by_name
    assert "DELTA DELTA" not in by_name


@pytest.mark.asyncio
async def test_fecha_mode_has_no_delta(world):
    """Una carrera aislada no tiene con qué compararse: el Δ va vacío."""
    stage2 = world["stages"][2].id
    rows = await compute_standings(world["session"], stage_limit=stage2, scope="PRO",
                                    mode="fecha")
    assert all(r["rank_delta"] == 0 for r in rows)
    assert all(r["previous_rank"] is None for r in rows)
    assert all(r["is_debut"] is False for r in rows)


@pytest.mark.asyncio
async def test_fecha_mode_of_the_first_stage(world):
    stage1 = world["stages"][1].id
    rows = await compute_standings(world["session"], stage_limit=stage1, scope="PRO",
                                    mode="fecha")
    by_name = {r["rider_name"]: r for r in rows}
    assert by_name["ALEX ALPHA"]["total_points"] == 10
    assert by_name["GAMMA GOLF"]["total_points"] == 10
    # En la fecha 1 el acumulado y la fecha aislada coinciden.
    acumulado = await compute_standings(world["session"], stage_limit=stage1, scope="PRO")
    assert [r["rider_name"] for r in rows] == [r["rider_name"] for r in acumulado]


@pytest.mark.asyncio
async def test_acumulado_mode_is_untouched_by_the_new_mode(world):
    """El modo por defecto sigue siendo el acumulado hasta el corte."""
    stage2 = world["stages"][2].id
    rows = await compute_standings(world["session"], stage_limit=stage2, scope="PRO")
    by_name = {r["rider_name"]: r for r in rows}
    assert by_name["ALEX ALPHA"]["total_points"] == 19   # 10 + 9
    assert by_name["ALEX ALPHA"]["rank_delta"] == -1     # sí compara con la fecha 1


@pytest.mark.asyncio
async def test_team_standings_in_fecha_mode(world):
    stage2 = world["stages"][2].id
    rows = await compute_team_standings(world["session"], stage_limit=stage2, mode="fecha")
    by_name = {r["team_name"]: r for r in rows}
    # Solo la fecha 2: ALPHA = 10 (GAMMA) + 9 (ALEX) = 19 | BETA = 8 (EPSILON)
    assert by_name["TEAM ALPHA"]["total_points"] == 19
    assert by_name["TEAM BETA"]["total_points"] == 8
    assert by_name["TEAM ALPHA"]["total_riders"] == 2


@pytest.mark.asyncio
async def test_fecha_mode_context_counts_one_stage(world):
    """En modo fecha la cinta dice UNA fecha y la distancia es la de esa carrera."""
    from backend.app.services.standings_service import standings_context

    stage2 = world["stages"][2].id
    ctx = await standings_context(world["session"], stage_limit=stage2, mode="fecha")
    assert ctx["stages_counted"] == 1
    assert ctx["selected_stage_id"] == stage2

    ctx_acum = await standings_context(world["session"], stage_limit=stage2, mode="acumulado")
    assert ctx_acum["stages_counted"] == 2


@pytest.mark.asyncio
async def test_unknown_mode_falls_back_to_acumulado(world):
    stage2 = world["stages"][2].id
    rows = await compute_standings(world["session"], stage_limit=stage2, scope="PRO",
                                    mode="inventado")
    by_name = {r["rider_name"]: r for r in rows}
    assert by_name["ALEX ALPHA"]["total_points"] == 19
