import time
import uuid
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select

from backend.app.core.cache import cache
from backend.app.core.db import get_session
from backend.app.core.security import verify_judge_pin_header
from backend.app.core.sse_manager import sse_manager
from backend.app.models.entities import (
    Stage, StartWave, Checkpoint, StageEntry, TimingEvent, RaceStatusEnum,
    Rider, Category, Team,
)
from backend.app.models.schemas import (
    TimeSyncResponse, TimingEventCreate, BatchSyncRequest, BatchSyncResponse, WaveStartRequest
)
from backend.app.services.scoring import (
    recalculate_stage_ranks, recalculate_championship_standings, recalculate_team_standings
)
from backend.app.services.pdf_service import format_ms_to_time

router = APIRouter(prefix="", tags=["Timing & SSE"])


@router.get("/timing/time-sync", response_model=TimeSyncResponse)
async def get_time_sync():
    """Devuelve el timestamp del servidor en milisegundos para calibrar el reloj del juez."""
    return {"server_time_ms": int(time.time() * 1000)}


@router.get("/stages/{stage_id}/judge-auth")
async def judge_auth(
    stage_id: int,
    session: AsyncSession = Depends(get_session),
    judge_pin: str = Depends(verify_judge_pin_header)
):
    """
    Valida el PIN de juez de una fecha SIN registrar ninguna marcación.

    La puerta del panel (`/admin/juez`) la usa para comprobar el PIN antes
    de montar el panel: así el PIN nunca viaja en el código de la página
    (antes venía hardcodeado en `initialJudgePin`, y cualquiera podía
    leerlo en el código fuente y mandar marcaciones).
    """
    stmt_stage = select(Stage).where(Stage.id == stage_id)
    stage = (await session.exec(stmt_stage)).first()
    if not stage:
        raise HTTPException(status_code=404, detail="Etapa no encontrada.")
    if stage.judge_pin != judge_pin:
        raise HTTPException(status_code=403, detail="PIN de juez inválido para esta etapa.")

    # Ojo: el PIN NO se devuelve. Sólo se confirma que es válido.
    return {
        "status": "ok",
        "stage_id": stage.id,
        "stage_number": stage.stage_number,
        "stage_name": stage.name,
        "slug": stage.slug,
    }


@router.post("/stages/{stage_id}/entries/{stage_entry_id}/start")
async def start_entry(
    stage_id: int,
    stage_entry_id: int,
    payload: Optional[WaveStartRequest] = None,
    session: AsyncSession = Depends(get_session),
    judge_pin: str = Depends(verify_judge_pin_header)
):
    """
    Larga individual (contrarreloj o excepción): asigna la hora de partida a
    UN corredor (specs/02 §1.2).
    """
    stmt_stage = select(Stage).where(Stage.id == stage_id)
    stage = (await session.exec(stmt_stage)).first()
    if not stage:
        raise HTTPException(status_code=404, detail="Etapa no encontrada.")
    if stage.judge_pin != judge_pin:
        raise HTTPException(status_code=403, detail="PIN de juez inválido para esta etapa.")

    stmt_entry = select(StageEntry).where(
        StageEntry.id == stage_entry_id, StageEntry.stage_id == stage_id
    )
    entry = (await session.exec(stmt_entry)).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Inscripción del corredor no encontrada.")

    start_ms = payload.started_at_ms if (payload and payload.started_at_ms) else int(time.time() * 1000)
    entry.start_time_ms = start_ms
    entry.race_status = RaceStatusEnum.STARTED
    session.add(entry)
    await session.commit()

    await sse_manager.broadcast(stage_id, "wave-started", {
        "wave_id": None,
        "wave_name": f"Largada individual · dorsal #{entry.bib_number}",
        "started_at_ms": start_ms,
        "category_ids": [entry.category_id]
    })

    # La largada cambia el estado de la carrera: lo que el público tiene
    # cacheado (clasificación, calendario, resumen de la fecha) ya no vale.
    cache.invalidate_public()

    return {
        "status": "success",
        "stage_entry_id": entry.id,
        "bib_number": entry.bib_number,
        "started_at_ms": start_ms
    }


