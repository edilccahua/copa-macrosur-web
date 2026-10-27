import datetime
import pytest
from backend.app.models.entities import Stage, StageStatusEnum
from backend.app.routers.public import compute_hero_card, RECENT_RESULTS_WINDOW_DAYS


def _mock_stages():
    return [
        Stage(
            id=1,
            stage_number=1,
            name="Fecha 1: La Joya Extreme",
            slug="la-joya-extreme",
            date=datetime.date(2026, 5, 17),
            status=StageStatusEnum.FINISHED,
            laps=1,
            judge_pin="1111",
        ),
        Stage(
            id=2,
            stage_number=2,
            name="Fecha 2: Kúspide Z Xtreme III",
            slug="z-xtreme-2026",
            date=datetime.date(2026, 8, 23),
            status=StageStatusEnum.FINISHED,
            laps=3,
            judge_pin="2222",
        ),
        Stage(
            id=3,
            stage_number=3,
            name="Fecha 3: El Retorno a los Poblados 2",
            slug="vuelta-a-los-poblados",
            date=datetime.date(2026, 10, 25),
            status=StageStatusEnum.FINISHED,
            laps=1,
            judge_pin="3333",
        ),
        Stage(
            id=4,
            stage_number=4,
            name="Fecha 4: Quequeña Xtreme III",
            slug="quequena-xtreme",
            date=datetime.date(2026, 12, 13),
            status=StageStatusEnum.UPCOMING,
            laps=1,
            judge_pin="4444",
        ),
    ]


def test_hero_card_dia_1_post_carrera_muestra_resultados_recientes():
    stages = _mock_stages()
    # 26 de octubre de 2026: 1 día después de la Fecha 3 (25 de octubre)
    now = datetime.datetime(2026, 10, 26, 12, 0, 0)
    card = compute_hero_card(stages, now=now)

    assert card["mode"] == "recent_results"
    assert card["days_since_race"] == 1
    assert card["stage"]["stage_number"] == 3
    assert card["stage"]["slug"] == "vuelta-a-los-poblados"
    assert card["next_stage"] is not None
    assert card["next_stage"]["stage_number"] == 4


def test_hero_card_dia_10_post_carrera_sigue_en_resultados_recientes():
    stages = _mock_stages()
    # 4 de noviembre de 2026: 10 días exactos después de la Fecha 3 (25 de octubre)
    now = datetime.datetime(2026, 11, 4, 18, 0, 0)
    card = compute_hero_card(stages, now=now)

    assert card["mode"] == "recent_results"
    assert card["days_since_race"] == 10
    assert card["stage"]["stage_number"] == 3


def test_hero_card_dia_11_post_carrera_conmuta_a_proxima_carrera():
    stages = _mock_stages()
    # 5 de noviembre de 2026: 11 días después de la Fecha 3 -> expira ventana de gracia
    now = datetime.datetime(2026, 11, 5, 9, 0, 0)
    card = compute_hero_card(stages, now=now)

    assert card["mode"] == "upcoming"
    assert card["days_since_race"] is None
    assert card["stage"]["stage_number"] == 4
    assert card["stage"]["slug"] == "quequena-xtreme"


def test_hero_card_antes_de_primera_carrera_muestra_upcoming():
    stages = [
        Stage(
            id=1,
            stage_number=1,
            name="Fecha 1: La Joya Extreme",
            slug="la-joya-extreme",
            date=datetime.date(2026, 5, 17),
            status=StageStatusEnum.UPCOMING,
            laps=1,
            judge_pin="1111",
        )
    ]
    now = datetime.datetime(2026, 5, 1, 10, 0, 0)
    card = compute_hero_card(stages, now=now)

    assert card["mode"] == "upcoming"
    assert card["stage"]["stage_number"] == 1
