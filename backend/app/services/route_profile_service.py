"""
Perfil de ruta: lee la geometría real de una etapa y extrae sus cimas.

La geometría de `Stage.route_geojson` es una LineString de coordenadas
`[lon, lat, ele, km]`. De ahí sale:

  · el desnivel **positivo acumulado** (tramo a tramo, como lo cuenta un GPS:
    un vaivén no es un desnivel);
  · los **tramos de subida** (pendiente ≥ 3%) y de bajada (≤ -3%);
  · la **cima** de cada tramo, con su nombre.

El nombre de la cima se resuelve con el reverse-geocode de OpenStreetMap
(Nominatim) **al sembrar**, no en cada request: la red no debe estar en el
camino de una página. Si el geocodificador no conoce el lugar, la cima se
queda con un nombre derivado de la geometría.

Categoría de puerto, al estilo del Tour (specs/03 §1.2). La regla se aplica
sobre el **desnivel del tramo** y su **pendiente media**, que es lo que hace
el Tour:

  · **HC**  — ≥ 1000 m de desnivel con ≥ 8% de pendiente media.
  · **1**   — ≥ 700 m de desnivel con ≥ 6% de pendiente media.
  · **2**   — ≥ 400 m de desnivel con ≥ 4% de pendiente media.
  · **3**   — ≥ 200 m de desnivel con ≥ 3% de pendiente media.
  · **4**   — el resto de las subidas de más de 100 m de desnivel.
"""
import json
import math
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from backend.app.models.entities import RouteSummit

# Pendiente (en %) a partir de la cual un tramo cuenta como subida.
CLIMB_THRESHOLD_PCT = 3.0
# Pendiente (en %) a partir de la cual un tramo cuenta como bajada.
DESCENT_THRESHOLD_PCT = -3.0
# Desnivel mínimo (m) para que una subida se registre como puerto.
MIN_CLIMB_GAIN_M = 25
# Ventana de suavizado (puntos) para el cálculo de pendientes: la geometría
# viene simplificada a 500 puntos y el ruido de esa simplificación infla las
# pendientes cortas (un tramo de 70 m marcaba 53% de pendiente).
SMOOTHING_WINDOW = 3

_NOMINATIM = "https://nominatim.openstreetmap.org/reverse"
_USER_AGENT = "kuspide-mtb/1.0 (https://kuspide.pe)"

# Categorías de puerto, de la más dura a la más suave:
# (etiqueta, desnivel mínimo en m, pendiente media mínima en %).
_CATEGORY_RULES = [
    ("HC", 1000, 8.0),
    ("1", 700, 6.0),
    ("2", 400, 4.0),
    ("3", 200, 3.0),
    ("4", 100, 2.0),
]


def _coords_from_geojson(route_geojson: Optional[Dict[str, Any]]) -> List[List[float]]:
    """Extrae la lista de coordenadas `[lon, lat, ele, km]` de un geojson."""
    if not route_geojson:
        return []
    features = route_geojson.get("features") or []
    for feature in features:
        geometry = feature.get("geometry") or {}
        if geometry.get("type") == "LineString":
            return list(geometry.get("coordinates") or [])
    return []


def _slope_pct(from_coord: List[float], to_coord: List[float]) -> float:
    """Pendiente en % entre dos coordenadas consecutivas."""
    d_km = to_coord[3] - from_coord[3]
    if d_km <= 0:
        return 0.0
    return (to_coord[2] - from_coord[2]) / (d_km * 1000.0) * 100.0


def _smooth_elevations(coords: List[List[float]], window: int = SMOOTHING_WINDOW) -> List[float]:
    """Media móvil centrada de la altitud.

    La geometría se guarda simplificada a 500 puntos; esa simplificación mete
    ruido en la altitud y hace que un tramo de 70 m parezca un 53% de
    pendiente. Suavizar antes de medir es lo que hace un GPS con filtro.
    """
    if window <= 1 or len(coords) < window:
        return [c[2] for c in coords]
    half = window // 2
    elevations = [c[2] for c in coords]
    smoothed: List[float] = []
    for index in range(len(elevations)):
        low = max(0, index - half)
        high = min(len(elevations), index + half + 1)
        smoothed.append(sum(elevations[low:high]) / (high - low))
    return smoothed


