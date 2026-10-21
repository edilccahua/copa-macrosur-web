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
  short_name?: string | null;
  title?: string | null;
  slug: string;
  date: string;
  /** `null` en una fecha sin ruta publicada: no se puede afirmar la cifra. */
  distance_km: number | null;
  elevation_gain_m?: number | null;
  start_location?: string | null;
  start_time?: string | null;
  laps: number;
  status?: string;
  poster_url?: string | null;
  live_closed_at?: string | null;
}

/**
 * Una fila de la clasificación individual: SÓLO los campos que la tabla
 * pinta. Los que el backend devuelve y la tabla no usa (`team_id`,
 * `category_id`, `category_short_code`, `first_places_count`,
 * `total_elapsed_ms`, `stages_completed`) no viajan: son bytes muertos en el
 * HTML de cada página de clasificación.
 */
export interface StandingsRow {
  rider_id: number;
  rider_name: string;
  rider_slug: string;
  team_name: string;
  team_slug: string | null;
  category_name: string;
  category_rank: number;
  current_rank: number;
  previous_rank: number | null;
  rank_delta: number;
  is_debut: boolean;
  total_points: number;
  formatted_total_time: string;
  gap_to_leader_ms: number;
  formatted_gap: string;
}

/**
 * Una fila de la Copa de Equipos: también SÓLO lo que la tabla pinta
 * (aquí lo único que sobra es `total_elapsed_ms`).
 */
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
  formatted_total_time: string;
  gap_to_leader_ms: number;
  formatted_gap: string;
}

// --- Transporte compacto de las filas ----------------------------------------
//
// Las filas viajan al navegador dentro del atributo `props` del
// `<astro-island>`. Astro serializa ahí cada valor con un envoltorio
// (`[0, valor]`) y escapa cada comilla del atributo: con objetos sueltos, 102
// filas de clasificación occupy ~90 KB de HTML (el 33 % de la página) para
// acabar pintando los MISMOS datos que ya están en el HTML de la tabla.
//
// Por eso las filas viajan COLUMNADAS: la primera fila son los nombres de los
// campos y cada fila es la lista de sus valores. Se repiten los 102 valores,
// no los 102 × 15 nombres de campo. Con el mismo contenido, el payload pasa
// de ~90 KB a ~25 KB de HTML.

/** El orden de los campos de una fila columnada de la clasificación individual. */
export const STANDINGS_ROW_FIELDS = [
  'rider_id',
  'rider_name',
  'rider_slug',
  'team_name',
  'team_slug',
  'category_name',
  'category_rank',
  'current_rank',
  'previous_rank',
  'rank_delta',
  'is_debut',
  'total_points',
  'formatted_total_time',
  'gap_to_leader_ms',
  'formatted_gap',
] as const;

/** El orden de los campos de una fila columnada de la Copa de Equipos. */
export const TEAM_STANDINGS_ROW_FIELDS = [
  'team_id',
  'team_name',
  'team_slug',
  'current_rank',
  'total_points',
  'first_places',
  'second_places',
  'third_places',
  'total_riders',
  'formatted_total_time',
  'gap_to_leader_ms',
  'formatted_gap',
] as const;

/**
 * Empaqueta filas en el JSON columnar que viaja a la isla.
 * `null` conserva los valores ausentes (`previous_rank`, `team_slug`).
 */
function packColumnar<T extends Record<string, unknown>>(
  rows: T[],
  fields: readonly string[]
): string {
  return JSON.stringify([
    fields,
    ...rows.map((row) => fields.map((field) => row[field] ?? null)),
  ]);
}

/**
 * Desempaqueta el JSON columnar y devuelve las filas como objetos.
 * Un payload corrupto no debe tumbar la tabla: se devuelve la lista vacía y
 * la isla vuelve a pedir los datos a la API.
 */
function unpackColumnar<T>(payload: string, fields: readonly string[]): T[] {
  if (!payload) return [];
  try {
    // El primer elemento del array es la lista de campos; el resto son las
    // filas (una lista de valores cada una).
    const parsed = JSON.parse(payload) as unknown[];
    if (!Array.isArray(parsed)) return [];
    const values = parsed.slice(1);
    return values.map((row) => {
      const out: Record<string, unknown> = {};
      fields.forEach((field, i) => {
        out[field] = (row as unknown[])[i] ?? null;
      });
      return out as T;
    });
  } catch {
    return [];
  }
}

