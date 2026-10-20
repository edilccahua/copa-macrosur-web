from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select

from backend.app.core.cache import cache
from backend.app.core.config import settings
from backend.app.core.db import get_session
from backend.app.core.limits import detalle_excede_tope
from backend.app.core.security import verify_admin_key
from backend.app.models.entities import (
    Stage, StageEntry, PaymentStatusEnum, FeedbackTicket, TicketStatusEnum,
    StravaSegment, StravaEffort, Rider, Category, Team
)
from backend.app.models.schemas import StravaSyncPayload, LiveToggle
from backend.app.services.gpx_service import parse_gpx_in_memory
from backend.app.services.excel_service import normalize_name
from backend.app.services import live_service
from backend.app.services.storage import upload_file_to_r2

router = APIRouter(prefix="", tags=["Admin"])


@router.post("/stages/{stage_id}/live")
async def set_stage_live(
    stage_id: int,
    payload: LiveToggle,
    session: AsyncSession = Depends(get_session),
    admin_key: str = Depends(verify_admin_key),
):
    """Abre o cierra la transmisión de una etapa (specs/02 §6).

    Abrir (`active: true`) limpia `live_closed_at`; cerrar (`active: false`)
    lo marca con la hora UTC. El estado efectivo lo resuelve `live_service`:
    fuera del día de la carrera la transmisión sigue apagada aunque esté
    "abierta" en la BD.
    """
    stage = (
        await session.exec(select(Stage).where(Stage.id == stage_id))
    ).first()
    if not stage:
        raise HTTPException(status_code=404, detail="Etapa no encontrada.")

    # Cerrar una fecha futura la dejaría apagada el día de la carrera. El
    # cierre solo tiene sentido mientras la carrera de hoy está en curso.
    if not payload.active and stage.date != live_service.now_lima().date():
        raise HTTPException(
            status_code=400,
            detail="Solo se puede cerrar la transmisión el día de la carrera.",
        )

    stage.live_closed_at = None if payload.active else live_service.utc_now()
    session.add(stage)
    await session.commit()
    await session.refresh(stage)

    # El estado de la transmisión lo anuncia la portada: si el público lo
    # leyera de la caché, vería el enlace "en vivo" (o su ausencia) con
    # hasta dos minutos de retraso.
    cache.invalidate_public()

    return await live_service.resolve_live_status(session)


@router.post("/stages/{stage_id}/upload-gpx")
async def upload_gpx_file(
    stage_id: int,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    admin_key: str = Depends(verify_admin_key)
):
    stmt = select(Stage).where(Stage.id == stage_id)
    stage = (await session.exec(stmt)).first()
    if not stage:
        raise HTTPException(status_code=404, detail="Etapa no encontrada.")

    # Tope del archivo: se lee UN byte más que el límite para saber que se
    # pasó sin tragarse la traza entera en memoria.
    limite = settings.MAX_UPLOAD_BYTES
    content = await file.read(limite + 1)
    if len(content) > limite:
        raise HTTPException(status_code=413, detail=detalle_excede_tope(limite))

    # 1. Parsear en memoria
    parsed = parse_gpx_in_memory(content, max_points=500)

    # 2. Subir a R2
    file_key = f"stages/{stage_id}/route.gpx"
    r2_url = await upload_file_to_r2(content, file_key, content_type="application/gpx+xml")

    # 3. Guardar en etapa
    stage.distance_km = parsed["distance_km"]
    stage.elevation_gain_m = parsed["elevation_gain_m"]
    stage.route_geojson = parsed["route_geojson"]
    stage.gpx_file_url = r2_url

    session.add(stage)
    await session.commit()

    # La traza nueva cambia la distancia, el desnivel y el perfil de la
    # fecha: el calendario y el resumen cacheados ya no valen.
    cache.invalidate_public()

    return {
        "status": "success",
        "distance_km": stage.distance_km,
        "elevation_gain_m": stage.elevation_gain_m,
        "gpx_file_url": r2_url
    }


