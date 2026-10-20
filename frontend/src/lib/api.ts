// Cliente base hacia la API FastAPI.
// Centraliza la URL para no hardcodear `localhost:8000` en las páginas/componentes.
// Se configura con la variable pública PUBLIC_API_URL (ver .env.example).
export const API_BASE: string =
  import.meta.env.PUBLIC_API_URL || 'http://localhost:8000';

// Alias retrocompatible usado por el panel del juez.
export const BASE_URL: string = API_BASE;

export const API_V1: string = `${API_BASE}/api/v1`;

// --- Clasificación (ranking) -------------------------------------------------

export interface StageOption {
  id: number;
  stage_number: number;
  name: string;
  slug: string;
  date: string;
  distance_km: number;
  laps: number;
  status?: string;
}

export interface StandingsRow {
  rider_id: number;
  rider_name: string;
  rider_slug: string;
  team_name: string;
  team_slug: string | null;
  category_id: number;
  category_name: string;
  category_short_code: string;
  category_rank: number;
  current_rank: number;
  previous_rank: number | null;
  rank_delta: number;
  is_debut: boolean;
  total_points: number;
  first_places_count: number;
  total_elapsed_ms: number;
  formatted_total_time: string;
  gap_to_leader_ms: number;
  formatted_gap: string;
  stages_completed: number;
}

export interface TeamStandingRow {
  team_id: number;
  team_name: string;
  team_slug: string;
  current_rank: number;
  total_points: number;
  first_places: number;
  second_places: number;
  third_places: number;
  total_riders: number;
  total_elapsed_ms: number;
  formatted_total_time: string;
  gap_to_leader_ms: number;
  formatted_gap: string;
}

export interface CategoryOption {
  id: number;
  short_code: string;
  name: string;
}

export interface StandingsContext {
  stages: StageOption[];
  selected_stage_id: number | null;
  stages_counted: number;
  total_distance_km: number;
  groups: Record<string, string[]>;
  scope_labels: Record<string, string>;
  scope_order: string[];
  categories: CategoryOption[];
}

export interface StandingsResponse {
  kind: 'individual' | 'teams';
  scope: string | null;
  category_id: number | null;
  rows: StandingsRow[] | TeamStandingRow[];
  context: StandingsContext;
}

export interface StandingsParams {
  stage?: number | null;
  scope?: string;
  categoryId?: number | null;
  kind?: 'individual' | 'teams';
  /**
   * "acumulado": la fecha es el corte (se suma todo lo disputado hasta ahí).
   * "fecha": la fecha es la carrera exacta (solo sus puntos y su tiempo).
   */
  mode?: 'acumulado' | 'fecha';
}

/**
 * Ranking acumulado "a la fecha" (patrón Tour de Francia).
 * `scope`: COMBINED | PRO | NORMAL | E-MTB. `categoryId` acota a una categoría.
 */
export async function getStandings(
  params: StandingsParams = {}
): Promise<StandingsResponse> {
  const q = new URLSearchParams();
  if (params.stage != null) q.set('stage', String(params.stage));
  if (params.scope) q.set('scope', params.scope);
  if (params.categoryId != null) q.set('category_id', String(params.categoryId));
  if (params.kind) q.set('kind', params.kind);
  if (params.mode) q.set('mode', params.mode);
  const res = await fetch(`${API_V1}/public/standings?${q.toString()}`);
  if (!res.ok) throw new Error(`standings HTTP ${res.status}`);
  return res.json();
}

// --- Resumen de presentación de una fecha (`/fechas/[slug]`) ----------------
//
// El endpoint `GET /api/v1/stages/{slug}/summary` devuelve en UNA llamada todo
// lo que la ficha de una carrera muestra. La página no recalcula nada y no
// tiene datos literales (specs/03 §1.2).

export interface StageStats {
  entries_total: number;
  finishers: number;
  non_finishers: number;
  points_total: number;
  /** Distancia POR VUELTA (así se guarda en la BD). */
  distance_km_per_lap: number;
  /** Distancia total de la carrera (por_lap × laps). */
  distance_km_total: number;
  elevation_m_per_lap: number;
  elevation_m_total: number;
  laps: number;
  winner_time_ms: number | null;
  winner_avg_speed_kmh: number | null;
  categories_count: number;
}

export interface PodiumEntry {
  rank: number;
  bib_number: number;
  rider_name: string;
  rider_slug: string;
  team_name: string;
  team_slug: string | null;
  formatted_time: string;
  points_earned: number;
}

export interface CategoryPodium {
  category_id: number;
  category_name: string;
  short_code: string;
  /** Grupo de la categoría: PRO | NORMAL | E-MTB (es el acento del leaderboard). */
  group: string;
  entries: PodiumEntry[];
}

