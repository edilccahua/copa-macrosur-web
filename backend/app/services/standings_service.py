"""
Motor de clasificación del portal público.

Calcula el ranking acumulado "a la fecha" (patrón Tour de Francia) con las
mismas reglas de desempate del reglamento, pero **pooling por ámbito**:

  - `COMBINADO`: PRO + NORMAL (E-MTB queda fuera: es otra modalidad).
  - `PRO`: ELITE, MASTER A, MASTER B, MASTER C.
  - `NORMAL`: TURISMO OPEN, TURISMO MASTER, MASTER D, OPEN DAMAS, DAMAS MASTER,
    JUVENILES 15-17.
  - `E-MTB`: E-BIKE OPEN.
  - `category_id`: acota a una categoría concreta (su propio ranking).

Fuente de verdad: `StageEntry` (resultados oficiales). No se usan tablas de
cache: la clasificación se deriva siempre de los resultados, de modo que un
corte por fecha es consistente con lo publicado en `/fechas/[slug]/resultados`.

Desempate del ranking por ámbito (specs/01 §3.2 para el ranking por categoría):
  1. Puntos acumulados DESC
  2. Victorias de categoría DESC
  3. Tiempo acumulado ASC
  4. Nombre ASC (desempate estable y determinista)
"""

from typing import Any, Dict, List, Optional

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from backend.app.models.entities import (
    Category, Rider, Stage, StageEntry, Team, RaceStatusEnum,
)
from backend.app.services.pdf_service import format_ms_to_time


# --- Ámbitos -----------------------------------------------------------------

#: Cada ámbito agrupa las categorías de una modalidad. El tiempo acumulado solo
#: es comparable dentro de un ámbito: las distancias y desniveles de PRO, NORMAL
#: y E-MTB no son homologables entre sí.
SCOPE_GROUPS: Dict[str, List[str]] = {
    "PRO": ["ELI", "MSA", "MSB", "MSC"],
    "NORMAL": ["TOV", "TMV", "MSD", "OPD", "DMM", "JUV"],
    "E-MTB": ["EBK"],
}

SCOPE_LABELS: Dict[str, str] = {
    "PRO": "PRO",
    "NORMAL": "NORMAL",
    "E-MTB": "E-MTB",
}

SCOPE_ORDER: List[str] = ["PRO", "NORMAL", "E-MTB"]


def scope_short_codes(scope: str) -> List[str]:
    """Devuelve los short_codes de categoría que integran un ámbito."""
    return list(SCOPE_GROUPS.get(scope, []))


# --- Utilidades --------------------------------------------------------------

def _elapsed_label(ms: Optional[int]) -> str:
    return format_ms_to_time(ms or 0)


def _gap_label(ms: Optional[int]) -> str:
    """
    Diferencia de tiempo acumulado respecto al líder de la clasificación.

    Puede ser **negativa**: el líder por puntos no siempre es el más rápido
    (puede haber corrido más etapas o de categoría más lenta). En ese caso se
    muestra el signo menos, que es información real, no un error.
    """
    if not ms:
        return "—"
    total = abs(ms) // 1000
    sign = "-" if ms < 0 else "+"
    return f"{sign}{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"


async def _category_index(session: AsyncSession) -> Dict[int, Category]:
    cats = (await session.exec(select(Category))).all()
    return {c.id: c for c in cats}


async def _finished_entries(
    session: AsyncSession,
    stage_limit: Optional[int],
    category_ids: Optional[List[int]],
) -> List[Any]:
    stmt = select(StageEntry).where(
        StageEntry.race_status == RaceStatusEnum.FINISHED,
        StageEntry.finish_elapsed_ms.is_not(None),
    )
    if stage_limit is not None:
        stmt = stmt.where(StageEntry.stage_id <= stage_limit)
    if category_ids:
        stmt = stmt.where(StageEntry.category_id.in_(category_ids))
    stmt = stmt.order_by(StageEntry.stage_id)
    return list((await session.exec(stmt)).all())