def _classify(distance_km: float, avg_grade_pct: float, gain_m: int) -> str:
    """Categoría de puerto al estilo del Tour."""
    for category, min_gain, min_grade in _CATEGORY_RULES:
        if gain_m >= min_gain and avg_grade_pct >= min_grade:
            return category
    return ""


def _reverse_geocode(lat: float, lon: float) -> Tuple[Optional[str], str]:
    """Nombre del lugar de una coordenada, vía Nominatim (OpenStreetMap).

    Devuelve `(nombre, origen)`. `nombre` es `None` si no se pudo resolver.
    """
    url = (
        f"{_NOMINATIM}?format=jsonv2&zoom=14&lat={lat}&lon={lon}&addressdetails=1"
    )
    try:
        request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None, "geo"

    address = data.get("address") or {}
    name = (
        data.get("name")
        or address.get("road")
        or address.get("neighbourhood")
        or address.get("suburb")
        or address.get("village")
        or address.get("town")
        or address.get("city")
        or address.get("hamlet")
    )
    if not name:
        display = data.get("display_name") or ""
        name = display.split(",")[0].strip() or None
    if not name:
        return None, "geo"
    return name, "osm"


def _fallback_name(coords: List[float], elevation_m: int) -> str:
    """Nombre derivado de la geometría cuando el mapa no conoce el lugar."""
    return f"CIMA {int(elevation_m)} MSNM"


def extract_summits(
    route_geojson: Optional[Dict[str, Any]],
    *,
    geocode: bool = False,
) -> List[Dict[str, Any]]:
    """Extrae las cimas de la ruta desde su geometría.

    `geocode=True` consulta Nominatim para nombrar cada cima. Se usa **solo al
    sembrar**: en cada request la red no debe estar en el camino.
    """
    coords = _coords_from_geojson(route_geojson)
    if len(coords) < 2:
        return []

    elevations = _smooth_elevations(coords)

    # Tramos de subida contiguos.
    climbs: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None

    for index in range(len(coords) - 1):
        d_km = coords[index + 1][3] - coords[index][3]
        if d_km <= 0:
            continue
        grade = (elevations[index + 1] - elevations[index]) / (d_km * 1000.0) * 100.0
        if grade >= CLIMB_THRESHOLD_PCT:
            if current is None:
                current = {
                    "from_km": coords[index][3],
                    "to_km": coords[index + 1][3],
                    "gain_m": 0.0,
                    "distance_km": 0.0,
                    "grade_sum": 0.0,
                    "segments": 0,
                    "max_grade_pct": 0.0,
                    "summit_ele": elevations[index],
                    "summit_km": coords[index][3],
                    "summit_lat": coords[index][1],
                    "summit_lon": coords[index][0],
                }
            current["to_km"] = coords[index + 1][3]
            current["gain_m"] += max(0.0, elevations[index + 1] - elevations[index])
            current["distance_km"] += d_km
            current["grade_sum"] += grade
            current["segments"] += 1
            current["max_grade_pct"] = max(current["max_grade_pct"], grade)
            if elevations[index + 1] > current["summit_ele"]:
                current["summit_ele"] = elevations[index + 1]
                current["summit_km"] = coords[index + 1][3]
                current["summit_lat"] = coords[index + 1][1]
                current["summit_lon"] = coords[index + 1][0]
        else:
            if current is not None:
                climbs.append(current)
            current = None

    if current is not None:
        climbs.append(current)

    summits: List[Dict[str, Any]] = []
    for climb in climbs:
        gain = int(round(climb["gain_m"]))
        if gain < MIN_CLIMB_GAIN_M:
            continue
        avg_grade = climb["grade_sum"] / max(1, climb["segments"])
        name: Optional[str] = None
        source = "geo"
        if geocode:
            name, source = _reverse_geocode(climb["summit_lat"], climb["summit_lon"])
        if not name:
            name = _fallback_name(coords, climb["summit_ele"])
            source = "geo"
        summits.append(
            {
                "name": name,
                "name_source": source,
                "category": _classify(climb["distance_km"], avg_grade, gain),
                "distance_km": round(climb["summit_km"], 3),
                "elevation_m": int(round(climb["summit_ele"])),
                "climb_gain_m": gain,
                "avg_grade_pct": round(avg_grade, 2),
                "max_grade_pct": round(climb["max_grade_pct"], 2),
                "lat": climb["summit_lat"],
                "lon": climb["summit_lon"],
            }
        )

    # Las cimas más duro primero: es el orden en que se leen en un perfil.
    summits.sort(key=lambda s: -s["climb_gain_m"])
    return summits


