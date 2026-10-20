import os
import pytest
from sqlmodel import select

from backend.app.models.entities import (
    Category, Stage, StageEntry, Rider, Team, RaceStatusEnum, ChampionshipStanding,
)
from backend.app.seed import (
    RACE_CONFIG, seed_categories, upsert_stage, load_results,
)
from backend.app.services.pdf_service import extract_race_results_from_pdf

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RACES_DIR = os.path.join(REPO_ROOT, "races")

JOYA_PDF = os.path.join(RACES_DIR, "1. LA JOYA EXTREME 2026  RESULTADOS.pdf")
ZETA_PDF = os.path.join(RACES_DIR, "LA Z XTREME 2026 - RESULTADOS.-1.pdf")

# Cifras oficiales verificadas con dos oráculos independientes
# (pdfplumber por coordenadas y pdftotext -raw).
OFFICIAL_TOTALS = {
    "la-joya-extreme": {"results": 198, "points": 667, "pdf": JOYA_PDF},
    "z-xtreme-2026": {"results": 112, "points": 555, "pdf": ZETA_PDF},
}


async def _seed_stage(async_session, monkeypatch, cfg):
    monkeypatch.chdir(REPO_ROOT)
    cat_map = await seed_categories(async_session)
    stage = await upsert_stage(async_session, cfg)
    await async_session.commit()
    await load_results(async_session, stage, cfg, cat_map)
    entries = (
        await async_session.exec(
            select(StageEntry).where(StageEntry.stage_id == stage.id)
        )
    ).all()
    return stage, entries


def _official_rows(pdf_path):
    return {r["bib_number"]: r for r in extract_race_results_from_pdf(pdf_path)}


@pytest.mark.asyncio
@pytest.mark.parametrize("stage_index", [0, 1])
async def test_seed_loads_every_official_result_with_its_own_time(
    async_session, monkeypatch, stage_index
):
    """Cada resultado del PDF oficial debe existir en la BD con SU tiempo."""
    cfg = RACE_CONFIG[stage_index]
    official = OFFICIAL_TOTALS[cfg["slug"]]
    stage, entries = await _seed_stage(async_session, monkeypatch, cfg)

    finished = [e for e in entries if e.finish_elapsed_ms is not None]
    assert len(finished) == official["results"], (
        f"{cfg['name']}: se esperaban {official['results']} resultados oficiales "
        f"y se cargaron {len(finished)}"
    )

    rows = _official_rows(official["pdf"])
    by_bib = {e.bib_number: e for e in finished}
    missing = sorted(set(rows) - set(by_bib))
    assert not missing, f"dorsales del PDF oficial sin resultado cargado: {missing}"

    for bib, row in rows.items():
        assert by_bib[bib].finish_elapsed_ms == row["elapsed_ms"], (
            f"dorsal {bib}: tiempo {by_bib[bib].finish_elapsed_ms} != oficial {row['elapsed_ms']}"
        )
        assert by_bib[bib].race_status == RaceStatusEnum.FINISHED
        assert by_bib[bib].category_rank is not None
        assert by_bib[bib].category_rank >= 1


@pytest.mark.asyncio
@pytest.mark.parametrize("stage_index", [0, 1])
async def test_seed_ranks_are_continuous_within_each_category(
    async_session, monkeypatch, stage_index
):
    """El puesto por categoría va de 1..N sin huecos ni duplicados."""
    cfg = RACE_CONFIG[stage_index]
    stage, entries = await _seed_stage(async_session, monkeypatch, cfg)

    by_cat = {}
    for e in entries:
        if e.category_rank is None:
            continue
        by_cat.setdefault(e.category_id, []).append(e.category_rank)

    assert by_cat, "no hay resultados clasificados"
    for cat_id, ranks in by_cat.items():
        assert sorted(ranks) == list(range(1, len(ranks) + 1)), (
            f"categoría {cat_id}: puestos no continuos {sorted(ranks)}"
        )


@pytest.mark.asyncio
async def test_seed_points_follow_the_official_ten_point_scale(
    async_session, monkeypatch
):
    """Los puntos de cada categoría siguen la escala 10..1 (specs/01 §3.1)."""
    cfg = RACE_CONFIG[0]
    stage, entries = await _seed_stage(async_session, monkeypatch, cfg)

    def expected_points(rank):
        if rank == 1:
            return 10
        return max(1, 11 - rank)

    for e in entries:
        if e.category_rank is None:
            assert e.points_earned == 0
        else:
            assert e.points_earned == expected_points(e.category_rank)

    total = sum(e.points_earned for e in entries if e.category_rank is not None)
    assert total == OFFICIAL_TOTALS["la-joya-extreme"]["points"]


@pytest.mark.asyncio
async def test_seed_does_not_duplicate_teams_normalizing_the_broken_club_name(
    async_session, monkeypatch
):
    """'CLUB ORIGINAL BIKES AREQUIPA- PERÚ' (Partido por el PDF) es el mismo club."""
    cfg = RACE_CONFIG[0]
    await _seed_stage(async_session, monkeypatch, cfg)

    teams = (await async_session.exec(select(Team))).all()
    names = [t.name for t in teams]
    assert len(names) == len(set(names)), f"equipos duplicados: {names}"

    arequipa = [n for n in names if "AREQUIPA" in n and "PERÚ" in n]
    assert arequipa == ["CLUB ORIGINAL BIKES AREQUIPA-PERÚ"], arequipa


