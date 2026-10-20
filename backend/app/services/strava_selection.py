"""
Reglas de seleccion de los segmentos Strava de una fecha.

Strava lista en la tabla de un segmento los intentos de MUCHAS fechas: los
de la carrera y los de años atrás, mezclados. Y lista tambien el segmento que
cubre la carrera ENTERA, que no es un puerto ni un称号: es la ruta.

Tres reglas, en este orden:

  1. **Filtro por fecha de medición.** Solo cuenta el intento cuya fecha
     coincide con la de la carrera (±1 día, por el desfase de zona horaria).
  2. **Cruce con los pilotos.** Solo cuenta el intento de un corredor que
     estaba inscrito en ESA fecha. Un corredor que hizo el tramo en 2019 no
     compitió en nuestra carrera.
  3. **Selección.** Se descarta el segmento que cubre casi toda la etapa
     (es la ruta, no un tramo) y se eligen los más relevantes: primero los
     de subida y bajada más empinados, luego los más largos.
"""
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Sequence

# Un segmento que cubre este porcentaje de la etapa NO es un tramo: es la ruta.
FULL_ROUTE_RATIO = 0.8
# Cuántos segmentos se muestran como máximo.
MAX_SEGMENTS = 5
# Tolerancia de fecha entre el intento y la carrera (±1 día).
DATE_TOLERANCE_DAYS = 1


def parse_iso(value: Optional[str]) -> Optional[date]:
    """'2026-05-17' → date(2026, 5, 17)."""
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def is_measured_on_stage(measured_on: Optional[str], stage_date: Optional[str]) -> bool:
    """¿El intento se midió el día de la carrera (o el día anterior)?"""
    attempt = parse_iso(measured_on)
    race = parse_iso(stage_date)
    if attempt is None or race is None:
        return False
    return abs((attempt - race).days) <= DATE_TOLERANCE_DAYS


def is_full_route(distance_km: float, stage_distance_km: float) -> bool:
    """¿Este segmento ES la carrera entera?"""
    if stage_distance_km <= 0:
        return False
    return distance_km >= stage_distance_km * FULL_ROUTE_RATIO


def segment_relevance(segment: Dict[str, Any]) -> tuple:
    """Puntuación de relevancia de un segmento, de mayor a menor.

    Se prioriza:
      1. el tipo (subida y bajada antes que llano);
      2. la pendiente (los puertos y las bajadas reales);
      3. la longitud (un tramo de 1 km no es un puerto).
    """
    kind = segment.get("kind") or "FLAT"
    kind_rank = {"CLIMB": 0, "DESCENT": 1, "FLAT": 2}.get(kind, 2)
    grade = abs(float(segment.get("average_grade") or 0))
    distance = float(segment.get("distance_km") or 0)
    # La pendiente manda, pero un tramo de 0.3 km con 8% no es un puerto.
    weight = min(distance, 3.0)
    return (kind_rank, -round(grade * weight, 3), -distance)


def select_segments(
    segments: Sequence[Dict[str, Any]],
    *,
    stage_distance_km: float,
    limit: int = MAX_SEGMENTS,
) -> List[Dict[str, Any]]:
    """Elige los segmentos que se muestran de una fecha.

    Descarta el segmento que cubre la carrera entera y se queda con los
    `limit` más relevantes.
    """
    candidates = [
        segment
        for segment in segments
        if not is_full_route(
            float(segment.get("distance_km") or 0), stage_distance_km
        )
    ]
    candidates.sort(key=segment_relevance)
    return candidates[:limit]


def filter_efforts(
    efforts: Sequence[Dict[str, Any]],
    *,
    stage_date: Optional[str],
    stage_rider_ids: Sequence[int],
) -> List[Dict[str, Any]]:
    """Deja solo los intentos de la carrera, de corredores que compitieron.

    Un intento cuenta si:
      · se midió en la fecha de la carrera (±1 día), y
      · su corredor estaba inscrito en esa fecha.
    """
    riders = set(stage_rider_ids)
    result = []
    for effort in efforts:
        if not is_measured_on_stage(effort.get("measured_on"), stage_date):
            continue
        rider_id = effort.get("rider_id")
        if rider_id is not None and riders and rider_id not in riders:
            continue
        result.append(effort)
    return result


__all__ = [
    "DATE_TOLERANCE_DAYS",
    "FULL_ROUTE_RATIO",
    "MAX_SEGMENTS",
    "filter_efforts",
    "is_full_route",
    "is_measured_on_stage",
    "parse_iso",
    "segment_relevance",
    "select_segments",
]
