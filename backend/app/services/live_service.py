"""Estado de la ventana de transmisión en vivo.

Una sola fuente de verdad para la portada, `/en-vivo` y el panel del
organizador:

  · `live`           — hoy hay carrera, ya pasaron las 08:00 y el admin no
                       cerró la transmisión.
  · `before_start`   — hoy hay carrera, pero aún no son las 08:00.
  · `closed`         — hoy hay carrera y el admin cerró la transmisión.
  · `no_race_today`  — hoy no hay carrera; se ofrece la próxima fecha.

La hora se calcula SIEMPRE en `America/Lima` (UTC-5, sin horario de verano),
nunca con la hora del servidor: el servidor puede estar en UTC y a las 08:00
de Lima todavía sería de madrugada.
"""
from datetime import datetime, time, timezone
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from backend.app.models.entities import Stage

LIMA_TZ = ZoneInfo("America/Lima")
DEFAULT_START = time(8, 0)

STATE_LIVE = "live"
STATE_BEFORE_START = "before_start"
STATE_CLOSED = "closed"
STATE_NO_RACE = "no_race_today"


def now_lima() -> datetime:
    """Ahora, en la zona horaria de la carrera."""
    return datetime.now(LIMA_TZ)


def utc_now() -> datetime:
    """Marca de cierre en UTC.

    SQLModel exige `datetime` con zona horaria (o `NaiveDatetime` explícito),
    así que se guarda aware y se serializa tal cual.
    """
    return datetime.now(timezone.utc)


def parse_start_time(raw: Optional[str]) -> time:
    """`"08:00 AM"` / `"02:30 PM"` / `"14:30"` → `time`.

    Cualquier valor raro cae en las 08:00, que es la hora oficial de la
    edición (specs/03 §1.7.1).
    """
    if not raw:
        return DEFAULT_START
    text = raw.strip().upper()
    for fmt in ("%I:%M %p", "%I:%M%p", "%H:%M"):
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    return DEFAULT_START


def opens_at(stage: Stage) -> datetime:
    """Instante de apertura de la transmisión, en hora de Lima."""
    return datetime.combine(
        stage.date, parse_start_time(stage.start_time), tzinfo=LIMA_TZ
    )


def compute_state(stage: Stage, now: datetime) -> str:
    """Estado de una etapa concreta en el instante `now`."""
    if stage.date != now.date():
        return STATE_NO_RACE
    if stage.live_closed_at is not None:
        return STATE_CLOSED
    if now < opens_at(stage):
        return STATE_BEFORE_START
    return STATE_LIVE


def _iso_utc(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def stage_brief(stage: Optional[Stage]) -> Optional[Dict[str, Any]]:
    if stage is None:
        return None
    status = stage.status.value if hasattr(stage.status, "value") else str(stage.status)
    return {
        "id": stage.id,
        "stage_number": stage.stage_number,
        "name": stage.name,
        "short_name": stage.short_name,
        "slug": stage.slug,
        "date": stage.date.isoformat(),
        "status": status,
        "start_time": stage.start_time,
        "poster_url": stage.poster_url,
    }


async def resolve_live_status(
    session: AsyncSession, now: Optional[datetime] = None
) -> Dict[str, Any]:
    """Estado completo que consumen la portada, `/en-vivo` y el admin."""
    now = now or now_lima()
    stages = (
        await session.exec(select(Stage).order_by(Stage.stage_number))
    ).all()

    today_stage = next((s for s in stages if s.date == now.date()), None)
    next_stage = next((s for s in stages if s.date > now.date()), None)

    if today_stage is not None:
        state = compute_state(today_stage, now)
        featured = today_stage
    else:
        state = STATE_NO_RACE
        featured = next_stage

    return {
        "active": state == STATE_LIVE,
        "state": state,
        "stage": stage_brief(featured),
        "next_stage": stage_brief(next_stage),
        "opens_at": opens_at(featured).isoformat() if featured is not None else None,
        "closed_at": _iso_utc(featured.live_closed_at) if featured is not None else None,
    }
