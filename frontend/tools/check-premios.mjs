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
        podio: [...el.querySelectorAll('.podium__step')].map((r) => ({
          medalla: r.querySelector('.medal') ? 'ok' : null,
          cifra: r.querySelector('.podium__value')?.textContent?.trim() ?? null,
          titular: r.querySelector('.podium__name')?.textContent?.trim() ?? null,
        })),
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

ok(portada.length === 4, `portada: hay 4 tarjetas de premios (${portada.length})`);
ok(
  portada.every((t) => !t.nombre && !t.detalle && !/GANADOR/.test(t.pie ?? '')),
  `portada: las tarjetas NO muestran ganadores provisionales (${portada.map((t) => t.pie).join(' · ')})`
);
ok(
  portada.every((t) => t.podio.length === 3),
  'portada: las 4 tarjetas dibujan el podio'
);
ok(
  portada[0]?.label === 'PRO' && portada[0]?.scope === '· ACUMULADO',
  `portada: el rótulo es "PRO · ACUMULADO" (${portada[0]?.label} ${portada[0]?.scope})`
);
ok(
  portada[2]?.label === 'CADA CATEGORÍA' && portada[2]?.scope === '· POR FECHA',
  `portada: el rótulo es "CADA CATEGORÍA · POR FECHA" (${portada[2]?.label} ${portada[2]?.scope})`
);
ok(
  portada[3]?.label === 'EQUIPOS',
  `portada: la cuarta tarjeta es la de equipos (${portada[3]?.label})`
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

// ── 3 · Los tres iconos son distintos ──────────────────────────────────────
const iconos = portada.map((t) => t.icono);
ok(
  new Set(iconos).size === 4,
  `portada: los cuatro iconos son distintos (${iconos.map((i) => (i ? 'svg' : '—')).join(' · ')})`
);

// ── 6 · /premios: CUATRO secciones, una sola gramática ────────────────────
await page.goto(`${BASE}/premios`, { waitUntil: 'networkidle' });
await page.waitForTimeout(1200);

const secciones = await page.$$eval('.premios-section', (els) =>
  els.map((el) => ({
    id: el.id,
    titulo: el.querySelector('.section-label__text')?.textContent?.trim() ?? null,
    celdas: el.querySelectorAll('.cell').length,
  }))
);
ok(secciones.length === 5, `/premios: hay 5 secciones (${secciones.length})`);
ok(
  secciones.map((s) => s.id).join('·') === 'acumulado·por-fecha·equipos·claro·montana',
  `/premios: las secciones en orden (${secciones.map((s) => s.id).join(' · ')})`
);
ok(
  secciones.map((s) => s.celdas).join('·') === '2·2·2·2·4',
  `/premios: cada sección tiene sus celdas (${secciones.map((s) => s.celdas).join('·')})`
);

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
      etiqueta: el.querySelector('.cell__label')?.textContent?.trim() ?? null,
      cuerpo: el.querySelector('.cell__body')?.textContent?.trim() ?? null,
      monto: el.querySelector('.cell__amount')?.textContent?.trim() ?? null,
      podio: [...el.querySelectorAll('.podium__step')].map((r) => ({
        medalla: r.querySelector('.medal') ? 'ok' : null,
        cifra: r.querySelector('.podium__value')?.textContent?.trim() ?? null,
        titular: r.querySelector('.podium__name')?.textContent?.trim() ?? null,
        provisional: r.querySelector('.podium__state')?.textContent?.trim() ?? null,
        alto: r.querySelector('.podium__block')
          ? Math.round(r.querySelector('.podium__block').getBoundingClientRect().height)
          : 0,
      })),
      sticker: el.querySelector('.cell__sticker')?.textContent?.trim() ?? null,
      puestoEnTexto: el.querySelector('.cell__podium-pos')?.textContent?.trim() ?? null,
      colorKicker: el.querySelector('.cell__label')
        ? getComputedStyle(el.querySelector('.cell__label')).color
        : null,
      colorValor: el.querySelector('.cell__step-value')
        ? getComputedStyle(el.querySelector('.cell__step-value')).color
        : null,
      estado: el.querySelector('.cell__state')?.textContent?.trim() ?? null,
      ganador: el.querySelector('.cell__value')?.textContent?.trim() ?? null,
      detalle: el.querySelector('.cell__detail')?.textContent?.trim() ?? null,
      maxFontSize: sizes.length ? Math.max(...sizes) : 0,
    };
  })
);

