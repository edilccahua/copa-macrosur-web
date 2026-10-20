/**
 * mountain-titles.ts — los cuatro títulos de montaña de cada fecha.
 *
 * El ganador NO se escribe aquí: lo calcula el backend con los intentos de
 * Strava de la ruta oficial (specs/03 §1.2 y §1.4) y la ficha de la fecha lo
 * devuelve en `kom`, `qom`, `kamikaze_male` y `kamikaze_female`.
 *
 * La edición 2026 paga **USD 15 a cada ganador**.
 */
export interface MountainTitleDef {
  key: 'kom' | 'qom' | 'kamikaze_male' | 'kamikaze_female';
  title: string;
  subtitle: string;
  criterion: string;
  amountUsd: number;
  icon: 'mountain' | 'descent';
}

export const MOUNTAIN_TITLES: MountainTitleDef[] = [
  {
    key: 'kom',
    title: 'KOM',
    subtitle: 'King of the Mountain',
    criterion: 'El varón más rápido en la subida más empinada de la fecha.',
    amountUsd: 15,
    icon: 'mountain',
  },
  {
    key: 'qom',
    title: 'QOM',
    subtitle: 'Queen of the Mountain',
    criterion: 'La dama más rápida en esa misma subida. Nunca puede ser un varón.',
    amountUsd: 15,
    icon: 'mountain',
  },
  {
    key: 'kamikaze_male',
    title: 'EL KAMIKAZE',
    subtitle: 'Mejor descenso · varones',
    criterion: 'El varón más rápido en el descenso más pronunciado de la fecha.',
    amountUsd: 15,
    icon: 'descent',
  },
  {
    key: 'kamikaze_female',
    title: 'LA KAMIKAZE',
    subtitle: 'Mejor descenso · damas',
    criterion: 'La dama más rápida en ese mismo descenso.',
    amountUsd: 15,
    icon: 'descent',
  },
];

export const MOUNTAIN_TITLES_TOTAL_USD = MOUNTAIN_TITLES.reduce(
  (total, title) => total + title.amountUsd,
  0
);
