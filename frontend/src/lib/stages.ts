import { API_V1, type StageOption } from './api';

/**
 * stages.ts — el calendario del campeonato para el servidor.
 *
 * El pie de página lo usaba, y la portada también: sin este caché cada
 * página pedía las fechas por su cuenta. El módulo vive en el proceso de
 * Node (SSR), así que la caché es por proceso.
 */

let cache: { data: StageOption[]; at: number } | null = null;

/** 60 s: bastante corto para que un cambio de estado se vea pronto. */
const TTL_MS = 60_000;

export async function getStages(): Promise<StageOption[]> {
  const fresh = cache && Date.now() - cache.at < TTL_MS;
  if (fresh) return cache!.data;

  try {
    const res = await fetch(`${API_V1}/stages`);
    if (!res.ok) return cache?.data ?? [];
    const data = (await res.json()) as StageOption[];
    cache = { data, at: Date.now() };
    return data;
  } catch {
    return cache?.data ?? [];
  }
}

const MONTHS = ['ENE', 'FEB', 'MAR', 'ABR', 'MAY', 'JUN', 'JUL', 'AGO', 'SEP', 'OCT', 'NOV', 'DIC'];

/** "17 MAY 2026" a partir de "2026-05-17". */
export function formatStageDate(iso: string): string {
  const [y, m, d] = iso.split('-');
  if (!y || !m || !d) return iso;
  return `${d} ${MONTHS[Number(m) - 1] ?? m} ${y}`;
}

/** "17 MAY" (sin el año), para el pie. */
export function formatStageDateShort(iso: string): string {
  const [, m, d] = iso.split('-');
  if (!m || !d) return iso;
  return `${d} ${MONTHS[Number(m) - 1] ?? m}`;
}
