import datetime
import uuid
from enum import Enum
from typing import Optional, List, Dict, Any
from sqlmodel import SQLModel, Field, Relationship, Column, JSON
from sqlalchemy import UniqueConstraint


class GenderEnum(str, Enum):
    M = "M"
    F = "F"


class StageStatusEnum(str, Enum):
    UPCOMING = "UPCOMING"
    REGISTRATION_OPEN = "REGISTRATION_OPEN"
    LIVE = "LIVE"
    FINISHED = "FINISHED"


class PaymentStatusEnum(str, Enum):
    PENDING = "PENDING"
    PAID = "PAID"
    FREE_GUEST = "FREE_GUEST"


class RaceStatusEnum(str, Enum):
    REGISTERED = "REGISTERED"
    STARTED = "STARTED"
    FINISHED = "FINISHED"
    DNF = "DNF"
    DSQ = "DSQ"
    DNS = "DNS"


class TicketTypeEnum(str, Enum):
    TIMING_CLAIM = "TIMING_CLAIM"
    RACE_SUGGESTION = "RACE_SUGGESTION"
    WEB_BUG = "WEB_BUG"
    OTHER = "OTHER"


class TicketStatusEnum(str, Enum):
    OPEN = "OPEN"
    REVIEWED = "REVIEWED"
    RESOLVED = "RESOLVED"


# 1. Team
class Team(SQLModel, table=True):
    __tablename__ = "teams"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)
    slug: str = Field(unique=True, index=True)
    logo_url: Optional[str] = Field(default=None)
    description: Optional[str] = Field(default=None)
    is_active: bool = Field(default=True)

    riders: List["Rider"] = Relationship(back_populates="team")
    stage_entries: List["StageEntry"] = Relationship(back_populates="team")


# 2. Rider
class Rider(SQLModel, table=True):
    __tablename__ = "riders"

    id: Optional[int] = Field(default=None, primary_key=True)
    dni: str = Field(unique=True, index=True)
    full_name: str = Field(index=True)
    slug: str = Field(unique=True, index=True)
    team_id: Optional[int] = Field(default=None, foreign_key="teams.id", nullable=True)
    birth_date: Optional[datetime.date] = Field(default=None)
    gender: GenderEnum = Field(default=GenderEnum.M)
    strava_athlete_id: Optional[str] = Field(default=None, unique=True, nullable=True)
    avatar_url: Optional[str] = Field(default=None)

    team: Optional[Team] = Relationship(back_populates="riders")
    stage_entries: List["StageEntry"] = Relationship(back_populates="rider")
    standings: List["ChampionshipStanding"] = Relationship(back_populates="rider")


# 3. Category
class Category(SQLModel, table=True):
    __tablename__ = "categories"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    short_code: str = Field(unique=True, index=True)
    min_age: Optional[int] = Field(default=None)
    max_age: Optional[int] = Field(default=None)
    aliases: List[str] = Field(default_factory=list, sa_column=Column(JSON))

    stage_entries: List["StageEntry"] = Relationship(back_populates="category")


# 4. Stage
class Stage(SQLModel, table=True):
    __tablename__ = "stages"

    id: Optional[int] = Field(default=None, primary_key=True)
    stage_number: int = Field(unique=True, index=True)
    name: str = Field(index=True)
    short_name: Optional[str] = Field(default=None)
    title: Optional[str] = Field(default=None)
    slug: str = Field(unique=True, index=True)
    date: datetime.date
    status: StageStatusEnum = Field(default=StageStatusEnum.UPCOMING)
    start_location: Optional[str] = Field(default=None)
    start_time: Optional[str] = Field(default="08:00 AM")
    poster_url: Optional[str] = Field(default=None)
    gpx_file_url: Optional[str] = Field(default=None)
    route_geojson: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    distance_km: Optional[float] = Field(default=None)
    elevation_gain_m: Optional[int] = Field(default=None)
    # Vueltas del circuito: para circuitos por vueltas (p.ej. Z Xtreme),
    # `distance_km` y `elevation_gain_m` son POR VUELTA y `laps` es el máximo de vueltas.
    laps: int = Field(default=1)
    gallery_r2_prefix: Optional[str] = Field(default=None)
    # PIN de juez de esta fecha. NUNCA hay un valor por defecto: se siembra
    # desde el entorno (ver `backend/app/core/secrets.py`) y se rota cambiando
    # la variable `JUDGE_PIN_F{n}` y reejecutando el sembrado.
    judge_pin: str = Field(default="")
    # Enlace público a la ruta de Strava de esta fecha (si existe)
    strava_route_url: Optional[str] = Field(default=None)
    # Cifras PUBLICADAS en el PDF oficial de resultados, para poder contrastar
    # lo que publica el organizador con lo que recalcula el motor (specs/01
    # §3.1). `official_points` puede diferir de la suma recalculada: el PDF de
    # Z Xtreme no imprime el 6º lugar de OPEN DAMAS, y al rellenarse el hueco
    # el motor reparte un punto más. `None` = la fecha no se ha disputado.
    official_results: Optional[int] = Field(default=None)
    official_points: Optional[int] = Field(default=None)
    # Cierre MANUAL de la transmisión en vivo (specs/02 §6). La apertura es
    # automática a las 08:00 de Lima el día de la carrera; el admin la cierra
    # cuando termina de llegar el último ciclista. `NULL` = abierta/never closed.
    live_closed_at: Optional[datetime.datetime] = Field(default=None)

    waves: List["StartWave"] = Relationship(back_populates="stage")
    checkpoints: List["Checkpoint"] = Relationship(back_populates="stage")
    entries: List["StageEntry"] = Relationship(back_populates="stage")
    special_awards: List["SpecialAward"] = Relationship(back_populates="stage")
    summits: List["RouteSummit"] = Relationship(back_populates="stage")


