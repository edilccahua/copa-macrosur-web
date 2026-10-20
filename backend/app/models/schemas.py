import uuid
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict
from backend.app.models.entities import (
    GenderEnum, StageStatusEnum, PaymentStatusEnum, RaceStatusEnum,
    TicketTypeEnum, TicketStatusEnum
)


# Timing Sync
class TimeSyncResponse(BaseModel):
    server_time_ms: int


# Timing Event Payloads
class TimingEventCreate(BaseModel):
    id: uuid.UUID
    stage_entry_id: int
    checkpoint_id: int
    recorded_at_ms: int
    recorded_by_admin: str = "judge"
    force_update: bool = False


class BatchSyncRequest(BaseModel):
    events: List[TimingEventCreate]


class BatchSyncResponse(BaseModel):
    processed: int
    ignored_duplicates: int
    conflicts: List[Dict[str, Any]]


# Wave Start
class WaveStartRequest(BaseModel):
    started_at_ms: Optional[int] = None


# Rider Schemas
class RiderRead(BaseModel):
    id: int
    dni: str
    full_name: str
    slug: str
    team_id: Optional[int] = None
    team_name: Optional[str] = None
    gender: GenderEnum
    avatar_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# Team Schemas
class TeamRead(BaseModel):
    id: int
    name: str
    slug: str
    logo_url: Optional[str] = None
    description: Optional[str] = None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


# Category Schemas
class CategoryRead(BaseModel):
    id: int
    name: str
    short_code: str
    min_age: Optional[int] = None
    max_age: Optional[int] = None
    aliases: List[str] = []

    model_config = ConfigDict(from_attributes=True)


# Stage Schemas
class StageRead(BaseModel):
    id: int
    stage_number: int
    name: str
    short_name: Optional[str] = None
    title: Optional[str] = None
    slug: str
    date: str
    status: StageStatusEnum
    start_location: Optional[str] = None
    start_time: Optional[str] = None
    poster_url: Optional[str] = None
    gpx_file_url: Optional[str] = None
    distance_km: float
    elevation_gain_m: int
    route_geojson: Optional[Dict[str, Any]] = None
    laps: int = 1
    strava_route_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# --- Resumen de presentación de una fecha (`GET /stages/{slug}/summary`) ---
#
# La ficha `/fechas/[slug]` consume este agregado en UNA llamada: cifras de la
# jornada, podio por categoría, podio de equipos, segmentos Strava, checkpoints,
# premios y extremos. La página no recalcula nada (specs/03 §1.2).


class StageStatsRead(BaseModel):
    """Cifras de una jornada.

    `distance_km` y `elevation_gain_m` de la tabla `stages` son POR VUELTA
    (ver `entities.Stage`); aquí se exponen las dos lecturas para que la
    página no las mezcle.
    """

    entries_total: int
    finishers: int
    non_finishers: int
    points_total: int
    distance_km_per_lap: float
    distance_km_total: float
    elevation_m_per_lap: int
    elevation_m_total: int
    laps: int
    winner_time_ms: Optional[int] = None
    winner_avg_speed_kmh: Optional[float] = None
    categories_count: int


class PodiumEntryRead(BaseModel):
    """Un corredor en un podio (por categoría o como extremo de la jornada)."""

    rank: int
    bib_number: int
    rider_name: str
    rider_slug: str
    team_name: str
    team_slug: Optional[str] = None
    formatted_time: str
    points_earned: int


class CategoryPodiumRead(BaseModel):
    category_id: int
    category_name: str
    short_code: str
    entries: List[PodiumEntryRead]


class TeamPodiumRead(BaseModel):
    team_id: int
    team_name: str
    team_slug: str
    points: int
    riders_counted: int
    best_rank: int


class StravaEffortRead(BaseModel):
    athlete_name: str
    elapsed_time_sec: int
    formatted_time: str
    is_kom_qom: bool


class StravaSegmentSummaryRead(BaseModel):
    strava_segment_id: str
    name: str
    distance_m: float
    average_grade: float
    distance_km: float
    efforts: List[StravaEffortRead]
    kom: Optional[StravaEffortRead] = None
    # Tipo del tramo: CLIMB | DESCENT | FLAT.
    kind: str = "FLAT"
    # Lugar del segmento ("Uchumayo, Arequipa"), tal como lo reporta Strava.
    location: Optional[str] = None
    elevation_min_m: Optional[int] = None
    elevation_max_m: Optional[int] = None


class RoutePointRead(BaseModel):
    """Un punto de la traza: kilómetro, altitud y coordenada."""

    km: float
    ele: float
    lat: float
    lon: float