/** Empaqueta las filas individuales para el viaje al navegador. */
export function packStandingsRows(rows: StandingsRow[]): string {
  return packColumnar(rows as unknown as Record<string, unknown>[], STANDINGS_ROW_FIELDS);
}

/** Empaqueta las filas de equipos para el viaje al navegador. */
export function packTeamStandingsRows(rows: TeamStandingRow[]): string {
  return packColumnar(
    rows as unknown as Record<string, unknown>[],
    TEAM_STANDINGS_ROW_FIELDS
  );
}

/** Desempaqueta las filas individuales que viajan al navegador. */
export function unpackStandingsRows(payload: string): StandingsRow[] {
  return unpackColumnar<StandingsRow>(payload, STANDINGS_ROW_FIELDS);
}

/** Desempaqueta las filas de equipos que viajan al navegador. */
export function unpackTeamStandingsRows(payload: string): TeamStandingRow[] {
  return unpackColumnar<TeamStandingRow>(payload, TEAM_STANDINGS_ROW_FIELDS);
}

export interface CategoryOption {
  id: number;
  short_code: string;
  name: string;
}

export interface StandingsStats {
  /** Corredores distintos que compitieron (en la ventana que se está viendo). */
  participants: number;
  /** Corredores distintos que cerraron al menos una vez. */
  finishers: number;
  non_finishers: number;
  /** Media de los tiempos de las cogidas terminadas (mezcla categorías). */
  avg_time_ms: number | null;
}