def _rank_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Ordena y numera las filas según el desempate del ámbito."""
    rows.sort(key=lambda r: (
        -r["total_points"],
        -r["first_places_count"],
        r["total_elapsed_ms"],
        r["rider_name"],
    ))
    for idx, row in enumerate(rows, start=1):
        row["current_rank"] = idx
    if rows:
        leader_ms = rows[0]["total_elapsed_ms"]
        for row in rows:
            row["gap_to_leader_ms"] = row["total_elapsed_ms"] - leader_ms
    return rows


async def _previous_stage_id(session: AsyncSession, stage_limit: int) -> Optional[int]:
    """Id de la fecha disputada inmediatamente anterior a `stage_limit`."""
    stmt = (
        select(Stage.id)
        .where(Stage.id < stage_limit)
        .order_by(Stage.stage_number.desc())
    )
    return (await session.exec(stmt)).first()


# --- Individual --------------------------------------------------------------

async def compute_standings(
    session: AsyncSession,
    stage_limit: Optional[int] = None,
    scope: str = "COMBINED",
    category_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Ranking individual acumulado hasta la fecha `stage_limit` (None = todas).

    `scope` acota las categorías (`COMBINED`, `PRO`, `NORMAL`, `E-MTB`) y
    `category_id`, si se indica, acota a una categoría concreta y anula el ámbito.

    Cada fila incluye: puesto en el ámbito, puesto dentro de su categoría, puntos,
    victorias, tiempo acumulado, diferencia al líder y delta contra la fecha previa.
    """
    cats = await _category_index(session)

    category_ids: Optional[List[int]] = None
    if category_id is not None:
        category_ids = [category_id]
    else:
        codes = scope_short_codes(scope)
        matched = [c.id for c in cats.values() if c.short_code in codes]
        category_ids = matched or None
    entries = await _finished_entries(session, stage_limit, category_ids)
    if not entries:
        return []

    rider_ids = {e.rider_id for e in entries}
    riders = (await session.exec(
        select(Rider).where(Rider.id.in_(rider_ids))
    )).all()
    rider_map = {r.id: r for r in riders}
    team_ids = {r.team_id for r in riders if r.team_id}
    teams = (await session.exec(select(Team).where(Team.id.in_(team_ids)))).all() if team_ids else []
    team_map = {t.id: t for t in teams}

    # Acumulado por corredor
    acc: Dict[int, Dict[str, Any]] = {}
    for e in entries:
        rider = rider_map.get(e.rider_id)
        if rider is None:
            continue
        row = acc.get(rider.id)
        if row is None:
            row = acc[rider.id] = {
                "rider_id": rider.id,
                "rider_name": rider.full_name,
                "rider_slug": rider.slug,
                "team_id": rider.team_id,
                "team_name": team_map[rider.team_id].name if rider.team_id in team_map else "LIBRE",
                "team_slug": team_map[rider.team_id].slug if rider.team_id in team_map else None,
                "category_id": e.category_id,
                "category_name": cats[e.category_id].name if e.category_id in cats else "SIN CATEGORÍA",
                "category_short_code": cats[e.category_id].short_code if e.category_id in cats else "",
                "total_points": 0,
                "first_places_count": 0,
                "total_elapsed_ms": 0,
                "stages_completed": 0,
                "_stage_ids": set(),
            }
        row["total_points"] += e.points_earned or 0
        row["total_elapsed_ms"] += e.finish_elapsed_ms or 0
        row["stages_completed"] += 1
        if e.category_rank == 1:
            row["first_places_count"] += 1
        row["_stage_ids"].add(e.stage_id)

    rows = list(acc.values())

    # Puesto dentro de la propia categoría (se calcula sobre el mismo corte)
    per_cat: Dict[int, List[Dict[str, Any]]] = {}
    for row in rows:
        per_cat.setdefault(row["category_id"], []).append(row)
    for cat_rows in per_cat.values():
        cat_rows.sort(key=lambda r: (
            -r["total_points"],
            -r["first_places_count"],
            r["total_elapsed_ms"],
            r["rider_name"],
        ))
        for idx, row in enumerate(cat_rows, start=1):
            row["category_rank"] = idx

    _rank_rows(rows)

    # Delta contra la fecha anterior
    prev_stage_id = await _previous_stage_id(session, stage_limit) if stage_limit is not None else None
    prev_ranks: Dict[int, int] = {}
    if prev_stage_id is not None:
        prev_rows = await compute_standings(
            session, stage_limit=prev_stage_id, scope=scope, category_id=category_id
        )
        prev_ranks = {r["rider_id"]: r["current_rank"] for r in prev_rows}

    for row in rows:
        prev = prev_ranks.get(row["rider_id"])
        if prev_stage_id is None:
            # Primera fecha: no hay con qué comparar.
            row["previous_rank"] = None
            row["rank_delta"] = 0
            row["is_debut"] = False
        elif prev is None:
            # Debutó en esta fecha.
            row["previous_rank"] = None
            row["rank_delta"] = 0
            row["is_debut"] = True
        else:
            row["previous_rank"] = prev
            row["rank_delta"] = prev - row["current_rank"]
            row["is_debut"] = False

    for row in rows:
        row.pop("_stage_ids", None)
        row["formatted_total_time"] = _elapsed_label(row["total_elapsed_ms"])
        row["formatted_gap"] = _gap_label(row["gap_to_leader_ms"])
    return rows


