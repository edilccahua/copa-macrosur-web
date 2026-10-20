/**
 * check-premios.mjs — regresión de las TARJETAS DE PREMIOS.
 *
 * Lo que se comprueba (y por qué):
 *
 *  1. PORTADA · La escala de premios dice la FRECUENCIA de cada premio, no
 *     un "por anunciar" genérico:
 *       · los acumulados (PRO / NORMAL) → el GANADOR PROVISIONAL, con su
 *         nombre y sus puntos (el leading real de la clasificación);
 *       · el premio por fecha → "CADA FECHA".
 *     Antes el "POR ANUNCIAR" estaba en los títulos de montaña, que se pagan
 *     en CADA fecha: la etiqueta mentía sobre la cadencia del premio.
 *
 *  2. PORTADA · El color de la tarjeta vive en el RÓTULO (mono, con color) y
 *     en el icono en línea — sin franja superior, sin chip con borde y sin
 *     borde lateral (specs/03 §Reglas 1 y 4).
 *
 *  3. PORTADA · La escala tipográfica es la de la sección 02 (PodiumPanel):
 *     ningún texto de la tarjeta pasa de 14 px.
 *
 *  4. /PREMIOS · La página tiene UNA gramática: los ocho premios son celdas
 *     de la misma tabla (`.cell`), con la misma anatomía (emblema, índice,
 *     titular, regla, cifra y estado). Ni tabla aparte en la cabecera, ni
 *     notas, ni párrafos que repitan lo que dice la celda.
 *
 *  5. /PREMIOS · La cabecera es el masthead de la referencia: titular
 *     grande y bajada. SIN panel de escala al lado.
 *
 * Uso:  node tools/check-premios.mjs [url]
 */
import { chromium } from 'playwright-core';

const PAGE_URL = process.argv[2] ?? 'http://127.0.0.1:4321/';
const BASE = new URL(PAGE_URL).origin;
const CHROME = process.env.CHROME_PATH ?? '/usr/bin/google-chrome-stable';

const browser = await chromium.launch({
  executablePath: CHROME,
  args: ['--no-sandbox', '--disable-gpu', '--hide-scrollbars'],
});

const fallos = [];
const ok = (cond, mensaje) => {
  console.log(`${cond ? 'OK  ' : 'FALLO'} ${mensaje}`);
  if (!cond) fallos.push(mensaje);
};

/** Lo que dice una tarjeta de premios de la portada. */
const leerTarjetas = (page, selector) =>
  page.$$eval(selector, (els) =>
    els.map((el) => {
      const label = el.querySelector('.prize__label');
      const icon = el.querySelector('.prize__icon svg');
      const pie = el.querySelector('.prize__foot-label');
      // La escala tipográfica: sólo los elementos que PINTAN texto (los
      // contenedores heredan el tamaño de la raíz y no cuentan).
      const sizes = [...el.querySelectorAll('*')]
        .filter((n) =>
          [...n.childNodes].some((c) => c.nodeType === 3 && c.textContent.trim())
        )
        .map((n) => parseFloat(getComputedStyle(n).fontSize));
      return {
        label: label?.textContent?.trim() ?? null,
        scope: el.querySelector('.prize__scope')?.textContent?.trim() ?? null,
        color: label ? getComputedStyle(label).color : null,
        icono: icon?.innerHTML ?? null,
        pie: pie?.textContent?.trim() ?? null,
        nombre: el.querySelector('.prize__foot-name')?.textContent?.trim() ?? null,
        detalle: el.querySelector('.prize__foot-detail')?.textContent?.trim() ?? null,
        borde: getComputedStyle(el).borderTopColor,
        maxFontSize: sizes.length ? Math.max(...sizes) : 0,
      };
    })
  );

const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

// ── 1 · La portada ─────────────────────────────────────────────────────────
await page.goto(`${BASE}/`, { waitUntil: 'networkidle' });
await page.waitForTimeout(1200);

const portada = await leerTarjetas(page, '#premios .prize');