ok(
  celdas.length === 12,
  `/premios: hay 12 celdas (8 premios + 1 equipos + 3 notas) (${celdas.length})`
);
ok(
  celdas.filter((c) => c.titulo).every((c) => c.emblema),
  '/premios: cada premio tiene emblema'
);
ok(
  celdas.every((c) => !c.indice),
  '/premios: las tarjetas ya no llevan el número arriba a la derecha'
);
// La referencia admite cuerpos de hasta ~80 caracteres en la celda
// ("Every line is on GitHub under permissive licenses. Read it, fork it,
// build on it."). El criterio del Premio CLARO es el texto oficial que
// publica la API (~150): es la regla del premio, no una explicación.
ok(
  celdas.every((c) => (c.cuerpo?.length ?? 0) <= 150),
  `/premios: las reglas no son párrafos (${celdas.map((c) => c.cuerpo?.length ?? 0).join(' · ')} caracteres)`
);

// ── 6b · El premio se DIBUJA: un podio con medallas, no una tira de cifras ──
const conEscala = celdas.filter((c) => c.podio.length > 0);
ok(
  conEscala.length === 4,
  `/premios: cuatro premios con podio (${conEscala.length})`
);
ok(
  conEscala.every((c) => c.podio.length === 3),
  '/premios: cada podio tiene los tres peldaños'
);
ok(
  conEscala.every((c) => c.podio.every((r) => r.medalla === 'ok')),
  '/premios: cada peldaño lleva su medalla'
);
// El podio: tercero, primero y segundo (el primero en el centro y el más
// alto), con la cifra ENCIMA de su peldaño.
const cifras = (c) => c.podio.map((r) => Number((r.cifra ?? '').replace(/\D/g, '')));
ok(
  conEscala.every((c) => {
    const v = cifras(c);
    return v[0] < v[1] && v[0] < v[2] && v[1] > v[2];
  }),
  `/premios: el podio va 3º 1º 2º con su cifra (${conEscala.map((c) => c.podio.map((r) => r.cifra).join(' · ')).join(' | ')})`
);
ok(
  conEscala.every((c) => c.podio[1].alto > c.podio[2].alto && c.podio[2].alto > c.podio[0].alto),
  'premios: el primer peldaño es el más alto y el tercero el más bajo'
);
// La medalla ya lleva el puesto calado: el "1º" en texto sobra.
ok(
  celdas.every((c) => !c.puestoEnTexto),
  '/premios: no se repite el puesto en texto (la medalla ya lo lleva)'
);

// ── 6b-bis · El premio ÚNICO va como sticker ───────────────────────────────
const conSticker = celdas.filter((c) => c.sticker);
ok(
  conSticker.length === 5,
  `/premios: cinco premios únicos con sticker (${conSticker.length})`
);
ok(
  conSticker.every((c) => /^USD \d+$/.test(c.sticker ?? '')),
  `/premios: el sticker lleva la cifra (${conSticker.map((c) => c.sticker).join(' · ')})`
);
ok(
  conEscala.every((c) => !c.sticker),
  '/premios: las escalas con tres peldaños NO llevan sticker'
);

