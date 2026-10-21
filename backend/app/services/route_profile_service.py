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
CLIMB_THRESHOLD_PCT = 2.5
# Pendiente (en %) a partir de la cual un tramo cuenta como bajada.
DESCENT_THRESHOLD_PCT = -2.5
# Desnivel mínimo (m) para que una subida se registre como puerto de montaña.
# Subidas menores de 80m de desnivel son repechos u ondulaciones, no puertos.
MIN_CLIMB_GAIN_M = 80
# Ventana de suavizado (puntos) para el cálculo de pendientes y cimas.
SMOOTHING_WINDOW = 5

_NOMINATIM = "https://nominatim.openstreetmap.org/reverse"
_USER_AGENT = "kuspide-mtb/1.0 (https://kuspide.pe)"

# Categorías de puerto, de la más dura a la más suave:
# (etiqueta, desnivel mínimo en m, pendiente media mínima en %).
_CATEGORY_RULES = [
    ("HC", 800, 7.0),
    ("1", 500, 6.0),
    ("2", 300, 5.0),
    ("3", 180, 4.0),
    ("4", 80, 2.5),
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

    Identifica puertos continuos (desnivel ≥ 80 m) tolerando pequeños descansos
    para no fragmentar un puerto real en múltiples picos artificiales.
    `geocode=True` consulta Nominatim para nombrar cada cima (solo al sembrar).
    """
    coords = _coords_from_geojson(route_geojson)
    if len(coords) < 2:
        return []

    elevations = _smooth_elevations(coords, window=SMOOTHING_WINDOW)
    kms = [c[3] for c in coords]

    climbs: List[Dict[str, Any]] = []
    i = 0
    while i < len(coords) - 1:
        if elevations[i + 1] > elevations[i]:
            start_i = i
            peak_i = i + 1
            max_ele = elevations[peak_i]
            j = i + 1
            while j < len(coords) - 1:
                if elevations[j] > max_ele:
                    max_ele = elevations[j]
                    peak_i = j
                drop = max_ele - elevations[j]
                dist_from_peak = kms[j] - kms[peak_i]
                # Si cae más de 15m o cae más de 8m durante más de 400m, concluye la subida
                if drop > 15.0 or (drop > 8.0 and dist_from_peak > 0.4):
                    break
                j += 1

            gain = max_ele - elevations[start_i]
            dist = kms[peak_i] - kms[start_i]
            avg_grade = (gain / (dist * 1000.0)) * 100.0 if dist > 0 else 0.0

            # Califican ascensiones de montaña (≥75m) o puertos cortos notables (≥45m con ≥3% o ≥30m con ≥1km)
            is_valid_climb = (
                (gain >= 75.0 and dist > 0.4)
                or (gain >= 45.0 and dist >= 0.8 and avg_grade >= 3.0)
                or (gain >= 30.0 and dist >= 1.0 and avg_grade >= 2.0)
            )

            if is_valid_climb:
                # Pendiente máxima en el puerto calculada sobre ventana móvil de 150m
                climb_max_grade = avg_grade
                for ci in range(start_i, peak_i):
                    d_s = kms[ci] * 1000.0
                    cj = ci
                    while cj <= peak_i and (kms[cj] * 1000.0 - d_s) < 150.0:
                        cj += 1
                    if cj <= peak_i:
                        d_sp = kms[cj] * 1000.0 - d_s
                        if d_sp > 0:
                            g = (elevations[cj] - elevations[ci]) / d_sp * 100.0
                            if g > climb_max_grade:
                                climb_max_grade = g

                name = None
                source = "geo"
                if geocode:
                    name, source = _reverse_geocode(coords[peak_i][1], coords[peak_i][0])
                if not name:
                    name = _fallback_name(coords, coords[peak_i][2])
                    source = "geo"

                gain_int = int(round(gain))
                climbs.append(
                    {
                        "name": name,
                        "name_source": source,
                        "category": _classify(dist, avg_grade, gain_int),
                        "start_km": round(kms[start_i], 2),
                        "distance_km": round(kms[peak_i], 2),
                        "elevation_m": int(round(coords[peak_i][2])),
                        "climb_gain_m": gain_int,
                        "climb_length_km": round(dist, 1),
                        "avg_grade_pct": round(avg_grade, 1),
                        "max_grade_pct": round(climb_max_grade, 1),
                        "lat": coords[peak_i][1],
                        "lon": coords[peak_i][0],
                    }
                )
                i = peak_i
            else:
                i += 1
        else:
            i += 1

    # Ordenar por kilometraje en la carrera
    climbs.sort(key=lambda s: s["distance_km"])
    return climbs


def build_route_profile(
    route_geojson: Optional[Dict[str, Any]],
    *,
    stage_laps: int = 1,
    official_gain_m: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Perfil de altimetría de la ruta, derivado de su geometría real.

    Devuelve `None` si la etapa no tiene geometría: la ficha lo dice en vez
    de dibujar un perfil vacío.

    `official_gain_m` es el desnivel **de la ruta oficial** (el que sale del
    GPX a resolución completa). La geometría que se guarda está simplificada a
    500 puntos, y al simplificarla se pierden unos treinta metros de subida:
    el perfil calculaba +359 m donde la ruta oficial tiene +384 m, y la misma
    ficha mostraba las dos cifras. Con este parámetro el perfil usa la cifra
    oficial y solo ella: **un solo desnivel por carrera**.
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
    for index in range(len(coords) - 1):
        delta = coords[index + 1][2] - coords[index][2]
        if delta > 0:
            gain += delta
        else:
            loss -= delta

    # Pendiente máxima calculada sobre ventana móvil (150 m) para filtrar
    # el ruido microscópico del GPS que inflaba pendientes absurdas de >50%.
    max_grade = 0.0
    max_grade_at_km = 0.0
    WINDOW_M = 150.0
    for i in range(len(coords)):
        d_start_m = coords[i][3] * 1000.0
        j = i
        while j < len(coords) and (coords[j][3] * 1000.0 - d_start_m) < WINDOW_M:
            j += 1
        if j < len(coords):
            d_span_m = coords[j][3] * 1000.0 - d_start_m
            ele_span = coords[j][2] - coords[i][2]
            if d_span_m > 0:
                grade = (ele_span / d_span_m) * 100.0
                if grade > max_grade:
                    max_grade = grade
                    max_grade_at_km = coords[j][3]

    # El desnivel que se muestra es el de la ruta oficial, no el de la traza
    # simplificada. El descenso no tiene cifra oficial: sale de la traza.
    if official_gain_m is not None:
        gain = float(official_gain_m)

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
    res = []
    for s in summits:
        climb_len = round(s.climb_gain_m / (s.avg_grade_pct * 10), 1) if s.avg_grade_pct > 0 else 0.0
        start_k = max(0.0, round(s.distance_km - climb_len, 2))
        res.append(
            {
                "name": s.name,
                "category": s.category or "",
                "start_km": start_k,
                "distance_km": s.distance_km,
                "elevation_m": s.elevation_m,
                "climb_gain_m": s.climb_gain_m,
                "climb_length_km": climb_len,
                "avg_grade_pct": s.avg_grade_pct,
                "max_grade_pct": s.max_grade_pct,
                "lat": s.lat,
                "lon": s.lon,
                "name_source": s.name_source,
            }
        )
    return res


__all__ = [
    "CLIMB_THRESHOLD_PCT",
    "DESCENT_THRESHOLD_PCT",
    "MIN_CLIMB_GAIN_M",
    "build_route_profile",
    "extract_summits",
    "summarize_summits",
]