def build_route_profile(
    route_geojson: Optional[Dict[str, Any]],
    *,
    stage_laps: int = 1,
) -> Optional[Dict[str, Any]]:
    """Perfil de altimetría de la ruta, derivado de su geometría real.

    Devuelve `None` si la etapa no tiene geometría: la ficha lo dice en vez
    de dibujar un perfil vacío.
    """
    coords = _coords_from_geojson(route_geojson)
    if len(coords) < 2:
        return None

    elevations = [c[2] for c in coords]
    kilometres = [c[3] for c in coords]
    elevation_min = min(elevations)
    elevation_max = max(elevations)

    gain = 0.0
    loss = 0.0
    max_grade = 0.0
    max_grade_at_km = 0.0
    for index in range(len(coords) - 1):
        delta = coords[index + 1][2] - coords[index][2]
        if delta > 0:
            gain += delta
        else:
            loss -= delta
        grade = _slope_pct(coords[index], coords[index + 1])
        if grade > max_grade:
            max_grade = grade
            max_grade_at_km = coords[index + 1][3]

    distance_km = kilometres[-1] - kilometres[0]
    mean_grade = (gain / (distance_km * 1000.0) * 100.0) if distance_km > 0 else 0.0
    stage_distance = distance_km * max(1, stage_laps)

    return {
        "distance_km": round(distance_km, 2),
        "distance_km_stage": round(stage_distance, 2),
        "elevation_min_m": int(round(elevation_min)),
        "elevation_max_m": int(round(elevation_max)),
        "elevation_gain_m": int(round(gain)),
        "elevation_loss_m": int(round(loss)),
        "mean_grade_pct": round(mean_grade, 2),
        "max_grade_pct": round(max_grade, 2),
        "max_grade_at_km": round(max_grade_at_km, 2),
        "geometry_covers_full_stage": distance_km >= stage_distance * 0.95,
        "points": [
            {"km": round(c[3], 3), "ele": round(c[2], 1), "lat": c[1], "lon": c[0]}
            for c in coords
        ],
    }


def summarize_summits(summits: List[RouteSummit]) -> List[Dict[str, Any]]:
    """Convierte las cimas de la BD en la forma que consume la página."""
    return [
        {
            "name": s.name,
            "category": s.category or "",
            "distance_km": s.distance_km,
            "elevation_m": s.elevation_m,
            "climb_gain_m": s.climb_gain_m,
            "avg_grade_pct": s.avg_grade_pct,
            "max_grade_pct": s.max_grade_pct,
            "lat": s.lat,
            "lon": s.lon,
            "name_source": s.name_source,
        }
        for s in summits
    ]


__all__ = [
    "CLIMB_THRESHOLD_PCT",
    "DESCENT_THRESHOLD_PCT",
    "MIN_CLIMB_GAIN_M",
    "build_route_profile",
    "extract_summits",
    "summarize_summits",
]
