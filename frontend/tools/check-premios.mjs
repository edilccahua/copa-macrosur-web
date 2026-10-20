/**
 * check-premios.mjs — regresión de las TARJETAS DE PREMIOS.
 *
 * Lo que se comprueba (y por qué):
 *
 *  1. La escala de premios dice la FRECUENCIA de cada premio, no un
 *     "por anunciar" genérico:
 *       · los acumulados (PRO / NORMAL) → el GANADOR PROVISIONAL, con su
 *         nombre y sus puntos (el leading real de la clasificación);
 *       · el premio por fecha → "CADA FECHA";
 *       · los títulos de montaña → "UNO POR FECHA" y, si la fecha aún no tiene
 *         ganador, "SIN GANADOR TODAVÍA".
 *     Antes el "POR ANUNCIAR" estaba en los títulos de montaña, que se pagan
 *     en CADA fecha: la etiqueta mentía sobre la cadencia del premio.
 *
 *  2. El color de la tarjeta vive en el RÓTULO (mono, con color) y en el
 *     icono en línea — sin franja superior, sin chip con borde y sin borde
 *     lateral (specs/03 §Reglas 1 y 4).
 *
 *  3. Los tres iconos son DISTINTOS: PRO, NORMAL y CADA CATEGORÍA no pueden
 *     llevar el mismo.
 *
 *  4. La tarjeta es la MISMA en la portada, en /premios y en la ficha de una
 *     fecha: mismo rótulo en color, mismo icono y mismo pie.
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

/** Lo que dice una tarjeta de premios. */
const leerTarjetas = (page, selector) =>
  page.$$eval(selector, (els) =>
    els.map((el) => {
      const label = el.querySelector('.prize__label');
      const icon = el.querySelector('.prize__icon svg');
      const pie = el.querySelector('.prize__foot-label');
      // La escala tipográfica de la tarjeta: sólo los elementos que
      // PINTAN texto (los contenedores heredan el tamaño de la raíz y no
      // cuentan).
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

const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });

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

// ── 1b · La escala tipográfica es la de la sección 02 ───────────────────────
//
// La sección 02 (PodiumPanel) es toda mono a .75 rem. La escala de premios
// tenía un titular display de 1.5 rem, los montos a 1 rem y el ganador
// provisional a 1.125 rem: tres veces más grande que la clasificación que
// tiene justo encima. Ahora NINGÚN texto de la tarjeta pasa de 14 px.
ok(
  portada.every((t) => t.maxFontSize <= 14),
  `portada: ningún texto de la tarjeta pasa de 14 px (${portada.map((t) => t.maxFontSize).join(' · ')})`
);

// ── 1c · El rótulo lleva la identidad: "PRO · ACUMULADO" ───────────────────
ok(
  portada[0]?.label === 'PRO' && portada[0]?.scope === '· ACUMULADO',
  `portada: el rótulo es "PRO · ACUMULADO" (${portada[0]?.label} ${portada[0]?.scope})`
);
ok(
  portada[2]?.label === 'CADA CATEGORÍA' && portada[2]?.scope === '· POR FECHA',
  `portada: el rótulo es "CADA CATEGORÍA · POR FECHA" (${portada[2]?.label} ${portada[2]?.scope})`
);

// ── 2 · El color vive en el rótulo, no en un borde ─────────────────────────
const colores = portada.map((t) => t.color);
ok(
  new Set(colores).size === 3,
  `portada: los tres rótulos tienen color distinto (${colores.join(' · ')})`
);
ok(
  portada.every((t) => t.borde === portada[0].borde),
  'portada: las tres tarjetas comparten el mismo borde (sin franja ni acento lateral)'
);

// ── 3 · Los tres iconos son distintos ──────────────────────────────────────
const iconos = portada.map((t) => t.icono);
ok(
  new Set(iconos).size === 3,
  `portada: los tres iconos son distintos (${iconos.map((i) => (i ? 'svg' : '—')).join(' · ')})`
);

// ── 4 · /premios ───────────────────────────────────────────────────────────
await page.goto(`${BASE}/premios`, { waitUntil: 'networkidle' });
await page.waitForTimeout(1200);

const premios = await leerTarjetas(page, '.prize');
ok(premios.length === 3, `/premios: hay 3 tarjetas de premios (${premios.length})`);
ok(
  premios[0]?.pie === 'GANADOR PROVISIONAL' && !!premios[0]?.nombre,
  `/premios: PRO dice "GANADOR PROVISIONAL" con nombre (${premios[0]?.nombre})`
);
ok(
  premios[2]?.pie === 'CADA FECHA',
  `/premios: CADA CATEGORÍA dice "CADA FECHA" (${premios[2]?.pie})`
);

const montana = await page.$$eval('.mountain-card', (els) =>
  els.map((el) => ({
    cadencia: el.querySelector('.mountain-card__cadence')?.textContent?.trim() ?? null,
    pendiente: el.querySelector('.mountain-card__pending')?.textContent?.trim() ?? null,
  }))
);
ok(montana.length === 4, `/premios: hay 4 títulos de montaña (${montana.length})`);
ok(
  montana.every((m) => m.cadencia === 'UNO POR FECHA'),
  `/premios: los títulos de montaña dicen "UNO POR FECHA"`
);
ok(
  montana.every((m) => m.pendiente !== 'POR ANUNCIAR'),
  '/premios: ningún título de montaña dice "POR ANUNCIAR"'
);
ok(
  !(await page.content()).includes('POR ANUNCIAR'),
  '/premios: no queda "POR ANUNCIAR" en la página'
);

// ── 5 · La ficha de una fecha usa la MISMA tarjeta ─────────────────────────
await page.goto(`${BASE}/fechas/la-joya-extreme`, { waitUntil: 'networkidle' });
await page.waitForTimeout(1200);

const ficha = await leerTarjetas(page, '.prize');
ok(ficha.length >= 1, `ficha: hay tarjeta de premios (${ficha.length})`);
ok(
  ficha[0]?.pie === 'CADA FECHA',
  `ficha: el premio de la jornada dice "CADA FECHA" (${ficha[0]?.pie})`
);
ok(
  ficha[0]?.icono === premios[2]?.icono,
  'ficha: el icono es el mismo que en la portada y en /premios'
);

await browser.close();

console.log(fallos.length ? `\n${fallos.length} FALLO(S)` : '\nTodo en verde.');
process.exit(fallos.length ? 1 : 0);
