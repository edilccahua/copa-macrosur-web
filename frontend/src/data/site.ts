/**
 * site.ts — datos editoriales del campeonato.
 *
 * Modulo portado de la referencia `copiaartcraft/src/data/site.ts` (que alimenta
 * las tarjetas de `/apps`). Aqui la "app" es cada FECHA del campeonato: el
 * componente `AppCard.astro` las presenta con el mismo indice tecnico, el bloque
 * de medio, el titulo y la fila de etiquetas.
 */

export interface CraftApp {
  /** Identificador de clase CSS (`app-<app>`). */
  app: string;
  /** Indice tecnico de la fila, p.ej. "01". */
  index: string;
  /** Nombre corto de la fecha. */
  name: string;
  /** Etiqueta superior (categoria de la fila). */
  category: string;
  /** Texto descriptivo de la fecha. */
  body: string;
  /** Estado editorial de la fila. */
  status: string;
  /** Etiquetas de la base (distancia, desnivel, Etc.). */
  platforms: string[];
}

export const SITE_NAME = 'La Copa MacroSur MTB';
export const SITE_TAGLINE = 'Edición 2026 Kúspide · Kúspide Xtreme Sports';

export const craftApps: CraftApp[] = [
  {
    app: 'joya',
    index: '01',
    name: 'La Joya Extreme',
    category: 'Cross-Country Marathon',
    body: 'Circuito de alta velocidad en Arequipa: 40.85 km con +384 m de desnivel acumulado y cronometraje electrónico por chip.',
    status: 'Finalizada — Resultados oficiales publicados',
    platforms: ['40.85 KM', '+384 M', '17 MAY 2026'],
  },
  {
    app: 'zxtreme',
    index: '02',
    name: 'Kúspide Z Xtreme III',
    category: 'Circuito por Vueltas',
    body: 'Circuito de 11.83 km por vuelta y +280 m de desnivel: 3 vueltas para ELITE y MASTERS, 2 vueltas para el resto de categorías.',
    status: 'Finalizada — Resultados oficiales publicados',
    platforms: ['11.83 KM', '+280 M', '3 VUELTAS', '23 AGO 2026'],
  },
  {
    app: 'poblados',
    index: '03',
    name: 'El Retorno a los Poblados 2',
    category: 'Cross-Country Marathon',
    body: 'Tercera fecha oficial con partida en Chiguata (8:00 AM): 47.23 km con +761 m de desnivel acumulado por los poblados tradicionales.',
    status: 'Inscripciones abiertas',
    platforms: ['47.23 KM', '+761 M', '25 OCT 2026'],
  },
  {
    app: 'quequena',
    index: '04',
    name: 'Quequeña Xtreme III',
    category: 'Cross-Country Marathon',
    body: 'Gran final del campeonato: 45 km con +950 m de desnivel positivo acumulado con partida en la Plaza Principal de Quequeña.',
    status: 'Próximamente',
    platforms: ['45 KM', '+950 M', '13 DIC 2026'],
  },
];