ok(portada.length === 3, `portada: hay 3 tarjetas de premios (${portada.length})`);
ok(
  portada[0]?.pie === 'GANADOR PROVISIONAL',
  `portada: PRO dice "GANADOR PROVISIONAL" (${portada[0]?.pie})`
);
ok(!!portada[0]?.nombre, `portada: PRO muestra el nombre del líder (${portada[0]?.nombre})`);
ok(
  /\d+\s*PTS/.test(portada[0]?.detalle ?? ''),
  `portada: PRO muestra los puntos del líder (${portada[0]?.detalle})`
);
ok(
  portada[1]?.pie === 'GANADOR PROVISIONAL' && !!portada[1]?.nombre,
  `portada: NORMAL dice "GANADOR PROVISIONAL" con nombre (${portada[1]?.nombre})`
);
ok(
  portada[2]?.pie === 'CADA FECHA',
  `portada: CADA CATEGORÍA dice "CADA FECHA" (${portada[2]?.pie})`
);

// ── 2 · La escala tipográfica es la de la sección 02 ───────────────────────
ok(
  portada.every((t) => t.maxFontSize <= 14),
  `portada: ningún texto de la tarjeta pasa de 14 px (${portada.map((t) => t.maxFontSize).join(' · ')})`
);

// ── 3 · El rótulo lleva la identidad: "PRO · ACUMULADO" ───────────────────
ok(
  portada[0]?.label === 'PRO' && portada[0]?.scope === '· ACUMULADO',
  `portada: el rótulo es "PRO · ACUMULADO" (${portada[0]?.label} ${portada[0]?.scope})`
);
ok(
  portada[2]?.label === 'CADA CATEGORÍA' && portada[2]?.scope === '· POR FECHA',
  `portada: el rótulo es "CADA CATEGORÍA · POR FECHA" (${portada[2]?.label} ${portada[2]?.scope})`
);

// ── 4 · El color vive en el rótulo, no en un borde ─────────────────────────
const colores = portada.map((t) => t.color);
ok(
  new Set(colores).size === 3,
  `portada: los tres rótulos tienen color distinto (${colores.join(' · ')})`
);
ok(
  portada.every((t) => t.borde === portada[0].borde),
  'portada: las tres tarjetas comparten el mismo borde (sin franja ni acento lateral)'
);

// ── 5 · Los tres iconos son distintos ──────────────────────────────────────
const iconos = portada.map((t) => t.icono);
ok(
  new Set(iconos).size === 3,
  `portada: los tres iconos son distintos (${iconos.map((i) => (i ? 'svg' : '—')).join(' · ')})`
);

// ── 6 · /premios: UNA sola gramática ───────────────────────────────────────
await page.goto(`${BASE}/premios`, { waitUntil: 'networkidle' });
await page.waitForTimeout(1200);

const celdas = await page.$$eval('.cell', (els) =>
  els.map((el) => {
    const sizes = [...el.querySelectorAll('*')]
      .filter((n) =>
        [...n.childNodes].some((c) => c.nodeType === 3 && c.textContent.trim())
      )
      .map((n) => parseFloat(getComputedStyle(n).fontSize));
    return {
      titulo: el.querySelector('.cell__title')?.textContent?.trim() ?? null,
      indice: el.querySelector('.cell__index')?.textContent?.trim() ?? null,
      emblema: el.querySelector('.cell__emblem') ? 'ok' : null,
      cuerpo: el.querySelector('.cell__body')?.textContent?.trim() ?? null,
      monto: el.querySelector('.cell__amount')?.textContent?.trim() ?? null,
      estado: el.querySelector('.cell__state')?.textContent?.trim() ?? null,
      ganador: el.querySelector('.cell__value')?.textContent?.trim() ?? null,
      detalle: el.querySelector('.cell__detail')?.textContent?.trim() ?? null,
      maxFontSize: sizes.length ? Math.max(...sizes) : 0,
    };
  })
);

