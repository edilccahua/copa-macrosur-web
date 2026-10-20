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