async def _previous_ranks(
    session: AsyncSession,
    stage_limit: Optional[int],
    scope: str,
    category_id: Optional[int],
) -> Dict[int, int]:
    """Puestos en la clasificación del corte anterior (para la DELTA)."""
    if stage_limit is None:
        return {}
    prev_stage_id = await _previous_stage_id(session, stage_limit)
    if prev_stage_id is None:
        return {}
    prev_rows = await compute_standings(
        session, stage_limit=prev_stage_id, scope=scope, category_id=category_id
    )
    return {r["rider_id"]: r["current_rank"] for r in prev_rows}


# --- Equipos -----------------------------------------------------------------

async def compute_team_standings(
    session: AsyncSession,
    stage_limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Copa de Equipos acumulada hasta la fecha `stage_limit` (None = todas)."""
    entries = await _finished_entries(session, stage_limit, None)
    if not entries:
        return []

    team_ids = {e.team_id for e in entries if e.team_id}
    if not team_ids:
        return []
    teams = (await session.exec(select(Team).where(Team.id.in_(team_ids)))).all()
    team_map = {t.id: t for t in teams}

    acc: Dict[int, Dict[str, Any]] = {}
    for e in entries:
        if not e.team_id:
            continue
        row = acc.get(e.team_id)
        if row is None:
            row = acc[e.team_id] = {
                "team_id": e.team_id,
                "team_name": team_map[e.team_id].name if e.team_id in team_map else "LIBRE",
                "team_slug": team_map[e.team_id].slug if e.team_id in team_map else None,
                "total_points": 0,
                "first_places": 0,
                "second_places": 0,
                "third_places": 0,
                "total_riders": 0,
                "total_elapsed_ms": 0,
                "_riders": set(),
            }
        row["total_points"] += e.points_earned or 0
        row["total_elapsed_ms"] += e.finish_elapsed_ms or 0
        row["_riders"].add(e.rider_id)
        if e.category_rank == 1:
            row["first_places"] += 1
        elif e.category_rank == 2:
            row["second_places"] += 1
        elif e.category_rank == 3:
            row["third_places"] += 1

    rows = list(acc.values())
    for row in rows:
        row["total_riders"] = len(row.pop("_riders"))

    rows.sort(key=lambda r: (
        -r["total_points"],
        -r["first_places"],
        -r["second_places"],
        -r["third_places"],
        -r["total_riders"],
        r["total_elapsed_ms"],
        r["team_name"],
    ))
    for idx, row in enumerate(rows, start=1):
        row["current_rank"] = idx
    if rows:
        leader_ms = rows[0]["total_elapsed_ms"]
        for row in rows:
            row["gap_to_leader_ms"] = row["total_elapsed_ms"] - leader_ms
            row["formatted_total_time"] = _elapsed_label(row["total_elapsed_ms"])
            row["formatted_gap"] = _gap_label(row["gap_to_leader_ms"])
    return rows


# --- Metadatos para la interfaz ---------------------------------------------

async def standings_context(
    session: AsyncSession,
    stage_limit: Optional[int] = None,
) -> Dict[str, Any]:
    """Datos de cabecera: etapas disputadas, fechas disponibles y distancia acumulada."""
    stages = (await session.exec(select(Stage).order_by(Stage.stage_number))).all()
    cats = (await session.exec(select(Category))).all()
    finished = [s for s in stages if s.status == "FINISHED"]

    available = [
        {
            "id": s.id,
            "stage_number": s.stage_number,
            "name": s.name,
            "slug": s.slug,
            "date": s.date.isoformat(),
            "distance_km": s.distance_km,
            "laps": s.laps,
        }
        for s in finished
    ]

    target_id = stage_limit
    if target_id is None and available:
        target_id = available[-1]["id"]

    distance = 0.0
    stages_count = 0
    for s in finished:
        if target_id is not None and s.id > target_id:
            continue
        distance += (s.distance_km or 0.0) * (s.laps or 1)
        stages_count += 1

    return {
        "stages": available,
        "selected_stage_id": target_id,
        "stages_counted": stages_count,
        "total_distance_km": round(distance, 2),
        "groups": {k: list(v) for k, v in SCOPE_GROUPS.items()},
        "scope_labels": dict(SCOPE_LABELS),
        "scope_order": list(SCOPE_ORDER),
        "categories": [
            {"id": c.id, "short_code": c.short_code, "name": c.name}
            for c in sorted(cats, key=lambda c: c.id)
        ],
    }