# 5. StartWave
class StartWave(SQLModel, table=True):
    __tablename__ = "start_waves"

    id: Optional[int] = Field(default=None, primary_key=True)
    stage_id: int = Field(foreign_key="stages.id", index=True)
    name: str
    category_ids: List[int] = Field(default_factory=list, sa_column=Column(JSON))
    started_at_ms: Optional[int] = Field(default=None)
    is_individual: bool = Field(default=False)

    stage: Stage = Relationship(back_populates="waves")


# 6. Checkpoint
class Checkpoint(SQLModel, table=True):
    __tablename__ = "checkpoints"

    id: Optional[int] = Field(default=None, primary_key=True)
    stage_id: int = Field(foreign_key="stages.id", index=True)
    name: str
    order_index: int = Field(default=0)
    distance_from_start_km: float = Field(default=0.0)
    is_finish_line: bool = Field(default=False)

    stage: Stage = Relationship(back_populates="checkpoints")


# 6b. RouteSummit — un punto alto de la ruta, con su nombre y su categoría.
#
# Es el "puerto" del perfil de etapa: la cima de un tramo de subida, con el
# nombre del lugar (resuelto con el reverse-geocode de OpenStreetMap al
# sembrar) y su categoría al estilo del Tour (HC, 1, 2, 3).
class RouteSummit(SQLModel, table=True):
    __tablename__ = "route_summits"

    id: Optional[int] = Field(default=None, primary_key=True)
    stage_id: int = Field(foreign_key="stages.id", index=True)
    # Nombre del lugar: "Espíritu Santo", "El Horno", "Cerro La Caldera".
    name: str
    # Categoría del puerto: "HC", "1", "2", "3" o "" si no es un puerto.
    category: str = Field(default="")
    # Kilómetro del recorrido en el que está la cima.
    distance_km: float = Field(default=0.0)
    # Altitud de la cima, en msnm.
    elevation_m: int = Field(default=0)
    # Desnivel acumulado desde el inicio del tramo de subida.
    climb_gain_m: int = Field(default=0)
    # Pendiente media del tramo de subida, en %.
    avg_grade_pct: float = Field(default=0.0)
    # Pendiente máxima del tramo, en %.
    max_grade_pct: float = Field(default=0.0)
    # Latitud y longitud de la cima.
    lat: Optional[float] = Field(default=None)
    lon: Optional[float] = Field(default=None)
    # Dónde sale el nombre: "osm" (geocodificado) o "geo" (derivado).
    name_source: str = Field(default="geo")

    stage: Stage = Relationship(back_populates="summits")


