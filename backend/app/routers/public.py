from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select

from backend.app.core.db import get_session
from backend.app.models.entities import (
    Rider, Team, Category, Stage, StageEntry, ChampionshipStanding,
    TeamChampionshipStanding, FeedbackTicket, PaymentStatusEnum, RaceStatusEnum, ExtraEvent,
    PrizeTier,
)
from backend.app.models.schemas import (
    PreRegistrationCreate, FeedbackTicketCreate, ExtraEventRead, PrizeTierRead,
)
from backend.app.services.excel_service import slugify, resolve_or_create_team
from backend.app.services.live_service import resolve_live_status
from backend.app.services.pdf_service import format_ms_to_time
from backend.app.services.standings_service import (
    compute_standings, compute_team_standings, normalize_mode, normalize_scope,
    standings_context,
)

router = APIRouter(prefix="/public", tags=["Public Portal"])


@router.get("/live-status")
async def get_live_status(session: AsyncSession = Depends(get_session)):
    """¿Está abierta la transmisión de llegadas? (specs/02 §6).

    La apertura es automática a las 08:00 de Lima el día de la carrera; el
    cierre es manual del organizador. La portada y `/en-vivo` leen esto para
    no mostrar un enlace "en vivo" cuando no hay carrera.
    """
    return await resolve_live_status(session)


@router.get("/prizes", response_model=List[PrizeTierRead])
async def get_prize_tiers(session: AsyncSession = Depends(get_session)):
    """La escala de premios, en dólares, por categoría y por ámbito.

    Dos ámbitos: `FECHA` (el podio de cada carrera) y `ACUMULADO` (el podio
    final del campeonato). El premio es por categoría: el 1º de cada una de
    las 11 categorías cobra lo que dice su fila.
    """
    tiers = (
        await session.exec(select(PrizeTier).order_by(PrizeTier.scope, PrizeTier.position))
    ).all()
    return [
        PrizeTierRead(
            scope=tier.scope,
            position=tier.position,
            amount_usd=tier.amount_usd,
            label=tier.label,
            currency=tier.currency,
        )
        for tier in tiers
    ]


@router.get("/standings")
async def get_standings(
    stage: Optional[int] = Query(None, description="Id de la fecha; None = última disputada"),
    scope: str = Query("COMBINED", description="COMBINED | PRO | NORMAL | E-BIKE"),
    category_id: Optional[int] = Query(None, description="Acota a una categoría concreta"),
    kind: str = Query("individual", description="individual | teams"),
    mode: str = Query("acumulado", description="acumulado | fecha"),
    session: AsyncSession = Depends(get_session)
):
    """
    Clasificación oficial (patrón Tour de Francia).

    `mode` define qué significa la fecha:
    - "acumulado" (por defecto): la fecha es el CORTE; se suma todo lo disputado
      hasta ahí y la DELTA compara contra la fecha anterior.
    - "fecha": la fecha es la CARRERA exacta; solo se cuentan sus puntos y su
      tiempo, y no hay DELTA (no existe una clasificación previa que comparar).

    `scope` define el ámbito de categorías pooled (COMBINED = PRO + NORMAL);
    `category_id` acota a una categoría y anula el ámbito. `kind=teams` devuelve
    la Copa de Equipos con la misma fecha.
    """
    mode = normalize_mode(mode)
    scope = normalize_scope(scope)
    # Se resuelve primero la fecha efectiva (la última disputada si no se indica):
    # la DELTA necesita un corte concreto para compararlo con la fecha anterior.
    context = await standings_context(
        session, stage_limit=stage, mode=mode, scope=scope, category_id=category_id
    )
    target_stage = context["selected_stage_id"]

    if kind == "teams":
        rows = await compute_team_standings(session, stage_limit=target_stage, mode=mode)
    else:
        rows = await compute_standings(
            session, stage_limit=target_stage, scope=scope, category_id=category_id, mode=mode
        )

    return {
        "kind": kind,
        "scope": scope if kind == "individual" else None,
        "category_id": category_id,
        "mode": mode,
        "rows": rows,
        "context": context,
    }

@router.get("/standings/individual")
async def get_individual_standings(
    category_id: Optional[int] = Query(None, description="Filtro opcional por ID de categoría"),
    session: AsyncSession = Depends(get_session)
):
    stmt = (
        select(ChampionshipStanding, Rider, Category)
        .join(Rider, ChampionshipStanding.rider_id == Rider.id)
        .join(Category, ChampionshipStanding.category_id == Category.id)
        .order_by(ChampionshipStanding.category_id, ChampionshipStanding.current_rank)
    )
    if category_id:
        stmt = stmt.where(ChampionshipStanding.category_id == category_id)

    res = await session.exec(stmt)
    rows = []
    for stand, rider, cat in res.all():
        await session.refresh(rider, ["team"])
        rows.append({
            "standing_id": stand.id,
            "rider_id": rider.id,
            "rider_name": rider.full_name,
            "rider_slug": rider.slug,
            "team_name": rider.team.name if rider.team else "LIBRE",
            "team_slug": rider.team.slug if rider.team else None,
            "category_id": cat.id,
            "category_name": cat.name,
            "current_rank": stand.current_rank,
            "previous_rank": stand.previous_rank,
            "rank_delta": stand.rank_delta,
            "total_points": stand.total_points,
            "first_places_count": stand.first_places_count,
            "total_elapsed_ms": stand.total_elapsed_ms,
            "formatted_total_time": format_ms_to_time(stand.total_elapsed_ms),
            "stages_completed": stand.stages_completed
        })
    return rows


