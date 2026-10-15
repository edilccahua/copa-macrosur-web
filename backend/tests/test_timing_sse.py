import uuid
import datetime
import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from backend.app.models.entities import Stage, Checkpoint, Category, Rider, StageEntry, RaceStatusEnum


@pytest.mark.asyncio
async def test_timing_sync_and_events(client: AsyncClient, async_session: AsyncSession):
    # 1. Test time-sync
    res = await client.get("/api/v1/timing/time-sync")
    assert res.status_code == 200
    assert "server_time_ms" in res.json()
    assert res.json()["server_time_ms"] > 0

    # 2. Configurar etapa, checkpoints y corredor
    stage = Stage(stage_number=1, name="Fecha 1", slug="f1", date=datetime.date(2026, 3, 15), judge_pin="PIN-123")
    async_session.add(stage)
    await async_session.flush()

    cp_finish = Checkpoint(stage_id=stage.id, name="Meta", order_index=99, is_finish_line=True)
    cat = Category(name="ELITE", short_code="ELI")
    rider = Rider(dni="77777777", full_name="Carlos Timing", slug="carlos-t")
    async_session.add_all([cp_finish, cat, rider])
    await async_session.flush()

    entry = StageEntry(
        stage_id=stage.id,
        rider_id=rider.id,
        category_id=cat.id,
        bib_number=15,
        start_time_ms=1000000,
        race_status=RaceStatusEnum.STARTED
    )
    async_session.add(entry)
    await async_session.commit()

    headers = {"X-Judge-Pin": "PIN-123"}
    event_id = str(uuid.uuid4())

    # 3. Registrar llegada normal
    payload = {
        "id": event_id,
        "stage_entry_id": entry.id,
        "checkpoint_id": cp_finish.id,
        "recorded_at_ms": 4600000,
        "force_update": False
    }
    res_ev = await client.post("/api/v1/timing/events", json=payload, headers=headers)
    assert res_ev.status_code == 200
    assert res_ev.json()["elapsed_ms"] == 3600000

    # 4. Intentar registrar de nuevo el mismo evento (Idempotencia por UUID)
    res_dup = await client.post("/api/v1/timing/events", json=payload, headers=headers)
    assert res_dup.status_code == 200
    assert res_dup.json()["status"] == "ignored"

    # 5. Intentar registrar una NUEVA llegada con distinto UUID sin force_update -> HTTP 409 Conflict
    payload_conflict = {
        "id": str(uuid.uuid4()),
        "stage_entry_id": entry.id,
        "checkpoint_id": cp_finish.id,
        "recorded_at_ms": 4700000,
        "force_update": False
    }
    res_conflict = await client.post("/api/v1/timing/events", json=payload_conflict, headers=headers)
    assert res_conflict.status_code == 409
    assert "ya cruzó meta" in str(res_conflict.json()["detail"])

    # 6. Registrar con force_update=True -> Debe sobrescribir con éxito
    payload_conflict["force_update"] = True
    res_force = await client.post("/api/v1/timing/events", json=payload_conflict, headers=headers)
    assert res_force.status_code == 200
    assert res_force.json()["elapsed_ms"] == 3700000
