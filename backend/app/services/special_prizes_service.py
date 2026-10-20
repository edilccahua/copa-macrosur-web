"""Premios especiales que dependen de los resultados del campeonato.

Hoy: el **Premio CLARO a la remontada** (USD 100).

Regla:
  · Solo compiten los corredores que terminaron **todas las fechas disputadas**
    (cuando el campeonato cierre, serán las cuatro).
  · Se compara el puesto dentro de su categoría en la PRIMERA fecha disputada
    con el de la ÚLTIMA fecha disputada.
  · Gana la mayor subida de puestos (`primero_rank - ultimo_rank`).
  · Desempate: mejor puesto en la última fecha; luego mejor puesto en la
    primera; luego nombre.
  · Mientras no se hayan disputado las cuatro fechas, el ganador es
    **provisional**.
"""
import re
from typing import Any, Dict, List, Optional

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from backend.app.models.entities import (
    Category,
    RaceStatusEnum,
    Rider,
    Stage,
    StageEntry,
    StageStatusEnum,
    Team,
)

CLARO_AMOUNT_USD = 100
TOTAL_STAGES = 4
CLARO_TITLE = "Premio CLARO"
CLARO_SPONSOR = "Claro Perú"
CLARO_LOGO = "/images/sponsors/claro.svg"
CLARO_CRITERION = (
    "Al corredor que más puestos sube en su categoría entre la primera y la "
    "última fecha, habiendo terminado todas."
)


def clean_display_name(name: str) -> str:
    """Quita el guion/punto final que deja el PDF en algunos nombres."""
    return re.sub(r"[\s\-.;]+$", "", (name or "").strip())


async def compute_claro_remontada(session: AsyncSession) -> Dict[str, Any]:
    stages = (
        await session.exec(select(Stage).order_by(Stage.stage_number))
    ).all()
    disputed = [s for s in stages if s.status == StageStatusEnum.FINISHED]

    base: Dict[str, Any] = {
        "title": CLARO_TITLE,
        "sponsor_name": CLARO_SPONSOR,
        "sponsor_logo_url": CLARO_LOGO,
        "amount_usd": CLARO_AMOUNT_USD,
        "criterion": CLARO_CRITERION,
        "stages_counted": len(disputed),
        "total_stages": TOTAL_STAGES,
        "provisional": len(disputed) < TOTAL_STAGES,
        "winner": None,
    }

    # Hacen falta al menos dos fechas para que exista una remontada.
    if len(disputed) < 2:
        return base

    stage_ids = [s.id for s in disputed]
    entries = (
        await session.exec(
            select(StageEntry).where(
                StageEntry.stage_id.in_(stage_ids),
                StageEntry.race_status == RaceStatusEnum.FINISHED,
            )
        )
    ).all()

    by_rider: Dict[int, Dict[int, StageEntry]] = {}
    for entry in entries:
        if entry.category_rank is None:
            continue
        by_rider.setdefault(entry.rider_id, {})[entry.stage_id] = entry

    first_stage = disputed[0]
    last_stage = disputed[-1]

    candidates: List[Dict[str, Any]] = []
    for rider_id, per_stage in by_rider.items():
        # Participó (terminó) en TODAS las fechas disputadas.
        if any(stage_id not in per_stage for stage_id in stage_ids):
            continue

        first = per_stage[first_stage.id]
        last = per_stage[last_stage.id]
        gain = int(first.category_rank) - int(last.category_rank)
        if gain <= 0:
            continue

        candidates.append(
            {
                "rider_id": rider_id,
                "first_rank": int(first.category_rank),
                "last_rank": int(last.category_rank),
                "positions_gained": gain,
                "category_id": last.category_id,
                "team_id": last.team_id,
            }
        )

    if not candidates:
        return base

    candidates.sort(
        key=lambda c: (
            -c["positions_gained"],
            c["last_rank"],
            c["first_rank"],
        )
    )
    best = candidates[0]

    rider = (
        await session.exec(select(Rider).where(Rider.id == best["rider_id"]))
    ).first()
    category = (
        await session.exec(select(Category).where(Category.id == best["category_id"]))
    ).first()
    team = (
        await session.exec(select(Team).where(Team.id == best["team_id"]))
    ).first() if best["team_id"] else None

    base["winner"] = {
        "rider_id": best["rider_id"],
        "rider_name": clean_display_name(rider.full_name) if rider else "",
        "rider_slug": rider.slug if rider else "",
        "team_name": team.name if team else "LIBRE",
        "team_slug": team.slug if team else None,
        "category_name": category.name if category else "",
        "category_short_code": category.short_code if category else "",
        "first_stage_number": first_stage.stage_number,
        "first_stage_name": first_stage.name,
        "first_rank": best["first_rank"],
        "last_stage_number": last_stage.stage_number,
        "last_stage_name": last_stage.name,
        "last_rank": best["last_rank"],
        "positions_gained": best["positions_gained"],
    }
    return base