# 7. StageEntry
class StageEntry(SQLModel, table=True):
    __tablename__ = "stage_entries"
    __table_args__ = (
        UniqueConstraint("stage_id", "bib_number", name="uq_stage_entry_stage_bib"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    stage_id: int = Field(foreign_key="stages.id", index=True)
    rider_id: int = Field(foreign_key="riders.id", index=True)
    category_id: int = Field(foreign_key="categories.id", index=True)
    team_id: Optional[int] = Field(default=None, foreign_key="teams.id", nullable=True)
    bib_number: int = Field(index=True)
    payment_status: PaymentStatusEnum = Field(default=PaymentStatusEnum.PENDING)
    payment_voucher_url: Optional[str] = Field(default=None)
    race_status: RaceStatusEnum = Field(default=RaceStatusEnum.REGISTERED)
    start_time_ms: Optional[int] = Field(default=None)
    finish_elapsed_ms: Optional[int] = Field(default=None)
    category_rank: Optional[int] = Field(default=None)
    overall_rank: Optional[int] = Field(default=None)
    points_earned: int = Field(default=0)
    # Vueltas efectivamente completadas por este corredor (2 o 3 en circuitos por vueltas)
    laps: int = Field(default=1)

    stage: Stage = Relationship(back_populates="entries")
    rider: Rider = Relationship(back_populates="stage_entries")
    category: Category = Relationship(back_populates="stage_entries")
    team: Optional[Team] = Relationship(back_populates="stage_entries")
    timing_events: List["TimingEvent"] = Relationship(back_populates="stage_entry")


# 8. TimingEvent
class TimingEvent(SQLModel, table=True):
    __tablename__ = "timing_events"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    stage_entry_id: int = Field(foreign_key="stage_entries.id", index=True)
    checkpoint_id: int = Field(foreign_key="checkpoints.id", index=True)
    recorded_at_ms: int
    elapsed_from_start_ms: Optional[int] = Field(default=None)
    recorded_by_admin: str = Field(default="judge")
    is_verified: bool = Field(default=True)

    stage_entry: StageEntry = Relationship(back_populates="timing_events")


# 9. ChampionshipStanding
class ChampionshipStanding(SQLModel, table=True):
    __tablename__ = "championship_standings"

    id: Optional[int] = Field(default=None, primary_key=True)
    rider_id: int = Field(foreign_key="riders.id", index=True)
    category_id: int = Field(foreign_key="categories.id", index=True)
    total_points: int = Field(default=0)
    first_places_count: int = Field(default=0)
    last_stage_rank: Optional[int] = Field(default=None)
    total_elapsed_ms: int = Field(default=0)
    stages_completed: int = Field(default=0)
    current_rank: int = Field(default=0)
    previous_rank: Optional[int] = Field(default=None)
    rank_delta: int = Field(default=0)

    rider: Rider = Relationship(back_populates="standings")


# 10. TeamStageStanding
class TeamStageStanding(SQLModel, table=True):
    __tablename__ = "team_stage_standings"

    id: Optional[int] = Field(default=None, primary_key=True)
    stage_id: int = Field(foreign_key="stages.id", index=True)
    team_id: int = Field(foreign_key="teams.id", index=True)
    points_earned: int = Field(default=0)
    first_places_count: int = Field(default=0)
    second_places_count: int = Field(default=0)
    riders_scored_count: int = Field(default=0)
    rank: int = Field(default=0)


# 11. TeamChampionshipStanding
class TeamChampionshipStanding(SQLModel, table=True):
    __tablename__ = "team_championship_standings"

    id: Optional[int] = Field(default=None, primary_key=True)
    team_id: int = Field(foreign_key="teams.id", index=True)
    total_points: int = Field(default=0)
    first_places_count: int = Field(default=0)
    second_places_count: int = Field(default=0)
    third_places_count: int = Field(default=0)
    total_riders_participations: int = Field(default=0)
    total_elapsed_ms: int = Field(default=0)
    current_rank: int = Field(default=0)
    previous_rank: Optional[int] = Field(default=None)
    rank_delta: int = Field(default=0)


# 12. StravaSegment
class StravaSegment(SQLModel, table=True):
    __tablename__ = "strava_segments"

    id: Optional[int] = Field(default=None, primary_key=True)
    stage_id: int = Field(foreign_key="stages.id", index=True)
    strava_segment_id: str = Field(index=True)
    name: str
    distance_m: float = Field(default=0.0)
    average_grade: float = Field(default=0.0)
    elevation_profile_json: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    # Lugar del segmento ("Uchumayo, Arequipa"), tal como lo reporta Strava.
    location: Optional[str] = Field(default=None)
    # Altitud mínima y máxima del segmento, en msnm (lo reporta Strava).
    elevation_min_m: Optional[int] = Field(default=None)
    elevation_max_m: Optional[int] = Field(default=None)
    # Clasificación del tramo dentro de la ruta: CLIMB | DESCENT | FLAT.
    # La calcula el seed a partir de `average_grade`; el 1er y el 2º climbed
    # son el King of the Mountain y la Queen of the Mountain de la fecha.
    kind: str = Field(default="FLAT")
    # Kategoría de puerto al estilo del Tour (1, 2, 3, HC) o vacío si no es
    # un puerto. La decide el seed por longitud y pendiente.
    category: Optional[str] = Field(default=None)

    efforts: List["StravaEffort"] = Relationship(back_populates="segment")


# 13. StravaEffort
class StravaEffort(SQLModel, table=True):
    __tablename__ = "strava_efforts"

    id: Optional[int] = Field(default=None, primary_key=True)
    segment_id: int = Field(foreign_key="strava_segments.id", index=True)
    rider_id: Optional[int] = Field(default=None, foreign_key="riders.id", nullable=True)
    athlete_name_raw: str
    elapsed_time_sec: int
    is_kom_qom: bool = Field(default=False)
    # Fecha del intento (ISO, "YYYY-MM-DD"). Strava muestra intentos de muchas
    # fechas en un mismo segmento: sin esta columna no se puede saber cuales
    # son de la carrera y cuales de anos atras.
    measured_on: Optional[str] = Field(default=None, index=True)
    # Identificador del atleta en Strava, para cruzar sin depender del nombre.
    strava_athlete_id: Optional[str] = Field(default=None, index=True)
    # Género del atleta según Strava ("M" | "F"). Los títulos de damas (QOM y
    # la Kamikaze) se resuelven por este campo: hay corredoras de la fecha que
    # no están en `riders`, y su intento solo se reconoce por el filtro de
    # género del leaderboard de Strava.
    athlete_gender: Optional[str] = Field(default=None, index=True)

    segment: StravaSegment = Relationship(back_populates="efforts")


# 14. SpecialAward
class SpecialAward(SQLModel, table=True):
    __tablename__ = "special_awards"

    id: Optional[int] = Field(default=None, primary_key=True)
    stage_id: Optional[int] = Field(default=None, foreign_key="stages.id", nullable=True)
    title: str
    sponsor_name: Optional[str] = Field(default=None)
    sponsor_logo_url: Optional[str] = Field(default=None)
    prize_description: Optional[str] = Field(default=None)
    winner_rider_id: Optional[int] = Field(default=None, foreign_key="riders.id", nullable=True)
    metric_value: Optional[str] = Field(default=None)

    stage: Optional[Stage] = Relationship(back_populates="special_awards")


# 15. FeedbackTicket
class FeedbackTicket(SQLModel, table=True):
    __tablename__ = "feedback_tickets"

    id: Optional[int] = Field(default=None, primary_key=True)
    stage_id: Optional[int] = Field(default=None, foreign_key="stages.id", nullable=True)
    type: TicketTypeEnum = Field(default=TicketTypeEnum.TIMING_CLAIM)
    submitted_by_name: str
    contact_whatsapp_or_email: str
    bib_number_ref: Optional[int] = Field(default=None)
    message: str
    status: TicketStatusEnum = Field(default=TicketStatusEnum.OPEN)
    # SQLModel mapea `datetime` a una columna CON zona horaria: un valor
    # naive (como el `utcnow()` de antes) hace fallar el INSERT en SQLite
    # ("Datetime values must have timezone information"). Se guarda aware,
    # como ya hace `live_service.utc_now()`.
    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )


# 16. ExtraEvent (Eventos Especiales y de Ruta no puntuables del campeonato)
class ExtraEvent(SQLModel, table=True):
    __tablename__ = "extra_events"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    short_name: Optional[str] = Field(default=None)
    slug: str = Field(unique=True, index=True)
    event_type: str = Field(default="ROAD")
    edition: Optional[str] = Field(default=None)
    dates_text: str
    start_location: Optional[str] = Field(default=None)
    start_time: Optional[str] = Field(default=None)
    distance_text: Optional[str] = Field(default=None)
    description: Optional[str] = Field(default=None)
    poster_url: Optional[str] = Field(default=None)
    whatsapp_contact: Optional[str] = Field(default="994382248")
    registration_fee_text: Optional[str] = Field(default=None)
    status: str = Field(default="UPCOMING")
    is_active: bool = Field(default=True)


# 17. PrizeTier (escala de premios en dólares, por categoría y por ámbito)
class PrizeTier(SQLModel, table=True):
    """Premio en dólares para un puesto de una categoría.

    Hay dos ámbitos, porque hay dos clasificaciones:
      · `FECHA`     — el podio de CADA fecha: 1º 70 USD, 2º 50, 3º 30.
      · `ACUMULADO` — el podio final del campeonato: 1º 300 USD, 2º 200, 3º 100.

    El premio es POR CATEGORÍA: el 1º de cada una de las 11 categorías cobra
    lo que dice su fila.

    Montos decididos por el organizador el 20 de Octubre de 2026; en dólares
    porque es como se pagan.
    """

    __tablename__ = "prize_tiers"

    id: Optional[int] = Field(default=None, primary_key=True)
    scope: str = Field(index=True)
    position: int
    amount_usd: int
    label: str
    currency: str = Field(default="USD")