@router.post("/stages/{stage_id}/waves/{wave_id}/start")
async def start_wave(
    stage_id: int,
    wave_id: int,
    payload: Optional[WaveStartRequest] = None,
    session: AsyncSession = Depends(get_session),
    judge_pin: str = Depends(verify_judge_pin_header)
):
    """Larga una manga de categorías simultáneamente."""
    stmt_stage = select(Stage).where(Stage.id == stage_id)
    stage = (await session.exec(stmt_stage)).first()
    if not stage:
        raise HTTPException(status_code=404, detail="Etapa no encontrada.")
    if stage.judge_pin != judge_pin:
        raise HTTPException(status_code=403, detail="PIN de juez inválido para esta etapa.")

    stmt_wave = select(StartWave).where(StartWave.id == wave_id, StartWave.stage_id == stage_id)
    wave = (await session.exec(stmt_wave)).first()
    if not wave:
        raise HTTPException(status_code=404, detail="Manga de largada no encontrada.")

    start_ms = payload.started_at_ms if (payload and payload.started_at_ms) else int(time.time() * 1000)
    wave.started_at_ms = start_ms
    session.add(wave)

    # Actualizar corredores pertenecientes a las categorías de esta manga
    if wave.category_ids:
        stmt_entries = select(StageEntry).where(
            StageEntry.stage_id == stage_id,
            StageEntry.category_id.in_(wave.category_ids)
        )
        entries = (await session.exec(stmt_entries)).all()
        for e in entries:
            e.start_time_ms = start_ms
            e.race_status = RaceStatusEnum.STARTED
            session.add(e)

    await session.commit()

    # Emitir evento SSE
    await sse_manager.broadcast(stage_id, "wave-started", {
        "wave_id": wave_id,
        "wave_name": wave.name,
        "started_at_ms": start_ms,
        "category_ids": wave.category_ids
    })

    # La largada cambia el estado de la carrera: lo que el público tiene
    # cacheado (clasificación, calendario, resumen de la fecha) ya no vale.
    cache.invalidate_public()

    return {"status": "success", "wave_id": wave_id, "started_at_ms": start_ms}


@router.post("/timing/events")
async def record_timing_event(
    event_in: TimingEventCreate,
    session: AsyncSession = Depends(get_session),
    judge_pin: str = Depends(verify_judge_pin_header)
):
    """
    Registra una marcación individual del juez.
    Verifica idempotencia por UUID, sanity check de hora y protección 409 contra re-tap en meta.
    """
    # 1. Verificar idempotencia por UUID
    stmt_existing = select(TimingEvent).where(TimingEvent.id == event_in.id)
    if (await session.exec(stmt_existing)).first():
        return {"status": "ignored", "message": "Evento ya registrado (UUID duplicado)."}

    # 2. Verificar StageEntry y Checkpoint.
    # La inscripción se trae con corredor, categoría y equipo en la MISMA
    # consulta: el aviso por SSE los necesita y recargarlos después (un
    # `refresh` con tres relaciones) costaba cuatro consultas en el camino
    # crítico del juez.
    stmt_entry = (
        select(StageEntry, Rider, Category, Team)
        .outerjoin(Rider, StageEntry.rider_id == Rider.id)
        .outerjoin(Category, StageEntry.category_id == Category.id)
        .outerjoin(Team, StageEntry.team_id == Team.id)
        .where(StageEntry.id == event_in.stage_entry_id)
    )
    fila = (await session.exec(stmt_entry)).first()
    if fila is None:
        raise HTTPException(status_code=404, detail="Inscripción de corredor no encontrada.")
    entry, rider, category, team = fila

    stmt_cp = select(Checkpoint).where(Checkpoint.id == event_in.checkpoint_id)
    checkpoint = (await session.exec(stmt_cp)).first()
    if not checkpoint:
        raise HTTPException(status_code=404, detail="Punto de control no encontrado.")

    if checkpoint.stage_id != entry.stage_id:
        raise HTTPException(status_code=400, detail="El punto de control y la inscripción pertenecen a etapas distintas.")

    stmt_stage = select(Stage).where(Stage.id == entry.stage_id)
    stage = (await session.exec(stmt_stage)).first()
    if not stage or stage.judge_pin != judge_pin:
        raise HTTPException(status_code=403, detail="PIN de juez inválido para esta etapa.")

    # 3. Sanity check: tiempo registrado >= start_time
    if entry.start_time_ms and event_in.recorded_at_ms < entry.start_time_ms:
        raise HTTPException(status_code=422, detail="La marcación no puede ser anterior a la hora de partida.")

    elapsed_ms = (event_in.recorded_at_ms - entry.start_time_ms) if entry.start_time_ms else 0

    # 4. Protección contra re-tap en meta (HTTP 409 Conflict)
    if checkpoint.is_finish_line and entry.finish_elapsed_ms is not None and not event_in.force_update:
        prev_time = format_ms_to_time(entry.finish_elapsed_ms)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": f"El dorsal #{entry.bib_number} ya cruzó meta a las {prev_time}.",
                "existing_elapsed_ms": entry.finish_elapsed_ms,
                "existing_time_str": prev_time,
                "bib_number": entry.bib_number
            }
        )

    # 5. Guardar evento
    timing_event = TimingEvent(
        id=event_in.id,
        stage_entry_id=entry.id,
        checkpoint_id=checkpoint.id,
        recorded_at_ms=event_in.recorded_at_ms,
        elapsed_from_start_ms=elapsed_ms,
        recorded_by_admin=event_in.recorded_by_admin
    )
    session.add(timing_event)

    if checkpoint.is_finish_line:
        entry.finish_elapsed_ms = elapsed_ms
        entry.race_status = RaceStatusEnum.FINISHED
        session.add(entry)

    await session.commit()

    # Recalcular puestos de fecha si cruzó meta
    if checkpoint.is_finish_line:
        await recalculate_stage_ranks(session, entry.stage_id)
        await recalculate_team_standings(session, entry.stage_id)

    # Emitir SSE
    await sse_manager.broadcast(entry.stage_id, "timing-update", {
        "event_type": "finish" if checkpoint.is_finish_line else "split",
        "stage_id": entry.stage_id,
        "bib_number": entry.bib_number,
        "rider_name": rider.full_name if rider else "",
        "team_name": team.name if team else "LIBRE",
        "category_name": category.name if category else "",
        "elapsed_ms": elapsed_ms,
        "formatted_time": format_ms_to_time(elapsed_ms),
        "provisional_category_rank": entry.category_rank,
        "checkpoint_name": checkpoint.name
    })

    # Una marcación (sobre todo si cruzó meta) cambia los puntos y los
    # puestos: la clasificación cacheada del público deja de ser válida.
    cache.invalidate_public()

    return {
        "status": "success",
        "id": str(timing_event.id),
        "elapsed_ms": elapsed_ms,
        "formatted_time": format_ms_to_time(elapsed_ms)
    }


