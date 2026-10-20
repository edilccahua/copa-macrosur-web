"""
Tests del perfil de ruta: la geometría real de cada etapa y las cimas que
produce.

Las cifras de referencia salen de `kuspide_mtb.db` (las rutas oficiales
sembradas desde `races/`).
"""
import json
import os
import sqlite3

import pytest

from backend.app.services.route_profile_service import (
    build_route_profile,
    extract_summits,
)

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "kuspide_mtb.db",
)


def _real_geojson(slug: str):
    """La geometría real de una fecha, leída de la BD de desarrollo."""
    if not os.path.exists(DB_PATH):
        pytest.skip(f"no hay BD de desarrollo en {DB_PATH}")
    con = sqlite3.connect(DB_PATH)
    try:
        raw = con.execute(
            "SELECT route_geojson, distance_km, elevation_gain_m, laps FROM stages WHERE slug=?",
            (slug,),
        ).fetchone()
    finally:
        con.close()
    if raw is None or not raw[0]:
        pytest.skip(f"la fecha {slug} no tiene geometría sembrada")
    return json.loads(raw[0]), raw[1], raw[2], raw[3]


def test_route_profile_from_real_geometry():
    """El perfil sale de la geometría, no de multiplicar distancia × vueltas."""
    geojson, distance_km, gain_m, laps = _real_geojson("la-joya-extreme")
    profile = build_route_profile(geojson, stage_laps=laps)

    assert profile is not None
    assert profile["distance_km"] == pytest.approx(distance_km, abs=0.2)
    assert profile["elevation_min_m"] == 1632
    assert profile["elevation_max_m"] == 2281
    # El desnivel acumulado NO es la diferencia entre máximo y mínimo: la ruta
    # tiene más bajada que subida (986 m perdidos frente a 359 m ganados).
    assert profile["elevation_gain_m"] == pytest.approx(359, abs=15)
    assert profile["elevation_loss_m"] > profile["elevation_gain_m"]
    assert profile["mean_grade_pct"] == pytest.approx(0.88, abs=0.1)
    assert profile["max_grade_pct"] > 30
    assert profile["geometry_covers_full_stage"] is True
    assert len(profile["points"]) == 500


def test_route_profile_on_lap_circuit_covers_one_lap():
    """En un circuito por vueltas la geometría es de UNA vuelta."""
    geojson, distance_km, gain_m, laps = _real_geojson("z-xtreme-2026")
    profile = build_route_profile(geojson, stage_laps=laps)

    assert profile is not None
    assert profile["distance_km"] == pytest.approx(distance_km, abs=0.2)
    assert profile["distance_km_stage"] == pytest.approx(distance_km * laps, abs=0.2)
    assert profile["geometry_covers_full_stage"] is False


def test_flat_route_has_degenerate_elevation_range():
    """Una vuelta llana: el rango de altitudes es 0 y no se divide por él."""
    flat = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[-71.0, -16.0, 100.0, 0.0], [-71.1, -16.0, 100.0, 5.0]],
                },
            }
        ],
    }
    profile = build_route_profile(flat)
    assert profile is not None
    assert profile["elevation_gain_m"] == 0
    assert profile["elevation_loss_m"] == 0
    assert profile["elevation_min_m"] == profile["elevation_max_m"] == 100
    assert profile["mean_grade_pct"] == 0.0
    assert profile["max_grade_pct"] == 0.0


def test_missing_geometry_returns_none():
    """Sin geometría no hay perfil: la página lo dice, no inventa."""
    assert build_route_profile(None) is None
    assert build_route_profile({"type": "FeatureCollection", "features": []}) is None


def test_summits_are_extracted_with_categories():
    """Las cimas salen de la geometría y llevan categoría de puerto."""
    geojson, distance_km, gain_m, laps = _real_geojson("la-joya-extreme")
    summits = extract_summits(geojson, geocode=False)

    assert len(summits) >= 1
    top = summits[0]
    assert top["climb_gain_m"] > 0
    assert top["elevation_m"] > 1600
    assert 0 < top["distance_km"] <= distance_km
    assert top["name"].startswith("CIMA")
    # La categoría sale de la longitud y la pendiente del tramo.
    assert top["category"] in {"HC", "1", "2", "3", ""}


def test_summits_of_poblados_carry_real_categories():
    """La vuelta a los poblados tiene subidas de categoría: son puertos."""
    geojson, *_ = _real_geojson("vuelta-a-los-poblados")
    summits = extract_summits(geojson, geocode=False)

    assert len(summits) >= 3
    # La mayor subida (km 8.0, +298 m, 8.6%) es categoría 3 del Tour:
    # ≥200 m de desnivel con ≥3% de pendiente media.
    top = summits[0]
    assert top["category"] == "3"
    assert top["climb_gain_m"] >= 200
    assert top["avg_grade_pct"] >= 3
    # Y todas están dentro del recorrido.
    assert all(0 < s["distance_km"] < 47.23 for s in summits)


def test_summits_are_sorted_by_difficulty():
    """Las cimas más duras primero: es el orden en que se leen."""
    geojson, *_ = _real_geojson("vuelta-a-los-poblados")
    summits = extract_summits(geojson, geocode=False)
    gains = [s["climb_gain_m"] for s in summits]
    assert gains == sorted(gains, reverse=True)


def test_no_summits_when_route_is_flat():
    """Una ruta llana no inventa cimas."""
    flat = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[-71.0, -16.0, 100.0, 0.0], [-71.1, -16.0, 100.0, 5.0]],
                },
            }
        ],
    }
    assert extract_summits(flat, geocode=False) == []
