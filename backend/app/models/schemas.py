import uuid
from datetime import date as date_cls, datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field, field_validator
from backend.app.models.entities import (
    GenderEnum, StageStatusEnum, PaymentStatusEnum, RaceStatusEnum,
    TicketTypeEnum, TicketStatusEnum
)


# Timing Sync
class TimeSyncResponse(BaseModel):
    server_time_ms: int


class LiveToggle(BaseModel):
    """Abrir o cerrar la transmisión de una etapa (panel del organizador)."""

    active: bool


# Timing Event Payloads
class TimingEventCreate(BaseModel):
    id: uuid.UUID
    stage_entry_id: int
    checkpoint_id: int
    recorded_at_ms: int
    # El nombre de quien marca (el juez de la fecha). Acotado: el campo
    # acaba en la base de datos y no tiene por qué ser un texto libre.
    recorded_by_admin: str = Field(default="judge", max_length=64)
    force_update: bool = False


class BatchSyncRequest(BaseModel):
    # El juez sincroniza lo que anotó OFFLINE: 500 marcas cubren una jornada
    # entera. Más que eso es un abuso (o un bucle).
    events: List[TimingEventCreate] = Field(max_length=500)


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
    live_closed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class StagePublicRead(BaseModel):
    """La fecha tal como la ve el PÚBLICO: sin credenciales y sin geometría.

    Este es el contrato de lectura de `/api/v1/stages`. Dos campos del modelo
    ORM `Stage` NO están aquí, y no es un descuido:

    · `judge_pin` es una **credencial**: con él se mandan marcaciones de
      cronometraje falsas (`/timing/events`) y se largan mangas
      (`/waves/*/start`). La garantía de que no sale es el `response_model`
      de la ruta, no un filtro a mano (specs/00 §1.4).
    · `route_geojson` pesa ~58 KB y ninguna página lo consume: el perfil se
      dibuja con el SVG estático de `/profiles/{slug}.svg`.

    `distance_km` y `elevation_gain_m` pueden ser `None`: una fecha sin ruta
    publicada (la Fecha 4) no puede afirmar cifras. `None` = "por confirmar",
    no 0.
    """

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
    distance_km: Optional[float] = None
    elevation_gain_m: Optional[int] = None
    laps: int = 1
    strava_route_url: Optional[str] = None
    official_results: Optional[int] = None
    official_points: Optional[int] = None
    live_closed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("date", mode="before")
    @classmethod
    def _fecha_a_texto_iso(cls, value: Any) -> Any:
        """La fecha de la BD es un `date`; en el JSON viaja como texto ISO."""
        if isinstance(value, (date_cls, datetime)):
            return value.isoformat()
        return value


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

    La distancia y el desnivel pueden ser `None`: una fecha sin ruta publicada
    (la Fecha 4) no puede afirmar cifras. `None` = "por confirmar", no 0.

    `official_results` y `official_points` son las cifras que PUBLICA el PDF
    oficial de resultados. Pueden diferir de las recalculadas: el motor
    reparte los puntos por posición (specs/01 §3.1) y, cuando el PDF tiene un
    hueco, al rellenarlo reparte un punto más. La página muestra las dos.
    """

    entries_total: int
    finishers: int
    non_finishers: int
    points_total: int
    distance_km_per_lap: Optional[float] = None
    distance_km_total: Optional[float] = None
    elevation_m_per_lap: Optional[int] = None
    elevation_m_total: Optional[int] = None
    laps: int
    winner_time_ms: Optional[int] = None
    winner_avg_speed_kmh: Optional[float] = None
    categories_count: int
    official_results: Optional[int] = None
    official_points: Optional[int] = None


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
    # Grupo de la categoría: PRO | NORMAL | E-BIKE. Es el acento que lleva el
    # leaderboard de la ficha.
    group: str = "PRO"
    entries: List[PodiumEntryRead]


class TeamPodiumRead(BaseModel):
    team_id: int
    team_name: str
    team_slug: str
    points: int
    riders_counted: int
    best_rank: int
    # Medallas de la jornada: puestos 1º, 2º y 3º conseguidos.
    first_places: int = 0
    second_places: int = 0
    third_places: int = 0


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
    # La traza punto a punto (500 puntos, ~58 KB) NO se serializa: el perfil se
    # dibuja con el SVG estático de `/profiles/{slug}.svg`. El campo sigue en el
    # modelo para el resto del código (scripts, tests), pero ninguna respuesta
    # lo lleva: el `response_model` de la ruta pública usa
    # `RouteProfileSummaryRead`, que ni siquiera lo declara.
    points: List[RoutePointRead] = Field(default_factory=list, exclude=True)


class RouteProfileSummaryRead(BaseModel):
    """El perfil de altimetría SIN la traza punto a punto.

    Mismos campos que `RouteProfileRead` menos `points`: las cifras del perfil
    (desnivel, pendiente, punto de máxima pendiente) son las que consume la
    ficha; los 500 puntos de la traza no los usa nadie.
    """

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

    model_config = ConfigDict(from_attributes=True)


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


class PrizeTierRead(BaseModel):
    """Un peldaño de la escala de premios: un puesto de una categoría."""

    scope: str
    position: int
    amount_usd: int
    label: str
    currency: str = "USD"


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
    """Agregado completo de presentación de una fecha.

    Es el `response_model` de `GET /api/v1/stages/{slug}/summary`: refleja
    EXACTAMENTE lo que devuelve el endpoint. La `stage` va en su versión
    pública (`StagePublicRead`): sin PIN de juez y sin geometría.
    """

    stage: StagePublicRead
    stats: StageStatsRead
    podium: List[CategoryPodiumRead]
    teams: List[TeamPodiumRead]
    strava: List[StravaSegmentSummaryRead]
    checkpoints: List[CheckpointRead]
    awards: List[AwardSummaryRead]
    extremes: StageExtremesRead
    # El perfil sin la traza punto a punto: el dibujo es un SVG estático.
    route_profile: Optional[RouteProfileSummaryRead] = None
    summits: List[SummitRead] = Field(default_factory=list)
    # Los cuatro títulos de montaña de la jornada.
    kom: Optional[MountainTitleRead] = None
    qom: Optional[MountainTitleRead] = None
    kamikaze_male: Optional[MountainTitleRead] = None
    kamikaze_female: Optional[MountainTitleRead] = None
    navigation: StageNavigationRead

    model_config = ConfigDict(from_attributes=True)


class StageDetailPublicRead(BaseModel):
    """La ficha de una fecha (`GET /api/v1/stages/{slug}`).

    El sobre que hoy devuelve el endpoint: la fecha, sus premios especiales,
    sus segmentos de Strava y los extremos de la jornada. La `stage` va en su
    versión pública: sin PIN de juez.
    """

    stage: StagePublicRead
    awards: List[AwardSummaryRead]
    strava_segments: List[Dict[str, Any]]
    extremes: StageExtremesRead

    model_config = ConfigDict(from_attributes=True)


class StageResultsPublicRead(BaseModel):
    """Los resultados de una fecha (`GET /api/v1/stages/{slug}/results`).

    Las filas de cada categoría son libres a propósito: cada una lleva el
    dorsal, el tiempo formateado y los puntos, y el motor de la página decide
    qué columnas pintar.
    """

    stage: StagePublicRead
    categories: Dict[str, List[Dict[str, Any]]]

    model_config = ConfigDict(from_attributes=True)


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
    """La pre-inscripción que escribe el público.

    Los campos están ACOTADOS: llegan sin verificar (escriben en la base de
    datos de la competición) y un nombre de 500 caracteres o un DNI de 2
    dígitos no son datos, son ruido.
    """

    stage_id: int
    dni: str = Field(min_length=6, max_length=20)
    full_name: str = Field(min_length=3, max_length=120)
    gender: GenderEnum
    category_id: int
    team_name_or_libre: str = Field(max_length=120)
    voucher_url: Optional[str] = Field(default=None, max_length=500)


# Feedback Ticket
class FeedbackTicketCreate(BaseModel):
    """El reclamo que escribe el público."""

    stage_id: Optional[int] = None
    type: TicketTypeEnum = TicketTypeEnum.TIMING_CLAIM
    submitted_by_name: str = Field(min_length=2, max_length=120)
    contact_whatsapp_or_email: str = Field(min_length=3, max_length=160)
    bib_number_ref: Optional[int] = None
    message: str = Field(min_length=1, max_length=2000)


# Strava sync
class StravaEffortItem(BaseModel):
    strava_athlete_id: Optional[str] = None
    athlete_name_raw: str
    elapsed_time_sec: int
    is_kom_qom: bool = False
    # Fecha del intento (ISO, "YYYY-MM-DD"). Strava lista intentos de muchas
    # fechas en un mismo segmento: sin esto no se puede filtrar los de la
    # carrera.
    measured_on: Optional[str] = None
    # Género del atleta según Strava ("M" | "F"), tal como lo devuelve el
    # filtro del leaderboard. Es lo que permite separar KOM de QOM.
    athlete_gender: Optional[str] = None


class StravaSyncPayload(BaseModel):
    strava_segment_id: str
    segment_name: str
    distance_m: float
    average_grade: float
    efforts: List[StravaEffortItem]
    # `True` reemplaza los intentos del segmento (comportamiento histórico).
    # El sincronizador de género manda `False` para ir sumando las pasadas de
    # "Todos los tiempos" y "Este año" sin destruir las anteriores.
    replace: bool = True