@router.get("/standings/teams")
async def get_team_standings(session: AsyncSession = Depends(get_session)):
    stmt = (
        select(TeamChampionshipStanding, Team)
        .join(Team, TeamChampionshipStanding.team_id == Team.id)
        .order_by(TeamChampionshipStanding.current_rank)
    )
    res = await session.exec(stmt)
    rows = []
    for stand, team in res.all():
        rows.append({
            "team_id": team.id,
            "team_name": team.name,
            "team_slug": team.slug,
            "logo_url": team.logo_url,
            "current_rank": stand.current_rank,
            "previous_rank": stand.previous_rank,
            "rank_delta": stand.rank_delta,
            "total_points": stand.total_points,
            "first_places": stand.first_places_count,
            "second_places": stand.second_places_count,
            "third_places": stand.third_places_count,
            "total_riders": stand.total_riders_participations,
            "total_elapsed_ms": stand.total_elapsed_ms,
            "formatted_total_time": format_ms_to_time(stand.total_elapsed_ms)
        })
    return rows


@router.post("/pre-register")
async def submit_pre_registration(
    data: PreRegistrationCreate,
    session: AsyncSession = Depends(get_session)
):
    stmt_stage = select(Stage).where(Stage.id == data.stage_id)
    stage = (await session.exec(stmt_stage)).first()
    if not stage:
        raise HTTPException(status_code=404, detail="Etapa no encontrada.")

    # Resolver equipo
    team_id = await resolve_or_create_team(session, data.team_name_or_libre)

    # Buscar o crear Rider
    stmt_rider = select(Rider).where(Rider.dni == data.dni)
    rider = (await session.exec(stmt_rider)).first()
    if not rider:
        rider = Rider(
            dni=data.dni,
            full_name=data.full_name.strip().upper(),
            slug=f"{slugify(data.full_name)}-{data.dni[-4:]}",
            gender=data.gender,
            team_id=team_id
        )
        session.add(rider)
        await session.flush()

    # Verificar si ya está inscrito en la etapa
    stmt_entry = select(StageEntry).where(
        StageEntry.stage_id == data.stage_id,
        StageEntry.rider_id == rider.id
    )
    entry = (await session.exec(stmt_entry)).first()
    if entry:
        raise HTTPException(status_code=400, detail="El ciclista ya se encuentra registrado en esta etapa.")

    # Obtener el próximo dorsal disponible
    stmt_max_bib = select(StageEntry.bib_number).where(StageEntry.stage_id == data.stage_id).order_by(StageEntry.bib_number.desc())
    max_bib = (await session.exec(stmt_max_bib)).first() or 0
    next_bib = max_bib + 1

    entry = StageEntry(
        stage_id=data.stage_id,
        rider_id=rider.id,
        category_id=data.category_id,
        team_id=team_id,
        bib_number=next_bib,
        payment_status=PaymentStatusEnum.PENDING,
        payment_voucher_url=data.voucher_url,
        race_status=RaceStatusEnum.REGISTERED
    )
    session.add(entry)
    await session.commit()

    return {
        "status": "success",
        "message": "Pre-inscripción recibida correctamente. Pendiente de validación de pago.",
        "bib_number": next_bib,
        "stage_id": data.stage_id,
        "entry_id": entry.id
    }


@router.post("/feedback")
async def create_feedback_ticket(
    data: FeedbackTicketCreate,
    session: AsyncSession = Depends(get_session)
):
    ticket = FeedbackTicket(
        stage_id=data.stage_id,
        type=data.type,
        submitted_by_name=data.submitted_by_name,
        contact_whatsapp_or_email=data.contact_whatsapp_or_email,
        bib_number_ref=data.bib_number_ref,
        message=data.message
    )
    session.add(ticket)
    await session.commit()
    return {"status": "success", "ticket_id": ticket.id}


@router.get("/extra-events", response_model=List[ExtraEventRead])
async def list_extra_events(session: AsyncSession = Depends(get_session)):
    """
    Retorna los eventos especiales y carreras de ruta no puntuables del campeonato.
    """
    stmt = select(ExtraEvent).where(ExtraEvent.is_active == True)
    events = (await session.exec(stmt)).all()
    return events

