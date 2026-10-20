/**
 * prizes.ts — escala de premios de la edición 2026.
 *
 * ⚠️ PROVISIONAL: la BD (`prize_tiers`) todavía tiene la escala anterior
 * (por fecha 70/50/30 y acumulado 300/200/100 **por categoría**). El
 * organizador fijó esta escala nueva, pero la migración de datos queda
 * pendiente y documentada en `docs/PREMIOS-PENDIENTE.md`.
 *
 * Mientras esa migración no se haga, esta es la ÚNICA fuente de los montos
 * en el frontend: la portada y /premios leen de aquí, no escriben cifras
 * sueltas en el marcado. Cuando la BD se actualice, este módulo se sustituye
 * por la respuesta de `GET /api/v1/public/prizes`.
 *
 * Reglas:
 *  · Acumulado del campeonato: 300/200/100 USD para el líder de puntos de
 *    cada agrupación (PRO y NORMAL). No es por categoría.
 *  · Por fecha: 100/50/30 USD en CADA UNA de las 11 categorías, en cada una
 *    de las cuatro fechas.
 */
import type { IconName } from '../components/Icon.astro';

export type PrizePosition = 1 | 2 | 3;

export interface PrizeStep {
  position: PrizePosition;
  amountUsd: number;
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
    blurb:
      'Al líder de puntos del acumulado PRO, sumando Elite, Master A, Master B y Master C.',
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
    blurb:
      'Al líder de puntos del acumulado NORMAL, sumando Turismo, Master D, Damas y Juveniles.',
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

/** 100 / 50 / 30 USD en cada categoría, en cada fecha. */
export const PER_DATE_PRIZES: PrizeStep[] = [
  { position: 1, amountUsd: 100 },
  { position: 2, amountUsd: 50 },
  { position: 3, amountUsd: 30 },
];

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