ok(celdas.length === 8, `/premios: hay 8 celdas de premios (${celdas.length})`);
ok(
  celdas.every((c) => c.emblema && c.titulo && c.cuerpo && c.monto),
  '/premios: todas las celdas tienen la misma anatomía (emblema, titular, regla y cifra)'
);
ok(
  celdas.every((c, i) => c.indice === String(i + 1).padStart(2, '0')),
  `/premios: las celdas van numeradas (${celdas.map((c) => c.indice).join(' ')})`
);
// La referencia admite cuerpos de hasta ~80 caracteres en la celda
// ("Every line is on GitHub under permissive licenses. Read it, fork it,
// build on it."). Más que eso ya es un párrafo, no una regla.
ok(
  celdas.every((c) => (c.cuerpo?.length ?? 0) <= 80),
  `/premios: las reglas de las celdas son de una línea (${celdas.map((c) => c.cuerpo?.length ?? 0).join(' · ')} caracteres)`
);
ok(
  celdas.every((c) => c.estado),
  `/premios: todas las celdas dicen su estado (${celdas.map((c) => c.estado).join(' · ')})`
);
ok(
  !JSON.stringify(celdas).includes('POR ANUNCIAR'),
  '/premios: no queda "POR ANUNCIAR" en la tabla'
);

// ── 7 · La cabecera: masthead de la referencia, sin panel ───────────────────
const masthead = await page.evaluate(() => {
  const m = document.querySelector('.masthead');
  const t = document.querySelector('.display-title');
  return {
    display: m ? getComputedStyle(m).display : null,
    cols: m ? getComputedStyle(m).gridTemplateColumns : null,
    titleSize: t ? parseFloat(getComputedStyle(t).fontSize) : 0,
    panels: document.querySelectorAll('.scale-panel').length,
    notas: document.querySelectorAll('.prize-note').length,
  };
});
ok(
  masthead.display !== 'grid',
  `cabecera: el masthead es de una columna (${masthead.display})`
);
ok(
  masthead.panels === 0,
  `cabecera: no hay panel de escala al lado (${masthead.panels})`
);
ok(
  masthead.titleSize >= 40,
  `cabecera: el titular es grande, como en la referencia (${masthead.titleSize}px)`
);
ok(
  masthead.notas === 0,
  `cabecera: no hay notas sueltas que repitan la tabla (${masthead.notas})`
);

// ── 8 · La tabla: un filete, no un mosaico de cajas ───────────────────────
const tabla = await page.evaluate(() => {
  const g = document.querySelector('.prize-table');
  if (!g) return null;
  const cs = getComputedStyle(g);
  const celda = document.querySelector('.cell');
  return {
    gap: cs.gap,
    cols: cs.gridTemplateColumns.split(' ').length,
    celdaBg: celda ? getComputedStyle(celda).backgroundColor : null,
    celdaBorde: celda ? getComputedStyle(celda).borderTopWidth : null,
  };
});
ok(tabla?.gap === '1px', `tabla: el filete se dibuja con un hueco de 1px (${tabla?.gap})`);
ok(tabla?.cols === 4, `tabla: cuatro columnas (${tabla?.cols})`);
ok(
  tabla?.celdaBorde === '0px',
  `tabla: las celdas no tienen borde propio (${tabla?.celdaBorde})`
);

// ── 9 · La ficha de una fecha sigue usando la tarjeta de la portada ───────
await page.goto(`${BASE}/fechas/la-joya-extreme`, { waitUntil: 'networkidle' });
await page.waitForTimeout(1200);

const ficha = await leerTarjetas(page, '.prize');
ok(ficha.length >= 1, `ficha: hay tarjeta de premios (${ficha.length})`);
ok(
  ficha[0]?.pie === 'CADA FECHA',
  `ficha: el premio de la jornada dice "CADA FECHA" (${ficha[0]?.pie})`
);
ok(
  ficha[0]?.icono === portada[2]?.icono,
  'ficha: el icono es el mismo que en la portada y en /premios'
);

await browser.close();

console.log(fallos.length ? `\n${fallos.length} FALLO(S)` : '\nTodo en verde.');
process.exit(fallos.length ? 1 : 0);