class RouteProfileRead(BaseModel):
    """Perfil de altimetría de la ruta, derivado de su geometría real."""

    distance_km: float
    distance_km_stage: float
    elevation_min_m: int
    elevation_max_m: int
    elevation_gain_m: int
    elevation_loss_m: int
    mean_grade_pct: float
    max_grade_pct: float
    max_grade_at_km: float
    # False cuando la geometría es de UNA vuelta de un circuito por vueltas.
    geometry_covers_full_stage: bool
    points: List[RoutePointRead] = []


class SummitRead(BaseModel):
    """Una cima de la ruta: el «puerto» del perfil de etapa."""

    name: str
    category: str = ""
    distance_km: float = 0.0
    elevation_m: int = 0
    climb_gain_m: int = 0
    avg_grade_pct: float = 0.0
    max_grade_pct: float = 0.0
    lat: Optional[float] = None
    lon: Optional[float] = None
    name_source: str = "geo"


class MountainTitleRead(BaseModel):
    """El King of the Mountain o la Queen of the Mountain de la fecha."""

    strava_segment_id: str
    segment_name: str
    location: Optional[str] = None
    distance_km: float
    average_grade: float
    elevation_min_m: Optional[int] = None
    elevation_max_m: Optional[int] = None
    athlete_name: str
    formatted_time: str
    elapsed_time_sec: int


class CheckpointRead(BaseModel):
    name: str
    order_index: int
    distance_from_start_km: float
    is_finish_line: bool


class AwardSummaryRead(BaseModel):
    title: str
    sponsor_name: Optional[str] = None
    sponsor_logo_url: Optional[str] = None
    prize_description: Optional[str] = None
    metric_value: Optional[str] = None
    winner_name: Optional[str] = None


class StageExtremesRead(BaseModel):
    """Extremos de la jornada. Cualquiera de los dos puede ser `None`."""

    scratch: Optional[PodiumEntryRead] = None
    farolito: Optional[PodiumEntryRead] = None


class StageNavigationRead(BaseModel):
    """Fechas vecinas en el calendario, para la navegación prev/next."""

    prev_slug: Optional[str] = None
    prev_name: Optional[str] = None
    next_slug: Optional[str] = None
    next_name: Optional[str] = None


class StageSummaryRead(BaseModel):
    """Agregado completo de presentación de una fecha."""

    stage: StageRead
    stats: StageStatsRead
    podium: List[CategoryPodiumRead]
    teams: List[TeamPodiumRead]
    strava: List[StravaSegmentSummaryRead]
    checkpoints: List[CheckpointRead]
    awards: List[AwardSummaryRead]
    extremes: StageExtremesRead
    navigation: StageNavigationRead


# Extra Events Schemas
class ExtraEventRead(BaseModel):
    id: int
    name: str
    short_name: Optional[str] = None
    slug: str
    event_type: str
    edition: Optional[str] = None
    dates_text: str
    start_location: Optional[str] = None
    start_time: Optional[str] = None
    distance_text: Optional[str] = None
    description: Optional[str] = None
    poster_url: Optional[str] = None
    whatsapp_contact: Optional[str] = None
    registration_fee_text: Optional[str] = None
    status: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


# Standings Read
class StandingRead(BaseModel):
    rider_id: int
    rider_name: str
    rider_slug: str
    team_name: Optional[str] = None
    category_id: int
    category_name: str
    total_points: int
    first_places_count: int
    current_rank: int
    previous_rank: Optional[int] = None
    rank_delta: int
    total_elapsed_ms: int
    formatted_total_time: str

    model_config = ConfigDict(from_attributes=True)


class TeamStandingRead(BaseModel):
    team_id: int
    team_name: str
    team_slug: str
    logo_url: Optional[str] = None
    total_points: int
    first_places_count: int
    second_places_count: int
    third_places_count: int
    total_riders_participations: int
    total_elapsed_ms: int
    current_rank: int
    previous_rank: Optional[int] = None
    rank_delta: int

    model_config = ConfigDict(from_attributes=True)


# Pre-Registration
class PreRegistrationCreate(BaseModel):
    stage_id: int
    dni: str
    full_name: str
    gender: GenderEnum
    category_id: int
    team_name_or_libre: str
    voucher_url: Optional[str] = None


# Feedback Ticket
class FeedbackTicketCreate(BaseModel):
    stage_id: Optional[int] = None
    type: TicketTypeEnum = TicketTypeEnum.TIMING_CLAIM
    submitted_by_name: str
    contact_whatsapp_or_email: str
    bib_number_ref: Optional[int] = None
    message: str


# Strava sync
class StravaEffortItem(BaseModel):
    strava_athlete_id: Optional[str] = None
    athlete_name_raw: str
    elapsed_time_sec: int
    is_kom_qom: bool = False


class StravaSyncPayload(BaseModel):
    strava_segment_id: str
    segment_name: str
    distance_m: float
    average_grade: float
    efforts: List[StravaEffortItem]
