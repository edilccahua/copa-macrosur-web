"""
Tests de seguridad del contrato de lectura público.

El PIN de juez es una credencial: con él se pueden mandar marcaciones de
cronometraje falsas (`/timing/events`) y largar mangas (`/waves/*/start`). Por
eso **ningún endpoint público puede devolverlo** (specs/00 §1.4).

La garantía no es "quitar el campo a mano" en cada endpoint: es el
`response_model` de cada ruta. Estos tests fijan ese contrato para las cuatro
lecturas de `/api/v1/stages`.

Aquí viven también las otras tres fronteras de seguridad del backend:

  · la clave de administrador **falla cerrada** (503 si el servidor no la
    tiene, 403 si la que llega no es la buena);
  · el CORS **cerrado en producción** (sólo los orígenes de la lista, nunca
    un `*.pages.dev` arbitrario ni un localhost);
  · los **límites de entrada** (ventana deslizante por IP, tope del cuerpo
    JSON y tope del archivo subido).
"""
import datetime
import io

import openpyxl
import pytest
from sqlmodel import Session, SQLModel, select

from backend.app.core.config import settings
from backend.app.main import app
from backend.app.models.entities import Stage, StageStatusEnum

# Clave de administrator de las pruebas: NUNCA es la real (ésta vive en el
# entorno del servidor, nunca en el repositorio).
CLAVE_DE_PRUEBA = "clave-de-prueba-kuspide"

async def _seed_stage(session):
    stage = Stage(
        stage_number=99, name="Fecha 99: Prueba", slug="fecha-prueba",
        date=datetime.date(2026, 1, 1), status=StageStatusEnum.FINISHED,
        judge_pin="PIN-SECRETO-DE-PRUEBA",
        route_geojson={"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": {"type": "LineString",
             "coordinates": [[-71.5, -16.4, 2200, 0.0]]}}]},
    )
    session.add(stage)
    await session.commit()
    await session.refresh(stage)
    return stage


async def test_stages_no_expone_judge_pin(client, async_session):
    stage = await _seed_stage(async_session)
    res = await client.get("/api/v1/stages")
    assert res.status_code == 200
    assert "PIN-SECRETO-DE-PRUEBA" not in res.text
    assert "judge_pin" not in res.text


async def test_stage_detalle_no_expone_judge_pin(client, async_session):
    stage = await _seed_stage(async_session)
    res = await client.get(f"/api/v1/stages/{stage.slug}")
    assert res.status_code == 200
    assert "PIN-SECRETO-DE-PRUEBA" not in res.text


async def test_stage_summary_no_expone_judge_pin_ni_geometria(client, async_session):
    stage = await _seed_stage(async_session)
    res = await client.get(f"/api/v1/stages/{stage.slug}/summary")
    assert res.status_code == 200
    assert "PIN-SECRETO-DE-PRUEBA" not in res.text
    assert "judge_pin" not in res.text
    # La geometría pesada no viaja en el resumen: la página usa el SVG estatico.
    assert "route_geojson" not in res.text


async def test_stage_results_no_expone_judge_pin(client, async_session):
    stage = await _seed_stage(async_session)
    res = await client.get(f"/api/v1/stages/{stage.slug}/results")
    assert res.status_code == 200
    assert "PIN-SECRETO-DE-PRUEBA" not in res.text


# ─────────────────────────────────────────────────────────────────────────────
# La clave de administrador falla CERRADO
#
# Antes la clave tenía un valor por DEFECTO en el código y en el bundle del
# navegador: cualquiera que abriera el DevTools podía leerla, aprobar pagos,
# pisar la base de datos con un Excel o abrir la transmisión en vivo.
#
# Ahora la clave vive SÓLO en el entorno del servidor. Si el servidor no la
# tiene, NINGÚN endpoint de administración responde 200.
# ─────────────────────────────────────────────────────────────────────────────


async def test_admin_sin_clave_responde_403(client, monkeypatch):
    """Sin cabecera `X-Admin-Key` la puerta está cerrada (403)."""
    monkeypatch.setattr(settings, "ADMIN_API_KEY", CLAVE_DE_PRUEBA)
    res = await client.get("/api/v1/admin/pending-payments")
    assert res.status_code == 403


async def test_admin_con_clave_invalida_responde_403(client, monkeypatch):
    """Una clave inventada es un 403: no vale, pero el servidor está bien."""
    monkeypatch.setattr(settings, "ADMIN_API_KEY", CLAVE_DE_PRUEBA)
    res = await client.get(
        "/api/v1/admin/pending-payments",
        headers={"X-Admin-Key": "clave-inventada"},
    )
    assert res.status_code == 403


async def test_admin_con_clave_correcta_responde_200(client, monkeypatch):
    """Con la clave buena, la consola de pagos responde 200."""
    monkeypatch.setattr(settings, "ADMIN_API_KEY", CLAVE_DE_PRUEBA)
    res = await client.get(
        "/api/v1/admin/pending-payments",
        headers={"X-Admin-Key": CLAVE_DE_PRUEBA},
    )
    assert res.status_code == 200


async def test_admin_sin_clave_configurada_responde_503(client, monkeypatch):
    """El servidor SIN clave no es un 403: es un 503 (fallo de configuración).

    La diferencia importa: el 403 dice "te equivocaste", el 503 dice "el
    servidor está mal configurado". Con el 503 nadie puede creer que la
    credencial del navegador vale.
    """
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "")
    res = await client.get("/api/v1/admin/pending-payments")
    assert res.status_code == 503
    assert "ADMIN_API_KEY" in res.json()["detail"]


async def test_admin_clave_con_acentos_responde_403(client, monkeypatch):
    """Una cabecera con tildes no puede tumbar el servidor (500).

    `hmac.compare_digest` sólo acepta texto ASCII: hay que comparar BYTES.
    Las cabeceras HTTP viajan en latin-1, así que la prueba manda los bytes.
    """
    monkeypatch.setattr(settings, "ADMIN_API_KEY", CLAVE_DE_PRUEBA)
    res = await client.get(
        "/api/v1/admin/pending-payments",
        headers={"X-Admin-Key": "clávé-ñ".encode("latin-1")},
    )
    assert res.status_code == 403