@router.post("/stages/{stage_id}/sync-strava-efforts")
async def sync_strava_efforts(
    stage_id: int,
    payload: StravaSyncPayload,
    session: AsyncSession = Depends(get_session),
    admin_key: str = Depends(verify_admin_key)
):
    """
    Recibe la extracción de segmentos de Strava (KOM/QOM, tiempos y atletas)
    realizada por el script local mediante CDP / browser-use.
    """
    stmt = select(Stage).where(Stage.id == stage_id)
    if not (await session.exec(stmt)).first():
        raise HTTPException(status_code=404, detail="Etapa no encontrada.")

    # Buscar o crear segmento
    stmt_seg = select(StravaSegment).where(
        StravaSegment.stage_id == stage_id,
        StravaSegment.strava_segment_id == payload.strava_segment_id
    )
    segment = (await session.exec(stmt_seg)).first()
    if not segment:
        segment = StravaSegment(
            stage_id=stage_id,
            strava_segment_id=payload.strava_segment_id,
            name=payload.segment_name,
            distance_m=payload.distance_m,
            average_grade=payload.average_grade
        )
        session.add(segment)
        await session.flush()
    else:
        segment.name = payload.segment_name
        segment.distance_m = payload.distance_m
        segment.average_grade = payload.average_grade
        session.add(segment)

    # Limpiar esfuerzos previos del segmento para sobreescribir con los
    # actualizados. El sincronizador de género manda `replace=False` para sumar
    # varias pasadas (todos los tiempos / este año) sin perder las anteriores.
    stmt_prev = select(StravaEffort).where(StravaEffort.segment_id == segment.id)
    existing_efforts = (await session.exec(stmt_prev)).all()
    if payload.replace:
        for eff in existing_efforts:
            await session.delete(eff)
        existing_efforts = []

    # Insertar nuevos esfuerzos
    all_riders = (await session.exec(select(Rider))).all()
    rider_tokens = [(r, normalize_name(r.full_name).split()) for r in all_riders]
    # Cruce por identificador de Strava: es fiable, el nombre no.
    rider_by_strava_id = {
        r.strava_athlete_id: r for r in all_riders if r.strava_athlete_id
    }

    def find_rider(athlete_name: str) -> Optional[Rider]:
        """Cruza el nombre de Strava con un Rider por subconjunto de tokens normalizados."""
        at = [t for t in normalize_name(athlete_name).split() if len(t) > 1]
        if not at:
            return None
        best, best_len = None, -1
        for rider, toks in rider_tokens:
            if all(t in toks for t in at) or all(t in at for t in toks):
                if len(toks) > best_len:
                    best, best_len = rider, len(toks)
        return best

    # Clave natural de un intento: atleta + fecha + tiempo. Sin esto, sumar
    # pasadas duplicaría la misma fila que ya está en la BD.
    seen = {
        (
            eff.strava_athlete_id or normalize_name(eff.athlete_name_raw),
            eff.measured_on,
            eff.elapsed_time_sec,
        )
        for eff in existing_efforts
    }
    # El género ya guardado no se pierde si una pasada posterior no lo trae.
    gender_by_key = {
        (
            eff.strava_athlete_id or normalize_name(eff.athlete_name_raw),
            eff.measured_on,
            eff.elapsed_time_sec,
        ): eff.athlete_gender
        for eff in existing_efforts
        if eff.athlete_gender
    }

    inserted = 0
    for item in payload.efforts:
        key = (
            item.strava_athlete_id or normalize_name(item.athlete_name_raw),
            item.measured_on,
            item.elapsed_time_sec,
        )
        if key in seen:
            continue
        seen.add(key)

        # El identificador de Strava manda; el nombre es el respaldo.
        rider = (
            rider_by_strava_id.get(item.strava_athlete_id)
            if item.strava_athlete_id
            else None
        ) or find_rider(item.athlete_name_raw)

        effort = StravaEffort(
            segment_id=segment.id,
            rider_id=rider.id if rider else None,
            athlete_name_raw=item.athlete_name_raw,
            elapsed_time_sec=item.elapsed_time_sec,
            is_kom_qom=item.is_kom_qom,
            measured_on=item.measured_on,
            strava_athlete_id=item.strava_athlete_id,
            athlete_gender=item.athlete_gender or gender_by_key.get(key),
        )
        session.add(effort)
        inserted += 1

    await session.commit()

    # Los intentos de Strava son los que deciden el KOM, el QOM y los
    # Kamikaze: el resumen de la fecha cacheado ya no vale.
    cache.invalidate_public()

    return {"status": "success", "efforts_synced": inserted}


@router.get("/admin/pending-payments")
async def get_pending_payments(
    session: AsyncSession = Depends(get_session),
    admin_key: str = Depends(verify_admin_key)
):
    # Corredor, categoría, fecha y equipo salen en la misma consulta: antes
    # cada inscripción recargaba las cuatro relaciones (un N+1).
    stmt = (
        select(StageEntry, Rider, Category, Stage, Team)
        .outerjoin(Rider, StageEntry.rider_id == Rider.id)
        .outerjoin(Category, StageEntry.category_id == Category.id)
        .outerjoin(Stage, StageEntry.stage_id == Stage.id)
        .outerjoin(Team, StageEntry.team_id == Team.id)
        .where(StageEntry.payment_status == PaymentStatusEnum.PENDING)
        .order_by(StageEntry.id.desc())
    )
    entries = (await session.exec(stmt)).all()
    results = []
    for e, rider, category, stage, team in entries:
        results.append({
            "entry_id": e.id,
            "bib_number": e.bib_number,
            "stage_name": stage.name if stage else "",
            "rider_name": rider.full_name if rider else "",
            "rider_dni": rider.dni if rider else "",
            "category_name": category.name if category else "",
            "team_name": team.name if team else "LIBRE",
            "voucher_url": e.payment_voucher_url
        })
    return results


@router.post("/admin/entries/{entry_id}/approve-payment")
async def approve_payment(
    entry_id: int,
    session: AsyncSession = Depends(get_session),
    admin_key: str = Depends(verify_admin_key)
):
    stmt = select(StageEntry).where(StageEntry.id == entry_id)
    entry = (await session.exec(stmt)).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Inscripción no encontrada.")

    entry.payment_status = PaymentStatusEnum.PAID
    session.add(entry)
    await session.commit()
    return {"status": "success", "entry_id": entry.id, "payment_status": "PAID"}


@router.get("/admin/feedback-tickets")
async def list_feedback_tickets(
    session: AsyncSession = Depends(get_session),
    admin_key: str = Depends(verify_admin_key)
):
    stmt = select(FeedbackTicket).order_by(FeedbackTicket.created_at.desc())
    tickets = (await session.exec(stmt)).all()
    return tickets
