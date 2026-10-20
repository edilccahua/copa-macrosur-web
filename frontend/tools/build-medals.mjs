/**
 * build-medals.mjs — genera las medallas de podio.
 *
 * LA GEOMETRÍA ES DE STRAVA. Strava publica sus insignias de leaderboard
 * como sprites (`icon-at-pr-01/02/03`, en
 * `web-assets.strava.com/assets/svg/2024/sprites/`): una silueta de
 * "bolsillo" con la cinta y, en el disco, el puesto CALADO al vacío.
 *
 * Acá se reproducen esas siluetas y esos números LITERALMENTE (los
 * trazados se copiaron de los sprites de Strava), con dos ajustes:
 *
 *   1. Strava usa "PR" en el primer puesto; el campeonato usa 1, 2, 3. El
 *      "2" y el "3" son los de Strava; el "1" está dibujado con la misma
 *      construcción (trazo de 2 unidades sobre 8 de alto, remates rectos y
 *      bandera diagonal a la izquierda).
 *
 *   2. El color no se hornea en la versión canónica: se usa
 *      `currentColor`, de modo que la hoja de estilo lo decide (tokens
 *      `--medal-N`) y la medalla se adapta al tema claro/oscuro. La copia
 *      de `public/` sí lleva el color horneado, porque como <img> no
 *      hereda nada del sitio.
 *
 * El "calado" se hace con `fill-rule="evenodd"`: silueta y número van en el
 * MISMO path, así el número queda como troquel y se ve el fondo real de la
 * página (no un hueco "vacío" de archivo).
 *
 *     node tools/build-medals.mjs
 */
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const SRC = join(ROOT, 'src', 'assets', 'medals');
const PUBLIC = join(ROOT, 'public', 'icons', 'medals');

/**
 * Silueta de la medalla de Strava. Son cinco subtrazados dentro de un
 * único path: el contorno exterior (bolsillo + disco), la banda de la
 * cinta, la V del cuello y las dos correas.
 *
 * Copiado de `icon-at-pr-01.svg` (el sprite del primer puesto).
 */
const SHELL = [
  // Contorno exterior: bolsillo arriba, disco abajo.
  'M4.58275 12.997L1.87868 10.2929C1.31607 9.73028 1 8.96722 1 8.17157V3C1 1.34315 2.34315 0 4 0H20C21.6569 0 23 1.34315 23 3V8.17157C23 8.96722 22.6839 9.73028 22.1213 10.2929L19.4173 12.997C19.793 13.9242 20 14.9379 20 16C20 20.4183 16.4183 24 12 24C7.58172 24 4 20.4183 4 16C4 14.9379 4.20696 13.9242 4.58275 12.997Z',
  // La banda de la cinta.
  'M4 2C3.70203 2 3.4345 2.13032 3.25129 2.33708L4.91421 4H19.0858L20.7487 2.33708C20.5655 2.13032 20.298 2 20 2H4Z',
  // La V del cuello.
  'M9.36004 8.44583C10.1866 8.15701 11.0749 8 12 8C12.9251 8 13.8134 8.15701 14.64 8.44583L17.0858 6H6.91421L9.36004 8.44583Z',
  // Correa izquierda.
  'M7.48246 9.39667L3 4.91421V8.17157C3 8.43679 3.10536 8.69114 3.29289 8.87868L5.60577 11.1916C6.12934 10.4964 6.76364 9.88938 7.48246 9.39667Z',
  // Correa derecha.
  'M18.3942 11.1916L20.7071 8.87868C20.8946 8.69114 21 8.43679 21 8.17157V4.91421L16.5175 9.39667C17.2364 9.88938 17.8707 10.4964 18.3942 11.1916Z',
];

/**
 * Los dígitos, dentro del disco (centro 12,16; radio 8; altura 8).
 *
 * "2" y "3" son los de Strava, verbatim. El "1" está dibujado con la misma
 * construcción: asta de 2 de ancho (x 12..14) sobre 8 de alto, remate
 * recto arriba y bandera diagonal a la izquierda.
 */
const DIGITS = {
  // Strava, verbatim (icon-at-pr-02).
  2: 'M15 20V18H11.7957L13.7106 16.8602C15.1472 16.0051 15.4229 14.0398 14.2771 12.8225C13.7832 12.2976 13.0944 12 12.3736 12H12.125C10.4681 12 9.125 13.3431 9.125 15H10.875C10.875 14.3096 11.4346 13.75 12.125 13.75H12.3736C12.6119 13.75 12.8395 13.8484 13.0028 14.0218C13.3815 14.4242 13.2904 15.0738 12.8155 15.3564L10.1627 16.9355C9.44173 17.3646 9 18.1416 9 18.9806V20H15Z',
  // Strava, verbatim (icon-at-pr-03).
  3: 'M9 14H12.5C12.7761 14 13 14.2239 13 14.5C13 14.7761 12.7761 15 12.5 15H11V17H12.5C12.7761 17 13 17.2239 13 17.5C13 17.7761 12.7761 18 12.5 18H9C9 19.1046 9.89543 20 11 20H12.5C13.8807 20 15 18.8807 15 17.5C15 16.9372 14.814 16.4178 14.5002 16C14.814 15.5822 15 15.0628 15 14.5C15 13.1193 13.8807 12 12.5 12H11C9.89543 12 9 12.8954 9 14Z',
  // "1" en la tipografía de Strava: asta de 2 de ancho con la bandera
  // diagonal a la izquierda, remate recto arriba y abajo.
  1: 'M12 12H14V20H12V15.2H10V13.4L12 12Z',
};

/**
 * Colores: los de Strava (`#EEAF0B` oro, `#8B9699` plata, `#C46C3B`
 * bronce). La versión canónica usa `currentColor`; la plana los hornea.
 */
const COLORS = { 1: '#EEAF0B', 2: '#8B9699', 3: '#C46C3B' };

const LABELS = {
  1: 'Medalla de primer lugar',
  2: 'Medalla de segundo lugar',
  3: 'Medalla de tercer lugar',
};

/**
 * @param {number} rank
 * @param {string} fill  `currentColor` o un color horneado.
 */
function svg(rank, fill) {
  const d = [...SHELL, DIGITS[rank]].join('');
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" role="img" aria-label="${LABELS[rank]}">
  <path d="${d}" fill="${fill}" fill-rule="evenodd"/>
</svg>
`;
}

mkdirSync(SRC, { recursive: true });
mkdirSync(PUBLIC, { recursive: true });

for (const rank of [1, 2, 3]) {
  writeFileSync(join(SRC, `medal-${rank}.svg`), svg(rank, 'currentColor'), 'utf8');
  writeFileSync(join(PUBLIC, `medal-${rank}.svg`), svg(rank, COLORS[rank]), 'utf8');
  console.log(
    `medalla ${rank}: src/assets/medals/medal-${rank}.svg + public/icons/medals/medal-${rank}.svg`,
  );
}
