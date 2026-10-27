import { API_V1, type StageOption, type HeroCardData } from './api';

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

export const RECENT_RESULTS_WINDOW_DAYS = 10;

/**
 * Determina qué etapa y modo debe mostrar la tarjeta del Hero:
 * - 'recent_results': Si una fecha terminó hace <= windowDays (10 días), se priorizan
 *   sus resultados oficiales y podios.
 * - 'upcoming': Si ya pasaron los 10 días o no hay fecha previa, se muestra la próxima
 *   carrera con su cuenta regresiva.
 * - 'finished_all': Si el campeonato terminó por completo.
 */
export function resolveHeroStage(
  stages: StageOption[],
  now: Date = new Date(),
  windowDays: number = RECENT_RESULTS_WINDOW_DAYS
): HeroCardData {
  const finishedStages = stages
    .filter((s) => s.status === 'FINISHED')
    .sort((a, b) => b.stage_number - a.stage_number);
  const lastFinished = finishedStages[0] ?? null;

  const nextUpcoming =
    stages.find((s) => s.status === 'REGISTRATION_OPEN') ??
    stages.find((s) => s.status === 'UPCOMING') ??
    null;

  if (lastFinished) {
    const [y, m, d] = lastFinished.date.split('-').map(Number);
    if (!Number.isNaN(y) && !Number.isNaN(m) && !Number.isNaN(d)) {
      const raceDate = new Date(y, m - 1, d);
      const todayDate = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      const diffMs = todayDate.getTime() - raceDate.getTime();
      const diffDays = Math.round(diffMs / (1000 * 60 * 60 * 24));

      if (diffDays >= 0 && diffDays <= windowDays) {
        return {
          mode: 'recent_results',
          days_since_race: diffDays,
          stage: lastFinished,
          next_stage: nextUpcoming,
        };
      }
    }
  }

  if (nextUpcoming) {
    return {
      mode: 'upcoming',
      days_since_race: null,
      stage: nextUpcoming,
      next_stage: null,
    };
  }

  return {
    mode: 'finished_all',
    days_since_race: null,
    stage: lastFinished,
    next_stage: null,
  };
}
