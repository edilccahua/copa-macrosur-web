import io
import math
from typing import Dict, Any, List
import gpxpy


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia en kilómetros entre dos coordenadas geográficas."""
    R = 6371.0  # Radio de la Tierra en km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def parse_gpx_in_memory(gpx_bytes: bytes, max_points: int = 500) -> Dict[str, Any]:
    """
    Parsea archivo GPX en memoria.
    Retorna:
    - distance_km: float
    - elevation_gain_m: int
    - route_geojson: GeoJSON FeatureCollection con coordenadas simplificadas y altimetría
    """
    gpx_str = gpx_bytes.decode("utf-8", errors="ignore")
    gpx = gpxpy.parse(gpx_str)

    raw_points = []
    total_dist_km = 0.0
    total_elevation_gain = 0.0
    prev_point = None

    for track in gpx.tracks:
        for segment in track.segments:
            for pt in segment.points:
                ele = pt.elevation or 0.0
                if prev_point:
                    dist_step = haversine_distance(prev_point.latitude, prev_point.longitude, pt.latitude, pt.longitude)
                    total_dist_km += dist_step
                    ele_diff = ele - (prev_point.elevation or 0.0)
                    if ele_diff > 0:
                        total_elevation_gain += ele_diff
                raw_points.append({
                    "lat": pt.latitude,
                    "lon": pt.longitude,
                    "ele": round(ele, 1),
                    "dist_km": round(total_dist_km, 2)
                })
                prev_point = pt

    if not raw_points:
        return {
            "distance_km": 0.0,
            "elevation_gain_m": 0,
            "route_geojson": {"type": "FeatureCollection", "features": []}
        }

    # Simplificación uniforme a max_points puntos
    n_points = len(raw_points)
    if n_points > max_points:
        step = n_points / max_points
        sampled = [raw_points[int(i * step)] for i in range(max_points)]
        # Asegurar que el último punto esté presente
        if sampled[-1] != raw_points[-1]:
            sampled[-1] = raw_points[-1]
    else:
        sampled = raw_points

    # Generar GeoJSON
    # coordinates: [lon, lat, ele, dist_km]
    coordinates = [[p["lon"], p["lat"], p["ele"], p["dist_km"]] for p in sampled]

    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": coordinates
                },
                "properties": {
                    "distance_km": round(total_dist_km, 2),
                    "elevation_gain_m": int(round(total_elevation_gain)),
                    "points_count": len(coordinates)
                }
            }
        ]
    }

    return {
        "distance_km": round(total_dist_km, 2),
        "elevation_gain_m": int(round(total_elevation_gain)),
        "route_geojson": geojson
    }
