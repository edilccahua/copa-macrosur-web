import pytest
from backend.app.services.gpx_service import parse_gpx_in_memory

SAMPLE_GPX = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="Strava">
  <trk>
    <name>Vuelta a los Poblados Test</name>
    <trkseg>
      <trkpt lat="-16.4090" lon="-71.5375"><ele>2325.0</ele></trkpt>
      <trkpt lat="-16.4150" lon="-71.5420"><ele>2380.0</ele></trkpt>
      <trkpt lat="-16.4210" lon="-71.5490"><ele>2450.0</ele></trkpt>
      <trkpt lat="-16.4300" lon="-71.5580"><ele>2510.0</ele></trkpt>
    </trkseg>
  </trk>
</gpx>
"""


def test_parse_gpx_in_memory():
    gpx_bytes = SAMPLE_GPX.encode("utf-8")
    result = parse_gpx_in_memory(gpx_bytes, max_points=10)

    assert result["distance_km"] > 0
    assert result["elevation_gain_m"] == 185  # (2380-2325) + (2450-2380) + (2510-2450) = 55 + 70 + 60 = 185
    assert "route_geojson" in result
    features = result["route_geojson"]["features"]
    assert len(features) == 1
    coords = features[0]["geometry"]["coordinates"]
    assert len(coords) == 4
    # Coordenadas [lon, lat, ele, dist_km]
    assert coords[0][2] == 2325.0