export interface TeamPodium {
  team_id: number;
  team_name: string;
  team_slug: string;
  points: number;
  riders_counted: number;
  best_rank: number;
  /** Medallas de la jornada: puestos 1º, 2º y 3º conseguidos. */
  first_places: number;
  second_places: number;
  third_places: number;
}

export interface StravaEffort {
  athlete_name: string;
  elapsed_time_sec: number;
  formatted_time: string;
  is_kom_qom: boolean;
}

export interface StravaSegmentSummary {
  strava_segment_id: string;
  name: string;
  distance_m: number;
  average_grade: number;
  distance_km: number;
  efforts: StravaEffort[];
  kom: StravaEffort | null;
  /** Tipo del tramo: CLIMB | DESCENT | FLAT. */
  kind: 'CLIMB' | 'DESCENT' | 'FLAT';
  /** Lugar del segmento ("Uchumayo, Arequipa"), tal como lo reporta Strava. */
  location: string | null;
  elevation_min_m: number | null;
  elevation_max_m: number | null;
}

export interface Checkpoint {
  name: string;
  order_index: number;
  distance_from_start_km: number;
  is_finish_line: boolean;
}

/** Un punto de la traza: kilómetro, altitud y coordenada. */
export interface RoutePoint {
  km: number;
  ele: number;
  lat: number;
  lon: number;
}

/** El perfil de altimetría de la ruta, derivado de su geometría real. */
export interface RouteProfile {
  distance_km: number;
  distance_km_stage: number;
  elevation_min_m: number;
  elevation_max_m: number;
  elevation_gain_m: number;
  elevation_loss_m: number;
  mean_grade_pct: number;
  max_grade_pct: number;
  max_grade_at_km: number;
  /** False cuando la geometría es de UNA vuelta de un circuito por vueltas. */
  geometry_covers_full_stage: boolean;
  points: RoutePoint[];
}

/** Una cima de la ruta: el «puerto» del perfil de etapa. */
export interface Summit {
  name: string;
  category: string;
  distance_km: number;
  elevation_m: number;
  climb_gain_m: number;
  avg_grade_pct: number;
  max_grade_pct: number;
  lat: number | null;
  lon: number | null;
  name_source: string;
}

/** El King of the Mountain o la Queen of the Mountain de la fecha. */
export interface MountainTitle {
  strava_segment_id: string;
  segment_name: string;
  location: string | null;
  distance_km: number;
  average_grade: number;
  elevation_min_m: number | null;
  elevation_max_m: number | null;
  athlete_name: string;
  formatted_time: string;
  elapsed_time_sec: number;
}

export interface AwardSummary {
  title: string;
  sponsor_name: string | null;
  sponsor_logo_url: string | null;
  prize_description: string | null;
  metric_value: string | null;
  winner_name: string | null;
}

/** Geometría de la ruta: FeatureCollection con una LineString [lon, lat, ele, km]. */
export interface RouteGeoJson {
  type: 'FeatureCollection';
  features: {
    type: 'Feature';
    geometry: {
      type: 'LineString';
      coordinates: [number, number, number, number][];
    };
  }[];
}

export interface StageSummary {
  stage: StageOption & {
    title: string | null;
    short_name: string | null;
    start_location: string | null;
    start_time: string | null;
    poster_url: string | null;
    gpx_file_url: string | null;
    route_geojson: RouteGeoJson | null;
    strava_route_url: string | null;
    laps: number;
    status: 'UPCOMING' | 'REGISTRATION_OPEN' | 'LIVE' | 'FINISHED';
  };
  stats: StageStats;
  podium: CategoryPodium[];
  teams: TeamPodium[];
  strava: StravaSegmentSummary[];
  checkpoints: Checkpoint[];
  awards: AwardSummary[];
  extremes: { scratch: PodiumEntry | null; farolito: PodiumEntry | null };
  route_profile: RouteProfile | null;
  summits: Summit[];
  kom: MountainTitle | null;
  qom: MountainTitle | null;
  navigation: {
    prev_slug: string | null;
    prev_name: string | null;
    next_slug: string | null;
    next_name: string | null;
  };
}

/**
 * Resumen de presentación de una fecha.
 * Lanza `stage-not-found` si la fecha no existe (la página responde 404) y
 * cualquier otro error si el backend no responde (la página responde 503:
 * nunca se inventan datos, specs/03 §0.2).
 */
export async function getStageSummary(slug: string): Promise<StageSummary> {
  const res = await fetch(`${API_V1}/stages/${slug}/summary`);
  if (res.status === 404) throw new Error('stage-not-found');
  if (!res.ok) throw new Error(`summary HTTP ${res.status}`);
  return res.json();
}
