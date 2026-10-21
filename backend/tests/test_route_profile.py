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
    assert profile["elevation_min_m"] == pytest.approx(1677, abs=5)
    assert profile["elevation_max_m"] == pytest.approx(2287, abs=5)
    # El desnivel acumulado NO es la diferencia entre máximo y mínimo: la ruta
    # tiene más bajada que subida (~924 m perdidos frente a ~316 m ganados).
    assert profile["elevation_gain_m"] == pytest.approx(316, abs=20)
    assert profile["elevation_loss_m"] > profile["elevation_gain_m"]
    assert profile["mean_grade_pct"] == pytest.approx(0.8, abs=0.1)
    # Pendiente máxima calculada sobre ventana realista de 150m (sin artefactos de 53%)
    assert 5.0 <= profile["max_grade_pct"] <= 20.0
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
    geojson, distance_km, gain_m, laps = _real_geojson("z-xtreme-2026")
    summits = extract_summits(geojson, geocode=False)

    assert len(summits) >= 1
    top = summits[0]
    assert top["climb_gain_m"] >= 180
    assert top["elevation_m"] > 2700
    assert 0 < top["distance_km"] <= distance_km
    assert top["category"] == "3"


def test_summits_of_poblados_carry_real_categories():
    """La vuelta a los poblados tiene subidas de categoría: son puertos."""
    geojson, *_ = _real_geojson("vuelta-a-los-poblados")
    summits = extract_summits(geojson, geocode=False)

    assert len(summits) >= 2
    # La mayor subida (Cacayaco) es categoría 3:
    # ≥180 m de desnivel con ≥4% de pendiente media.
    top = max(summits, key=lambda s: s["climb_gain_m"])
    assert top["category"] == "3"
    assert top["climb_gain_m"] >= 200
    assert top["avg_grade_pct"] >= 4
    # Y todas están dentro del recorrido.
    assert all(0 < s["distance_km"] < 47.23 for s in summits)


def test_la_joya_has_real_climbs_and_no_pueblo_libre():
    """La Joya Extreme detecta sus ascensiones reales (Cañón del Perro Rabioso y Quishuarani) sin inventar Pueblo Libre."""
    geojson, *_ = _real_geojson("la-joya-extreme")
    summits = extract_summits(geojson, geocode=False)
    assert len(summits) >= 1
    # La subida corta (~1.1 km al ~5% en el km 5-7)
    first = summits[0]
    assert 5.0 <= first["distance_km"] <= 7.0
    assert first["climb_gain_m"] >= 45
    assert first["avg_grade_pct"] >= 4.0
    # No inventa Pueblo Libre
    assert all("Pueblo Libre" not in s["name"] for s in summits)


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
