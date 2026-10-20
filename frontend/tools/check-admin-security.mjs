/**
 * check-admin-security.mjs — regresión de la CONSOLA DEL ORGANIZADOR.
 *
 * Lo que se comprueba (y por qué):
 *
 *  1. La clave de administrador NO está en el código. Antes vivía en la
 *     página (`const ADMIN_KEY = '…'`): cualquiera que abriera el DevTools
 *     la leía y podía aprobar pagos, pisar la base de datos con un Excel o
 *     abrir la transmisión en vivo. Ahora la escribe el organizador en la
 *     puerta y vive en `sessionStorage` (ver `src/lib/admin.ts`).
 *
 *  2. En el código del frontend no hay NINGÚN secreto con forma de clave
 *     (hex largo). Es la red de seguridad: si alguien vuelve a pegar una
 *     clave en el bundle, el script lo dice antes de que llegue a la red.
 *
 *  3. La cabecera `X-Admin-Key` nunca lleva un valor escrito a mano: o
 *     viene de `adminHeaders()` o no viene.
 *
 *  4. El panel del organizador NO pinta datos con `innerHTML` interpolado.
 *     Los pagos pendientes los escribe QUIEN SE INSCRIBE (nombre, club,
 *     comprobante): con `innerHTML`, un nombre como `<img src=x onerror=…>`
 *     se ejecutaba en el navegador del organizador. El panel pinta nodos
 *     con `textContent`.
 *
 * Uso:  node tools/check-admin-security.mjs
 * Salida: 0 (todo en verde) o 1 (hay un fallo).
 */
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, extname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const RAIZ = dirname(dirname(fileURLToPath(import.meta.url)));
const SRC = join(RAIZ, 'src');
const PAGINA_ADMIN = join(SRC, 'pages', 'admin', 'index.astro');

/** Extensiones que pueden llevar código (o un secreto) en el bundle. */
const EXTENSIONES = new Set([
  '.astro',
  '.ts',
  '.tsx',
  '.js',
  '.jsx',
  '.mjs',
  '.svelte',
  '.vue',
  '.html',
  '.json',
  '.css',
]);

/** El marcador que dejaba la clave vieja cuando se redactó el repositorio. */
const LITERAL_ADMIN_KEY = '<CLAVE-ADMIN-ANTERIOR>';

/** Un secreto con forma de clave: hexadecimal de 32 caracteres o más. */
const SECRETO_EN_HEX = /['"][0-9a-fA-F]{32,}['"]/;

/** Una cabecera `X-Admin-Key` con el valor escrito a mano. */
const CABECERA_CON_LITERAL = /['"]X-Admin-Key['"]\s*:\s*['"][^'"]+['"]/;

/** `innerHTML` con una interpolación `${...}` dentro. */
const INNER_HTML_INTERPOLADO = /innerHTML\s*=[^;]*\$\{/;

const fallos = [];
const ok = (cond, mensaje) => {
  console.log(`${cond ? 'OK  ' : 'FALLO'} ${mensaje}`);
  if (!cond) fallos.push(mensaje);
};

/** Todos los ficheros del árbol `src/` con una extensión de código. */
function ficherosCodigo(directorio) {
  const salida = [];
  for (const entrada of readdirSync(directorio)) {
    const ruta = join(directorio, entrada);
    if (statSync(ruta).isDirectory()) {
      salida.push(...ficherosCodigo(ruta));
    } else if (EXTENSIONES.has(extname(ruta))) {
      salida.push(ruta);
    }
  }
  return salida;
}

const ficheros = ficherosCodigo(SRC);
console.log(`Revisando ${ficheros.length} ficheros de ${relative(RAIZ, SRC)}/\n`);

// ── 1 · La clave de administrador no está en el código ──────────────────────
const conLiteral = ficheros.filter((f) => readFileSync(f, 'utf8').includes(LITERAL_ADMIN_KEY));
ok(
  conLiteral.length === 0,
  `la clave de administrador no aparece en el código${
    conLiteral.length ? ` (${conLiteral.map((f) => relative(RAIZ, f)).join(', ')})` : ''
  }`
);

// ── 2 · Ningún secreto con forma de clave en el bundle ─────────────────────
const conSecreto = ficheros.filter((f) => SECRETO_EN_HEX.test(readFileSync(f, 'utf8')));
ok(
  conSecreto.length === 0,
  `no hay secretos con forma de clave en el bundle${
    conSecreto.length ? ` (${conSecreto.map((f) => relative(RAIZ, f)).join(', ')})` : ''
  }`
);

// ── 3 · La cabecera `X-Admin-Key` nunca lleva un valor escrito a mano ──────
const conCabeceraLiteral = ficheros.filter((f) =>
  CABECERA_CON_LITERAL.test(readFileSync(f, 'utf8'))
);
ok(
  conCabeceraLiteral.length === 0,
  `la cabecera X-Admin-Key nunca lleva una credencial escrita a mano${
    conCabeceraLiteral.length
      ? ` (${conCabeceraLiteral.map((f) => relative(RAIZ, f)).join(', ')})`
      : ''
  }`
);

// ── 4 · El panel no pinta datos con `innerHTML` interpolado ─────────────────
const paginaAdmin = readFileSync(PAGINA_ADMIN, 'utf8');
ok(
  !INNER_HTML_INTERPOLADO.test(paginaAdmin),
  'el panel del organizador no usa innerHTML con interpolación'
);

console.log(fallos.length ? `\n${fallos.length} FALLO(S)` : '\nTodo en verde.');
process.exit(fallos.length ? 1 : 0);
