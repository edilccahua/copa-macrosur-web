/**
 * nav.ts — FUENTE ÚNICA del menú del sitio.
 *
 * Antes el menú estaba duplicado: la barra, el panel móvil y el pie tenían
 * cada uno su propia lista, con destinos que no coincidían ("Copa de equipos"
 * apuntaba a la misma URL que "Ranking acumulado" y "Resultados oficiales"
 * estaba fijado a la Fecha 1). Aquí hay una sola definición y todo lo demás
 * se deriva de ella.
 *
 * REGLAS (evaluadas contra getartcraft.com):
 *   - La MARCA no es un item de menú: el wordmark "KÚSPIDE" es el logo y
 *     lleva a la portada. En artcraft el brand es un icono y el menú arranca
 *     en el primer destino real. Por eso no existe "Campeonato" en el nav:
 *     would ser el mismo destino que el logo.
 *   - El menú se agrupa y cada grupo va separado por un hairline vertical
 *     (`<li class="border-l ml-1.5 pl-1.5">` en el original).
 *   - Un item activo se invierte (pastilla) y `aria-current="page"` lo
 *     anuncia a los lectores de pantalla.
 */

export interface NavItem {
  /** Rótulo visible, en versalitas. */
  label: string;
  /** Destino. */
  href: string;
  /**
   * Prefijos de ruta que consideran este item activo.
   * El estado activo se calcula en el cliente porque la cabecera PERSISTE
   * entre navegaciones (astro:transitions): el HTML del servidor no vuelve
   * a pintarse.
   */
  match: string[];
  /** Abre en otra pestaña (contacto). */
  external?: boolean;
}

export interface NavGroup {
  /** Separador vertical antes del grupo (el primero no lleva). */
  separated: boolean;
  items: NavItem[];
}

/**
 * Los destinos del campeonato. "Reclamos" NO está aquí: es una utilidad
 * pública, vive en el pie (decisión del organizador, 20-Oct-2026).
 */
export const NAV_GROUPS: NavGroup[] = [
  {
    separated: false,
    items: [
      {
        label: 'CLASIFICACIONES',
        href: '/ranking-general',
        // Cubre el ranking, las fichas de fecha (que llevan al podio y a la
        // clasificación de esa carrera) y los perfiles de corredor y equipo:
        // todos son, en el fondo, vistas de la clasificación.
        match: ['/ranking-general', '/fechas', '/corredor', '/equipos'],
      },
    ],
  },
  {
    separated: true,
    items: [
      {
        label: 'EVENTOS RUTA',
        href: '/eventos-especiales',
        match: ['/eventos-especiales'],
      },
    ],
  },
];

/** CTA único de la barra. Antes "Inscripciones" estaba DOS veces. */
export const HEADER_CTA: NavItem = {
  label: 'INSCRIPCIÓN',
  href: '/inscripciones',
  match: ['/inscripciones'],
};

/** Contacto oficial (WhatsApp del organizador). */
export const CONTACT_WHATSAPP = {
  label: 'WhatsApp',
  href: 'https://wa.me/51994382248',
  phone: '994 382 248',
};

/** Todos los items, planos, para el panel móvil. */
export const NAV_ITEMS: NavItem[] = NAV_GROUPS.flatMap((g) => g.items);

/**
 * ¿Este item corresponde a la ruta actual?
 * Se comparan PREFIXOS de pathname (no el href), porque el href puede
 * llevar query string ("/ranking-general?tabla=EQUIPO") y el fragmento
 * ("/#fechas") nunca está en el pathname.
 */
export function isActivePath(pathname: string, item: NavItem): boolean {
  const path = pathname.replace(/\/+$/, '') || '/';
  return item.match.some((prefix) =>
    prefix === '/' ? path === '/' : path === prefix || path.startsWith(prefix + '/')
  );
}

/** Rótulo del item activo para una ruta, o null. */
export function activeLabel(pathname: string): string | null {
  const found = NAV_ITEMS.find((item) => isActivePath(pathname, item));
  return found ? found.label : null;
}
