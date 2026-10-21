/**
 * site.ts — datos editoriales del campeonato.
 *
 * FUENTE ÚNICA de la marca. Antes estos valores vivían sueltos: el pie decía
 * "La Copa MacroSur MTB", los rótulos del timeline decían "COPA MACROSUR MTB" y
 * el hero decía "KÚSPIDE", que es el ORGANIZADOR, no el campeonato. Ahora:
 *
 *   - `SITE_NAME`     → el nombre del campeonato (el que va en `<title>`).
 *   - `BRAND_WORDMARK`→ el rótulo grande del hero (dos palabras, sin acentos).
 *   - `BRAND_EDITION` → el año de la edición.
 *   - `BRAND_NAV`     → la marca en el MENÚ PRINCIPAL. Aquí sí va "KÚSPIDE":
 *     es el logo del organizador (Kuspide Xtreme Sports), que es lo que
 *     aparece en la cabecera de los pósters oficiales.
 *
 * Los rótulos salen de los pósters oficiales de `races/info/`:
 * "LA COPA MACROSUR MTB · EDICIÓN 2026 · KUSPIDE".
 */

/** El campeonato, como aparece en el `<title>` y en los textos legales. */
export const SITE_NAME = 'Copa MacroSur MTB';

/** Bajada: edición + organizador. */
export const SITE_TAGLINE = 'Edición 2026 · Kuspide Xtreme Sports';

/** Rótulo grande del hero. */
export const BRAND_WORDMARK = 'COPA MACROSUR MTB';

/**
 * Palabra que va en el amarillo de carrera. En los pósters, "MTB" es la
 * única palabra en amarillo del lockup (cartel madre + Z Xtreme).
 */
export const BRAND_ACCENT = 'MTB';

/** Etiqueta de edición que acompaña al rótulo. */
export const BRAND_EDITION = 'EDICIÓN 2026';

/**
 * La marca en el MENÚ PRINCIPAL (cabecera). Se queda "KÚSPIDE" a propósito:
 * en los pósters oficiales, Kúspide es el organizador y la copa es el
 * campeonato. Son dos cosas distintas y la cabecera muestra al organizador.
 */
export const BRAND_NAV = 'KÚSPIDE';

/**
 * Forma de una "fila de campeonato" para `AppCard.astro` (puerto de
 * `copiaartcraft`). Se conserva el TIPO porque el componente sigue portado;
 * el ARRAY de datos que había aquí (`craftApps`) se eliminó: duplicaba a mano
 * las cuatro fechas y por eso se quedó desfasado (decía 55.4 km y +920 m
 * para La Joya cuando la ruta oficial son 40.85 km y +384 m). Los datos de las
 * fechas salen de la API.
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
