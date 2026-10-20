"""
Tests de seguridad del contrato de lectura público.

El PIN de juez es una credencial: con él se pueden mandar marcaciones de
cronometraje falsas (`/timing/events`) y largar mangas (`/waves/*/start`). Por
eso **ningún endpoint público puede devolverlo** (specs/00 §1.4).

La garantía no es "quitar el campo a mano" en cada endpoint: es el
`response_model` de cada ruta. Estos tests fijan ese contrato para las cuatro
lecturas de `/api/v1/stages`.
"""
from sqlmodel import Session, SQLModel, select
from backend.app.main import app
from backend.app.models.entities import Stage, StageStatusEnum
import datetime

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
    assert "judge_pin" not in res.text
