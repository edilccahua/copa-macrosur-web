/**
 * check-anchors.mjs — regresión de las ANCLAS internas del sitio.
 *
 * Lo que se comprueba (y por qué):
 *
 *  1. El clic en un ancla del menú ("FECHAS" → /#fechas) lleva a la sección,
 *     con el margen de la cabecera fija.
 *  2. **Se puede repetir**: el segundo clic también funciona. Antes fallaba:
 *     el router de Astro interceptaba el clic y lanzaba una navegación (para
 *     una ancla, eso es pedir y cambiar la página entera), así que el
 *     elemento de destino y la instancia de Lenis desaparecían a mitad del
 *     recorrido. Por eso nuestro manejador de anclas va en FASE DE CAPTURA:
 *     su `preventDefault()` llega antes que el del router, y Astro se aparta
 *     (sólo navega si el evento NO está cancelado).
 *  3. Un ancla distinta (las del índice de secciones) también lleva a su
 *     sección.
 *  4. **El historial del router sigue íntegro**: `history.state.index` es lo
 *     que Astro usa para saber si el usuario va hacia delante o hacia atrás.
 *     Un `pushState` con un objeto de estado vacío lo borra, y a partir de
 *     ahí el botón "atrás" clasifica mal las navegaciones y el router se
 *     vuelve errático. Por eso la URL se actualiza con `replaceState`,
 *     conservando el estado que Astro guarda.
 *
 * Uso:  node tools/check-anchors.mjs [url]
 */
import { chromium } from 'playwright-core';

const URL = process.argv[2] ?? 'http://127.0.0.1:4321/';
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

const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
await page.goto(URL, { waitUntil: 'networkidle' });
await page.waitForTimeout(1500);

const estado = () =>
  page.evaluate(() => ({
    y: Math.round(window.scrollY),
    hash: location.hash,
    index: history.state?.index,
  }));

/** Posición absoluta de la sección y el margen que deja la cabecera fija. */
const destino = await page.evaluate(() => {
  const el = document.getElementById('fechas');
  if (!el) return null;
  const hdr = document.getElementById('site-header');
  return {
    top: Math.round(el.getBoundingClientRect().top + window.scrollY),
    offset: Math.round(hdr ? hdr.getBoundingClientRect().height : 50) + 8,
  };
});

if (!destino) {
  console.log('AVISO: esta página no tiene la sección "fechas"; se omite.');
  await browser.close();
  process.exit(0);
}

const enlace = await page.$('a[data-nav-anchor][href="/#fechas"]');
ok(Boolean(enlace), 'existe el enlace del menú con ancla');

if (enlace) {
  await enlace.click();
  await page.waitForTimeout(2500);

  const tras1 = await estado();
  ok(
    Math.abs(tras1.y - (destino.top - destino.offset)) < 30,
    `el 1er clic lleva a la sección (y=${tras1.y}, esperado ≈${destino.top - destino.offset})`,
  );
  ok(tras1.hash === '#fechas', `la URL lleva el ancla (${tras1.hash})`);
  ok(tras1.index !== undefined, `el router conserva su índice (index=${tras1.index})`);

  // El segundo clic: el que fallaba.
  await enlace.click();
  await page.waitForTimeout(2000);
  const tras2 = await estado();
  ok(
    Math.abs(tras2.y - (destino.top - destino.offset)) < 30,
    `el 2º clic también lleva a la sección (y=${tras2.y})`,
  );
  ok(tras2.index !== undefined, `el historial sigue íntegro (index=${tras2.index})`);
}

// Un ancla distinta: las del índice de secciones.
const otra = await page.$('.pageindex__link[href="#clasificacion"]');
if (otra) {
  await otra.click();
  await page.waitForTimeout(2500);
  const tras3 = await estado();
  const esperado = await page.evaluate(() => {
    const el = document.getElementById('clasificacion');
    const hdr = document.getElementById('site-header');
    return (
      Math.round(el.getBoundingClientRect().top + window.scrollY) -
      Math.round(hdr ? hdr.getBoundingClientRect().height : 50) -
      8
    );
  });
  ok(
    Math.abs(tras3.y - esperado) < 40,
    `un ancla distinta también lleva a su sección (y=${tras3.y}, esperado ≈${esperado})`,
  );
  ok(tras3.index !== undefined, `el historial sigue íntegro (index=${tras3.index})`);
} else {
  console.log('AVISO: no hay índice de secciones en esta página');
}

console.log(fallos.length === 0 ? '\nTodo en verde.' : `\n${fallos.length} fallo(s)`);
await browser.close();
process.exit(fallos.length === 0 ? 0 : 1);
