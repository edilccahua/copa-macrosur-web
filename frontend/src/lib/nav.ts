/**
 * nav.ts — FUENTE ÚNICA del menú del sitio.
 *
 * Estructura replicada de getartcraft.com (medida en vivo):
 *
 *   [logo] │ HOME IMAGE VIDEO RESOURCES▾ │ DOWNLOAD SUPPORT │ CRAFT APPS │ [iconos]
 *            ↑ grupo 1        ↑ grupo 2 (hairline)   ↑ grupo 3
 *
 * En nuestro caso la marca NO es un item de menú (es el logo) y los destinos
 * son las secciones del campeonato:
 *
 *   [KÚSPIDE] │ INICIO FECHAS CLASIFICACIONES ESPECIALES PREMIOS │ [☀]
 *
 * REGLAS:
 *   - `KÚSPIDE` y `INICIO` llevan a la MISMA página (la portada), pero el que
 *     se marca como activo es `INICIO`: la marca es el logo, no un item.
 *   - El item activo se invierte (pastilla) como en la referencia.
 *   - El estado activo se calcula en el cliente porque la cabecera PERSISTE
 *     entre navegaciones (`transition:persist`): el HTML del servidor no
 *     vuelve a pintarse.
 */

export interface NavItem {
  /** Rótulo visible, en versalitas. */
  label: string;
  /** Destino. */
  href: string;
  /**
   * Prefijos de ruta que consideran este item activo.
   * Se comparan PREFIXOS de pathname (no el href), porque el href puede
   * llevar ancla ("/#fechas") y el fragmento nunca está en el pathname.
   */
  match: string[];
  /** Es un ancla dentro de la página: el shell la resuelve con scroll suave. */
  anchor?: boolean;
}

export interface NavGroup {
  /** Separador vertical antes del grupo (el primero no lleva). */
  separated: boolean;
  items: NavItem[];
}

/**
 * Los destinos del campeonato.
 * "Reclamos" NO está aquí: es una utilidad pública y vive en el pie.
 * La INSCRIPCIÓN tampoco: no hay CTA en la barra (decisión del organizador,
 * 20-Oct-2026). Se llega desde la portada y desde el pie.
 */
export const NAV_GROUPS: NavGroup[] = [
  {
    separated: false,
    items: [
      {
        label: 'INICIO',
        href: '/',
        match: ['/'],
      },
      {
        label: 'FECHAS',
        href: '/#fechas',
        match: ['/fechas'],
        anchor: true,
      },
      {
        label: 'CLASIFICACIONES',
        href: '/ranking-general',
        // Cubre el ranking, las fichas de fecha (que llevan al podio y a la
        // clasificación de esa carrera) y los perfiles de corredor y equipo.
        match: ['/ranking-general', '/corredor', '/equipos'],
      },
      {
        label: 'ESPECIALES',
        href: '/eventos-especiales',
        match: ['/eventos-especiales'],
      },
      {
        label: 'PREMIOS',
        href: '/premios',
        match: ['/premios'],
      },
    ],
  },
];

/** Contacto oficial (WhatsApp del organizador). */
export const CONTACT_WHATSAPP = {
  label: 'WhatsApp',
  href: 'https://wa.me/51994382248',
  phone: '994 382 248',
};

/** Todos los items, planos. */
export const NAV_ITEMS: NavItem[] = NAV_GROUPS.flatMap((g) => g.items);

/**
 * ¿Este item corresponde a la ruta actual?
 * `INICIO` sólo se activa en la portada exacta; el resto, por prefijo.
 */
export function isActivePath(pathname: string, item: NavItem): boolean {
  const path = pathname.replace(/\/+$/, '') || '/';
  return item.match.some((prefix) =>
    prefix === '/' ? path === '/' : path === prefix || path.startsWith(prefix + '/')
  );
}