@router.post("/timing/batch-sync", response_model=BatchSyncResponse)
async def batch_sync_events(
    batch_in: BatchSyncRequest,
    session: AsyncSession = Depends(get_session),
    judge_pin: str = Depends(verify_judge_pin_header)
):
    """
    Sincronización masiva de eventos generados offline en IndexedDB.
    Idempotente: ignora eventos ya existentes y reporta conflictos si los hubiera.
    """
    processed = 0
    ignored = 0
    conflicts = []

    for item in batch_in.events:
        stmt_exist = select(TimingEvent).where(TimingEvent.id == item.id)
        if (await session.exec(stmt_exist)).first():
            ignored += 1
            continue

        try:
            await record_timing_event(item, session=session, judge_pin=judge_pin)
            processed += 1
        except HTTPException as he:
            if he.status_code == 409:
                conflicts.append({"id": str(item.id), "detail": he.detail})
            else:
                ignored += 1

    return {
        "processed": processed,
        "ignored_duplicates": ignored,
        "conflicts": conflicts
    }


@router.get("/stages/{stage_id}/stream")
async def sse_stream(stage_id: int):
    """Canal de streaming Server-Sent Events (SSE) desacoplado de la base de datos."""
    return StreamingResponse(
        sse_manager.event_generator(stage_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.get("/stages/{stage_id}/live-summary")
async def get_live_summary(stage_id: int, session: AsyncSession = Depends(get_session)):
    """Snapshot completo del estado de la carrera para clientes web que cargan /en-vivo."""
    stmt_stage = select(Stage).where(Stage.id == stage_id)
    stage = (await session.exec(stmt_stage)).first()
    if not stage:
        raise HTTPException(status_code=404, detail="Etapa no encontrada.")

    # Corredores finalistas: corredor, categoría y equipo salen en la misma
    # consulta (antes cada inscripción recargaba las tres relaciones).
    stmt_finished = (
        select(StageEntry, Rider, Category, Team)
        .outerjoin(Rider, StageEntry.rider_id == Rider.id)
        .outerjoin(Category, StageEntry.category_id == Category.id)
        .outerjoin(Team, StageEntry.team_id == Team.id)
        .where(StageEntry.stage_id == stage_id, StageEntry.race_status == RaceStatusEnum.FINISHED)
        .order_by(StageEntry.category_id, StageEntry.category_rank)
    )
    entries = (await session.exec(stmt_finished)).all()

    leaderboard = []
    for e, rider, category, team in entries:
        leaderboard.append({
            "entry_id": e.id,
            "bib_number": e.bib_number,
            "rider_name": rider.full_name if rider else "",
            "team_name": team.name if team else "LIBRE",
            "category_name": category.name if category else "",
            "elapsed_ms": e.finish_elapsed_ms,
            "formatted_time": format_ms_to_time(e.finish_elapsed_ms or 0),
            "category_rank": e.category_rank,
            "points_earned": e.points_earned
        })

    return {
        "stage_id": stage.id,
        "stage_name": stage.name,
        "status": stage.status,
        "leaderboard": leaderboard
    }