export interface StandingsContext {
  stages: StageOption[];
  selected_stage_id: number | null;
  stages_counted: number;
  total_distance_km: number;
  groups: Record<string, string[]>;
  /** Etiqueta CORTA del ámbito (la de la pestaña). */
  scope_labels: Record<string, string>;
  /** Etiqueta LARGA del ámbito (la de la cinta: "E-BIKE OPEN"). */
  scope_labels_long: Record<string, string>;
  scope_order: string[];
  categories: CategoryOption[];
  /** Cifras de la carrera (o de la ventana acumulada). */
  stats: StandingsStats;
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
 * `scope`: COMBINED | PRO | NORMAL | E-BIKE. `categoryId` acota a una categoría.
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
  /** Puntos que reparte el motor de scoring (specs/01 §3.1). */
  points_total: number;
  /** Distancia POR VUELTA (así se guarda en la BD). `null` = sin ruta. */
  distance_km_per_lap: number | null;
  /** Distancia total de la carrera (per_lap × laps). */
  distance_km_total: number | null;
  elevation_m_per_lap: number | null;
  elevation_m_total: number | null;
  laps: number;
  winner_time_ms: number | null;
  winner_avg_speed_kmh: number | null;
  categories_count: number;
  /** Resultados que PUBLICA el PDF oficial de resultados. */
  official_results: number | null;
  /** Puntos que PUBLICA el PDF oficial. Puede diferir de `points_total`. */
  official_points: number | null;
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
  /** Grupo de la categoría: PRO | NORMAL | E-BIKE (es el acento del leaderboard). */
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
  /** Tag editorial: ESCALADOR | PUNCHER | KAMIKAZE | LLANERO. */
  badge_tag?: 'ESCALADOR' | 'PUNCHER' | 'KAMIKAZE' | 'LLANERO';
  /** Objetivo de premio oficial en la fecha: KOM_QOM | KAMIKAZE | null. */
  award_target?: 'KOM_QOM' | 'KAMIKAZE' | null;
  /** Monto en USD del premio en juego (15 si tiene premio oficial). */
  award_amount_usd?: number | null;
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
  /** El varón más rápido en el descenso más pronunciado de la fecha. */
  kamikaze_male: MountainTitle | null;
  /** La mujer más rápida en ese mismo descenso. */
  kamikaze_female: MountainTitle | null;
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

/**
 * Un peldaño de la escala de premios: un puesto de una categoría.
 * Los montos vienen en dólares de la BD (`prize_tiers`); la página no los
 * escribe a mano.
 */
export interface PrizeTier {
  scope: 'FECHA' | 'ACUMULADO' | string;
  position: number;
  amount_usd: number;
  label: string;
  currency: string;
}

/** La escala de premios de la copa, por fecha y acumulada. */
export async function getPrizeTiers(): Promise<PrizeTier[]> {
  const res = await fetch(`${API_V1}/public/prizes`);
  if (!res.ok) return [];
  const data = await res.json();
  return Array.isArray(data) ? (data as PrizeTier[]) : [];
}

// --- Ventana de transmisión en vivo -----------------------------------------
//
// Una sola fuente para la portada, `/en-vivo` y el admin (specs/02 §6).
// La apertura es automática a las 08:00 de Lima el día de la carrera; el
// cierre es manual del organizador.

export type LiveState = 'live' | 'before_start' | 'closed' | 'no_race_today';

export interface LiveStageBrief {
  id: number;
  stage_number: number;
  name: string;
  short_name: string | null;
  slug: string;
  date: string;
  status: string;
  start_time: string | null;
  poster_url: string | null;
}

export interface LiveStatus {
  active: boolean;
  state: LiveState;
  /** Etapa de hoy o, si hoy no hay carrera, la próxima. */
  stage: LiveStageBrief | null;
  /** Próxima fecha futura (para el aviso informativo). */
  next_stage: LiveStageBrief | null;
  opens_at: string | null;
  closed_at: string | null;
}

export async function getLiveStatus(): Promise<LiveStatus> {
  const res = await fetch(`${API_V1}/public/live-status`, { cache: 'no-store' });
  if (!res.ok) throw new Error(`live-status HTTP ${res.status}`);
  return res.json();
}

// --- Premio CLARO a la remontada --------------------------------------------

export interface RemontadaWinner {
  rider_id: number;
  rider_name: string;
  rider_slug: string;
  team_name: string;
  team_slug: string | null;
  category_name: string;
  category_short_code: string;
  first_stage_number: number;
  first_stage_name: string;
  first_rank: number;
  last_stage_number: number;
  last_stage_name: string;
  last_rank: number;
  positions_gained: number;
}

export interface RemontadaData {
  title: string;
  sponsor_name: string;
  sponsor_logo_url: string;
  amount_usd: number;
  criterion: string;
  stages_counted: number;
  total_stages: number;
  provisional: boolean;
  winner: RemontadaWinner | null;
}

export async function getRemontada(): Promise<RemontadaData | null> {
  try {
    const res = await fetch(`${API_V1}/public/remontada`, { cache: 'no-store' });
    if (!res.ok) return null;
    return (await res.json()) as RemontadaData;
  } catch {
    return null;
  }
}

// --- Agregado de la portada (`GET /public/home`) ----------------------------
//
// La portada hacía SIETE llamadas a la API desde el SSR de Cloudflare (que
// NO cachea el HTML): siete esperas de red entre Render y Neon para
// construir una sola página. `/public/home` devuelve todo en una respuesta:
// una llamada, una espera, un payload que además viene cacheado 60 s en el
// backend.
//
// El payload NO lleva el PIN del juez ni la geometría de la ruta: lo
// primero es una credencial y lo segundo pesa ~58 KB por fecha.

/** Una fila del podio de la portada: nombre y puntos. */
export interface HomePodiumRow {
  rider_name: string;
  total_points: number;
  /** Slug del perfil público (`/corredor/{slug}`). */
  rider_slug?: string | null;
}

/** Una fila del podio de equipos de la portada: club y puntos. */
export interface HomeTeamRow {
  team_name: string;
  total_points: number;
  team_slug?: string | null;
}

/** Los cuatro títulos de montaña de la primera fecha disputada. */
export interface HomeMountainTitles {
  kom: MountainTitle | null;
  qom: MountainTitle | null;
  kamikaze_male: MountainTitle | null;
  kamikaze_female: MountainTitle | null;
}

/** Todo lo que la portada necesita, en una sola respuesta. */
export interface HomeBundle {
  /** El calendario, sin credenciales y sin geometría. */
  stages: StageOption[];
  /** El estado de la transmisión (misma forma que `/public/live-status`). */
  live_status: LiveStatus;
  /** Los tres primeros del acumulado PRO. */
  pro_podium: HomePodiumRow[];
  /** Los tres primeros del acumulado NORMAL. */
  normal_podium: HomePodiumRow[];
  /** Los tres primeros de la Copa de Equipos. */
  teams_podium: HomeTeamRow[];
  /** El premio CLARO a la remontada. */
  remontada: RemontadaData | null;
  /** KOM, QOM y los dos Kamikaze de la primera fecha disputada. */
  mountain_titles: HomeMountainTitles;
}

/**
 * El agregado de la portada.
 *
 * Lanza si el backend no responde: la página degrada a secciones vacías
 * (nunca inventa datos, specs/03 §0.2).
 */
export async function getHomeBundle(): Promise<HomeBundle> {
  const res = await fetch(`${API_V1}/public/home`);
  if (!res.ok) throw new Error(`home HTTP ${res.status}`);
  return res.json();
}

