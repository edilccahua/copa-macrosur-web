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
  const res = await fetch(`${API_V1}/public/standings?${q.toString()}`);
  if (!res.ok) throw new Error(`standings HTTP ${res.status}`);
  return res.json();
}