// ── 6b-ter · El ganador provisional va DENTRO de su peldaño ────────────────
//
// Sólo en los acumulados (PRO, NORMAL y equipos): los por fecha se resuelven
// en cada carrera.
const conGanador = celdas.filter((c) => c.podio.some((r) => r.titular));
ok(
  conGanador.length === 3,
  `/premios: tres podios con ganador provisional (${conGanador.length})`
);
ok(
  conGanador.every((c) => c.podio.every((r) => r.titular && r.provisional)),
  '/premios: cada peldaño lleva su ganador provisional'
);
const porFecha = celdas.filter((c) => c.titulo === 'CADA CATEGORÍA');
ok(
  porFecha.every((c) => c.podio.every((r) => !r.titular)),
  '/premios: el premio por fecha NO muestra ganador (es por fecha)'
);

// ── 6b-cuarto · Sin colores de ámbito: una sola tinta ──────────────────────
const tintes = new Set(
  celdas.flatMap((c) => [c.colorKicker, c.colorValor].filter(Boolean))
);
ok(
  tintes.size <= 2,
  `/premios: los premios usan una sola tinta (${[...tintes].join(' · ')})`
);

// La tira plana "USD 300 / 200 / 100" NO debe aparecer en la tabla.
ok(
  !celdas.some((c) => /\d\s*\/\s*\d\s*\/\s*\d/.test(c.monto ?? '')),
  '/premios: no hay tiras de cifras planas ("300 / 200 / 100")'
);
ok(
  !JSON.stringify(celdas).includes('POR ANUNCIAR'),
  '/premios: no queda "POR ANUNCIAR" en la tabla'
);
ok(
  celdas.some((c) => c.estado?.toLowerCase().includes('provisional') && c.ganador),
  '/premios: los acumulados muestran su ganador provisional'
);

// ── 6c · Los premios POR FECHA no muestran ganador en /premios ─────────────
//
// El KOM de la Fecha 1 no es un premio del campeonato: su ganador se
// publica en la ficha de la fecha. En la escala del campeonato sólo va la
// definición del premio.
const montana = celdas.filter((c) => ['KOM', 'QOM', 'EL KAMIKAZE', 'LA KAMIKAZE'].includes(c.titulo ?? ''));
ok(montana.length === 4, `/premios: los 4 títulos de montaña (${montana.length})`);
ok(
  montana.every((c) => !c.ganador && !c.detalle),
  '/premios: los títulos de montaña NO muestran ganador (es un premio por fecha)'
);

// ── 6d · El rótulo de sección no repite los montos ─────────────────────────
const rotulos = await page.$$eval('.section-label__kicker', (els) =>
  els.map((e) => e.textContent.trim())
);
ok(
  rotulos.length === 5,
  `/premios: las 5 secciones llevan rótulo (${rotulos.length})`
);
ok(
  rotulos.every((r) => !/\d+\s*\/\s*\d+/.test(r)),
  `/premios: los rótulos no repiten los montos (${rotulos.join(' · ')})`
);

// ── 7 · La cabecera: masthead de la referencia, sin panel ───────────────────
const masthead = await page.evaluate(() => {
  const m = document.querySelector('.masthead');
  const t = document.querySelector('.display-title');
  return {
    display: m ? getComputedStyle(m).display : null,
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

// ── 8 · Las tablas: un filete, no un mosaico de cajas ──────────────────────
const tablas = await page.evaluate(() =>
  [...document.querySelectorAll('.prize-table')].map((g) => {
    const cs = getComputedStyle(g);
    const celda = g.querySelector('.cell');
    return {
      gap: cs.gap,
      cols: cs.gridTemplateColumns.split(' ').length,
      celdaBorde: celda ? getComputedStyle(celda).borderTopWidth : null,
    };
  })
);
ok(
  tablas.length === 5,
  `/premios: cada sección es una tabla (${tablas.length})`
);
ok(
  tablas.every((t) => t.gap === '1px'),
  `tablas: el filete se dibuja con un hueco de 1px (${tablas.map((t) => t.gap).join(' · ')})`
);
ok(
  tablas.every((t) => t.celdaBorde === '0px'),
  'tablas: las celdas no tienen borde propio'
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