@pytest.mark.asyncio
async def test_seed_keeps_the_official_bib_when_the_registration_list_differs(
    async_session, monkeypatch
):
    """El dorsal publicado en el PDF oficial manda sobre el de la lista de inscritos."""
    cfg = RACE_CONFIG[1]  # Z Xtreme
    stage, entries = await _seed_stage(async_session, monkeypatch, cfg)

    by_bib = {e.bib_number: e for e in entries}
    # Dorsales que el PDF oficial asigna y el Excel no
    for bib in (86, 166, 167):
        assert bib in by_bib, f"falta el dorsal oficial {bib}"
        assert by_bib[bib].finish_elapsed_ms is not None


@pytest.mark.asyncio
async def test_seed_assigns_the_official_result_by_bib_when_names_differ(
    async_session, monkeypatch
):
    """
    Dorsal 11: el PDF oficial dice 'CHARLES GONZALES' y la lista de inscritos
    'ANDRE GONZALES'. Son el mismo ciclista: el resultado oficial debe quedar
    cargado en su inscripción.
    """
    cfg = RACE_CONFIG[0]
    stage, entries = await _seed_stage(async_session, monkeypatch, cfg)

    by_bib = {e.bib_number: e for e in entries}
    entry = by_bib.get(11)
    assert entry is not None
    assert entry.finish_elapsed_ms == 4243000  # 01:10:43 oficial
    assert entry.race_status == RaceStatusEnum.FINISHED

    rider = (await async_session.exec(select(Rider).where(Rider.id == entry.rider_id))).first()
    assert rider is not None
    assert "GONZALES" in rider.full_name


@pytest.mark.asyncio
async def test_seed_creates_riders_that_only_exist_in_the_official_pdf(
    async_session, monkeypatch
):
    """Dorsales 184, 185, 269, 270 y 283 aparecen en el PDF oficial y no en el Excel."""
    cfg = RACE_CONFIG[0]
    stage, entries = await _seed_stage(async_session, monkeypatch, cfg)

    by_bib = {e.bib_number: e for e in entries}
    for bib, ms in ((184, 7729000), (185, 6104000), (269, 7450000), (270, 7472000), (283, 9488000)):
        assert bib in by_bib, f"falta el dorsal PDF-only {bib}"
        assert by_bib[bib].finish_elapsed_ms == ms
        assert by_bib[bib].category_rank is not None


@pytest.mark.asyncio
async def test_seed_removes_stale_championship_standings(async_session, monkeypatch):
    """No deben quedar filas de clasificación de corredores que ya no competes."""
    cfg = RACE_CONFIG[0]
    stage, entries = await _seed_stage(async_session, monkeypatch, cfg)

    # Se inyecta una clasificación obsoleta: un corredor que no disputó la fecha
    # (categoría sin ningún registró suyo) para garantizar que la fila es inválida.
    finished_pairs = {
        (e.rider_id, e.category_id) for e in entries if e.finish_elapsed_ms is not None
    }
    rider = (await async_session.exec(select(Rider))).first()
    cat = (await async_session.exec(select(Category))).first()
    for cand_r in (await async_session.exec(select(Rider))).all():
        for cand_c in (await async_session.exec(select(Category))).all():
            if (cand_r.id, cand_c.id) not in finished_pairs:
                rider, cat = cand_r, cand_c
                break
        else:
            continue
        break
    stale = ChampionshipStanding(
        rider_id=rider.id, category_id=cat.id, current_rank=99, total_points=99,
        first_places_count=0, last_stage_rank=None, total_elapsed_ms=0, stages_completed=0,
    )
    async_session.add(stale)
    await async_session.commit()
    assert (stale.rider_id, stale.category_id) not in finished_pairs

    await load_results(async_session, stage, cfg, await seed_categories(async_session))

    standings = (await async_session.exec(select(ChampionshipStanding))).all()
    finished = [e for e in entries if e.finish_elapsed_ms is not None]
    expected = {(e.rider_id, e.category_id) for e in finished}
    actual = {(s.rider_id, s.category_id) for s in standings}
    assert actual == expected, (
        f"clasificaciones obsoletas o faltantes: sobran={actual - expected}, "
        f"faltan={expected - actual}"
    )


@pytest.mark.asyncio
async def test_seed_gives_the_official_bib_to_the_rider_of_the_official_pdf(
    async_session, monkeypatch
):
    """
    En Z Xtreme el dorsal 147 es de WENDY NINA CHIRE (OPEN DAMAS) en el PDF oficial,
    pero la lista de inscritos lo asigna a ELMER EFRAIN MAMANI MAQUERA (TURISMO OPEN).
    El resultado oficial manda: WENDY entra con el dorsal 147 y ELMER conserva su
    inscripción sin resultado oficial (DNS), sin perder su fila.
    """
    cfg = RACE_CONFIG[1]
    stage, entries = await _seed_stage(async_session, monkeypatch, cfg)

    by_bib = {e.bib_number: e for e in entries}
    wendy = by_bib.get(147)
    assert wendy is not None, "falta el dorsal 147 oficial (WENDY NINA CHIRE)"
    assert wendy.finish_elapsed_ms == 6594000  # 1:49:54 oficial

    riders = {r.id: r for r in (await async_session.exec(select(Rider))).all()}
    elmer = [
        e for e in entries
        if "ELMER EFRAIN MAMANI MAQUERA" in riders[e.rider_id].full_name.upper()
    ]
    assert elmer, "ELMER EFRAIN MAMANI MAQUERA perdió su inscripción"
    assert elmer[0].finish_elapsed_ms is None, "ELMER no debe heredar el tiempo de otra categoría"
    assert elmer[0].race_status == RaceStatusEnum.DNS
    assert elmer[0].bib_number != 147, "el dorsal 147 ya pertenece al resultado oficial"
