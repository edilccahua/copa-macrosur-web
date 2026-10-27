/**
 * prizes.ts — escala de premios de la edición 2026.
 *
 * La escala vive en la BD (`prize_tiers`, con su `group_key`) y el backend
 * la publica en `GET /api/v1/public/prizes`. Este módulo es la copia de
 * lectura del frontend: mientras la página no la pida a la API, es la fuente
 * de los montos que se pintan.
 *
 * Reglas:
 *  · Acumulado del campeonato: 300/200/100 USD para el líder de puntos de
 *    cada agrupación (PRO y NORMAL). No es por categoría.
 *  · Copa de Equipos acumulada: 500/400/300 USD para el podio de clubes.
 *  · Por fecha: 100/50/30 USD en CADA UNA de las 11 categorías, en cada una
 *    de las cuatro fechas.
 */
import type { IconName } from '../components/Icon.astro';

export type PrizePosition = 1 | 2 | 3;

export interface PrizeStep {
  position: PrizePosition;
  amountUsd?: number;
  label?: string;
}

export interface AccumulatedPrize {
  /** Ámbito del ranking al que pertenece. */
  scope: 'PRO' | 'NORMAL';
  /** Rótulo corto de la tarjeta. */
  label: string;
  /** Texto de contexto. */
  blurb: string;
  /**
   * Icono del ámbito: inline, sin caja, en el color de acento de la tarjeta.
   * Distinto en cada agrupación (regla: el tipo se dice con la palabra y el
   * ícono, specs/03 §Reglas 4).
   */
  icon: IconName;
  tiers: PrizeStep[];
}

/** 300 / 200 / 100 USD al podio de cada agrupación. */
export const ACCUMULATED_PRIZES: AccumulatedPrize[] = [
  {
    scope: 'PRO',
    label: 'PRO',
    blurb: 'Al que más puntos suma en PRO.',
    icon: 'bolt',
    tiers: [
      { position: 1, amountUsd: 300 },
      { position: 2, amountUsd: 200 },
      { position: 3, amountUsd: 100 },
    ],
  },
  {
    scope: 'NORMAL',
    label: 'NORMAL',
    blurb: 'Al que más puntos suma en NORMAL.',
    icon: 'users',
    tiers: [
      { position: 1, amountUsd: 300 },
      { position: 2, amountUsd: 200 },
      { position: 3, amountUsd: 100 },
    ],
  },
];

/**
 * El premio por fecha se reparte en CADA una de las 11 categorías, en cada
 * una de las cuatro fechas: no hay un único ganador, hay once podios.
 */
export const PER_DATE_PRIZE_ICON: IconName = 'trophy';

/**
 * Escala por fecha en categorías generales:
 *  · 1er puesto: 50 USD.
 *  · 2do y 3er puesto: Regalo / Presente (para bici o ciclista).
 */
export const PER_DATE_PRIZES: PrizeStep[] = [
  { position: 1, amountUsd: 50 },
  { position: 2, label: 'Regalo / Presente' },
  { position: 3, label: 'Regalo / Presente' },
];

/**
 * Escala por fecha en categoría ELITE:
 *  · 1er puesto: 70 USD.
 *  · 2do y 3er puesto: Regalo / Presente (para bici o ciclista).
 */
export const PER_DATE_PRIZES_ELITE: PrizeStep[] = [
  { position: 1, amountUsd: 70 },
  { position: 2, label: 'Regalo / Presente' },
  { position: 3, label: 'Regalo / Presente' },
];

/**
 * El premio acumulado de EQUIPOS (la Copa de Equipos): 500 / 400 / 300 USD.
 * Es la única escala que NO coincide con la de los corredores, porque el
 * podio de clubes se paga con un presupuesto propio.
 */
export const TEAM_PRIZES: PrizeStep[] = [
  { position: 1, amountUsd: 500 },
  { position: 2, amountUsd: 400 },
  { position: 3, amountUsd: 300 },
];

/** El emblema del premio de equipos: la bandera del club. */
export const TEAM_PRIZE_ICON: IconName = 'flag';

/**
 * Las 11 categorías oficiales. El premio por fecha se reparte en CADA una:
 * no hay una bolsa común para el grupo NORMAL.
 */
export const PRIZE_CATEGORIES: string[] = [
  'ELITE',
  'MASTER A',
  'MASTER B',
  'MASTER C',
  'MASTER D',
  'TURISMO OPEN VARONES',
  'TURISMO MASTER VARONES',
  'OPEN DAMAS',
  'DAMAS MASTER',
  'JUVENILES 15 - 17',
  'E-BIKE OPEN',
];

/** Moneda de todos los montos. */
export const PRIZE_CURRENCY = 'USD';
