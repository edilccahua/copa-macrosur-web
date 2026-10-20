"""
Tests de las reglas de seleccion de los segmentos Strava.

Tres reglas, cada una con su caso:
  1. el intento debe ser de la fecha de la carrera;
  2. el corredor debe haber competir en esa fecha;
  3. el segmento que cubre la carrera entera no se muestra, y se eligen
     los mas relevantes (maximo 5).
"""
import pytest

from backend.app.services.strava_selection import (
    filter_efforts,
    is_full_route,
    is_measured_on_stage,
    select_segments,
    segment_relevance,
)


# --------------------------------------------------------------------------
# Regla 1 — la fecha de medición
# --------------------------------------------------------------------------


def test_effort_measured_on_the_race_date_counts():
    """El intento del día de la carrera cuenta."""
    assert is_measured_on_stage("2026-05-17", "2026-05-17") is True


def test_effort_measured_one_day_before_counts():
    """Un día de diferencia se tolera: el desfase de zona horaria."""
    assert is_measured_on_stage("2026-05-16", "2026-05-17") is True
    assert is_measured_on_stage("2026-05-18", "2026-05-17") is True


def test_effort_measured_on_another_date_does_not_count():
    """Un intento de 2019 no es de nuestra carrera."""
    assert is_measured_on_stage("2019-09-08", "2026-05-17") is False
    assert is_measured_on_stage("2024-11-02", "2026-05-17") is False


def test_effort_without_date_does_not_count():
    """Sin fecha no se puede afirmar nada: no cuenta."""
    assert is_measured_on_stage(None, "2026-05-17") is False
    assert is_measured_on_stage("2026-05-17", None) is False


# --------------------------------------------------------------------------
# Regla 2 — el cruce con los pilotos
# --------------------------------------------------------------------------


def test_filter_keeps_only_efforts_of_race_day_and_race_riders():
    """Solo cuentan los intentos de la carrera, de corredores inscritos."""
    efforts = [
        {"measured_on": "2026-05-17", "rider_id": 10, "athlete_name_raw": "A"},
        {"measured_on": "2026-05-17", "rider_id": 20, "athlete_name_raw": "B"},
        {"measured_on": "2019-09-08", "rider_id": 10, "athlete_name_raw": "A"},
        {"measured_on": "2026-05-17", "rider_id": 99, "athlete_name_raw": "C"},
    ]
    result = filter_efforts(
        efforts, stage_date="2026-05-17", stage_rider_ids=[10, 20]
    )
    assert len(result) == 2
    assert {e["rider_id"] for e in result} == {10, 20}


def test_filter_keeps_unmatched_riders_when_stage_has_no_riders():
    """Sin inscripciones cruzadas no se descarta a nadie por eso."""
    efforts = [{"measured_on": "2026-05-17", "rider_id": None}]
    result = filter_efforts(efforts, stage_date="2026-05-17", stage_rider_ids=[])
    assert len(result) == 1


# --------------------------------------------------------------------------
# Regla 3 — la seleccion de segmentos
# --------------------------------------------------------------------------


def test_full_route_segment_is_detected():
    """El segmento que cubre la carrera entera es la ruta, no un tramo."""
    # 38.8 km sobre una etapa de 40.85 km: es el 95% de la carrera.
    assert is_full_route(38.8, 40.85) is True
    # Sobre una etapa de 60 km, 38.8 km NO es la ruta entera.
    assert is_full_route(38.8, 60.0) is False
    assert is_full_route(6.92, 40.85) is False


def test_select_segments_drops_the_full_route():
    """La ruta entera no se muestra entre los segmentos."""
    segments = [
        {"name": "La Joya Xtreme 26", "distance_km": 38.8, "average_grade": -1.6, "kind": "DESCENT"},
        {"name": "Perro rabioso - trepada", "distance_km": 1.0, "average_grade": 4.5, "kind": "CLIMB"},
        {"name": "A la Joya", "distance_km": 5.51, "average_grade": -3.9, "kind": "DESCENT"},
    ]
    selected = select_segments(segments, stage_distance_km=40.85)
    names = [s["name"] for s in selected]
    assert "La Joya Xtreme 26" not in names
    assert len(names) == 2


def test_select_segments_caps_at_five():
    """Como maximo cinco segmentos."""
    segments = [
        {"name": f"S{i}", "distance_km": 1.0 + i, "average_grade": 1.0 + i * 0.5, "kind": "CLIMB"}
        for i in range(9)
    ]
    selected = select_segments(segments, stage_distance_km=40.85)
    assert len(selected) == 5


def test_relevance_prefers_climb_then_descent_then_flat():
    """El orden de relevancia: subidas, bajadas y por ultimo los llanos."""
    climb = {"kind": "CLIMB", "average_grade": 4.0, "distance_km": 1.0}
    descent = {"kind": "DESCENT", "average_grade": 4.0, "distance_km": 1.0}
    flat = {"kind": "FLAT", "average_grade": 0.0, "distance_km": 1.0}
    assert segment_relevance(climb) < segment_relevance(descent)
    assert segment_relevance(descent) < segment_relevance(flat)


def test_relevance_prefers_the_steeper_and_longer():
    """A igualdad de tipo, manda la pendiente y luego la longitud."""
    steep = {"kind": "CLIMB", "average_grade": 6.0, "distance_km": 2.0}
    mild = {"kind": "CLIMB", "average_grade": 2.0, "distance_km": 2.0}
    assert segment_relevance(steep) < segment_relevance(mild)

    # Un tramo de 2 km al 6% es mas relevante que uno de 400 m al 6%: un
    # puerto de 400 m no es un puerto.
    short = {"kind": "CLIMB", "average_grade": 6.0, "distance_km": 0.4}
    assert segment_relevance(steep) < segment_relevance(short)
