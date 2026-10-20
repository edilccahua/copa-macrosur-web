"""Ventana de transmisión en vivo (specs/02 §6).

La apertura es automática a las 08:00 de Lima; el cierre es manual. Estos
tests fijan las fronteras y la autenticación del panel del organizador.
"""
from datetime import date, datetime

import pytest

import backend.app.services.live_service as live_service
from backend.app.core.cache import cache
from backend.app.core.config import settings
from backend.app.models.entities import Stage
from backend.app.services.live_service import (
    LIMA_TZ,
    STATE_BEFORE_START,
    STATE_CLOSED,
    STATE_LIVE,
    STATE_NO_RACE,
    compute_state,
    parse_start_time,
    resolve_live_status,
)

RACE_DAY = date(2026, 10, 25)


def stage(date_value: date = RACE_DAY, start_time: str = "08:00 AM") -> Stage:
    return Stage(
        stage_number=1,
        name="Fecha de prueba",
        slug="fecha-de-prueba",
        date=date_value,
        start_time=start_time,
    )


def at(hour: int, minute: int = 0) -> datetime:
    return datetime(RACE_DAY.year, RACE_DAY.month, RACE_DAY.day, hour, minute, tzinfo=LIMA_TZ)


def test_parse_start_time_meridiem():
    assert parse_start_time("08:00 AM").hour == 8
    assert parse_start_time("02:30 PM").hour == 14
    assert parse_start_time("14:30").hour == 14
    assert parse_start_time(None).hour == 8
    assert parse_start_time("cualquier cosa").hour == 8


def test_before_start_and_live_boundary():
    assert compute_state(stage(), at(7, 59)) == STATE_BEFORE_START
    assert compute_state(stage(), at(8, 0)) == STATE_LIVE
    assert compute_state(stage(), at(9, 30)) == STATE_LIVE


def test_manual_close_wins_over_clock():
    s = stage()
    s.live_closed_at = datetime(2026, 10, 25, 12, 0)
    assert compute_state(s, at(9, 0)) == STATE_CLOSED


def test_no_race_today():
    assert compute_state(stage(), at(9, 0).replace(day=24)) == STATE_NO_RACE


@pytest.mark.asyncio
async def test_resolve_offers_next_stage_when_today_has_no_race(async_session):
    async_session.add(stage())
    await async_session.commit()

    data = await resolve_live_status(
        async_session,
        now=datetime(2026, 10, 20, 9, 0, tzinfo=LIMA_TZ),
    )

    assert data["active"] is False
    assert data["state"] == STATE_NO_RACE
    assert data["stage"]["slug"] == "fecha-de-prueba"
    assert data["opens_at"].startswith("2026-10-25T08:00:00")


@pytest.mark.asyncio
async def test_live_status_endpoint_reads_lima_clock(client, async_session, monkeypatch):
    async_session.add(stage())
    await async_session.commit()

    monkeypatch.setattr(live_service, "now_lima", lambda: at(7, 59))
    res = await client.get("/api/v1/public/live-status")
    assert res.status_code == 200
    assert res.json()["state"] == STATE_BEFORE_START

    monkeypatch.setattr(live_service, "now_lima", lambda: at(8, 0))
    # La caché en memoria está ENCENDIDA también en los tests (para poder
    # probar su invalidación). Este test simula el paso del reloj, así que
    # hay que vaciar la caché entre las dos consultas: si no, la segunda
    # leería el estado cacheado de la primera.
    cache.clear()
    res = await client.get("/api/v1/public/live-status")
    assert res.status_code == 200
    body = res.json()
    assert body["active"] is True
    assert body["state"] == STATE_LIVE


@pytest.mark.asyncio
async def test_admin_closes_and_reopens_the_stream(client, async_session, monkeypatch):
    s = stage()
    async_session.add(s)
    await async_session.commit()
    await async_session.refresh(s)

    url = f"/api/v1/stages/{s.id}/live"

    # Sin X-Admin-Key no se puede cerrar.
    res = await client.post(url, json={"active": False})
    assert res.status_code == 403

    monkeypatch.setattr(live_service, "now_lima", lambda: at(9, 0))

    res = await client.post(
        url,
        json={"active": False},
        headers={"X-Admin-Key": settings.ADMIN_API_KEY},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["state"] == STATE_CLOSED
    assert body["closed_at"] is not None

    await session_refresh(async_session, s)
    assert s.live_closed_at is not None

    res = await client.post(
        url,
        json={"active": True},
        headers={"X-Admin-Key": settings.ADMIN_API_KEY},
    )
    assert res.status_code == 200
    assert res.json()["state"] == STATE_LIVE

    await session_refresh(async_session, s)
    assert s.live_closed_at is None


async def session_refresh(session, obj):
    """Vuelve a leer una fila que el endpoint pudo haber modificado."""
    await session.refresh(obj)


@pytest.mark.asyncio
async def test_admin_live_unknown_stage_is_404(client):
    res = await client.post(
        "/api/v1/stages/9999/live",
        json={"active": False},
        headers={"X-Admin-Key": settings.ADMIN_API_KEY},
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_admin_cannot_close_a_future_stage(client, async_session, monkeypatch):
    """Cerrar hoy una fecha futura la dejaría apagada el día de la carrera."""
    s = stage()
    async_session.add(s)
    await async_session.commit()
    await async_session.refresh(s)

    monkeypatch.setattr(
        live_service,
        "now_lima",
        lambda: datetime(2026, 10, 20, 9, 0, tzinfo=LIMA_TZ),
    )

    res = await client.post(
        f"/api/v1/stages/{s.id}/live",
        json={"active": False},
        headers={"X-Admin-Key": settings.ADMIN_API_KEY},
    )
    assert res.status_code == 400
    assert "día de la carrera" in res.json()["detail"]
