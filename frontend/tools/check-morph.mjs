/**
 * check-morph.mjs — regresión del MORPH del póster (portada → ficha).
 *
 * El morph comparte el nombre `poster-{slug}` entre el póster de la tarjeta
 * del timeline y el del hero de la ficha. Por regla de la especificación de
 * las View Transitions, ese nombre tiene que ser ÚNICO en el documento: si
 * dos elementos lo comparten, la transición de ese nombre se CANCELA y el
 * morph no ocurre.
 *
 * La línea de tiempo se renderiza DOS veces (copia de escritorio y copia
 * móvil, una se oculta con CSS), así que el nombre se asigna en tiempo de
 * ejecución y sólo a la copia visible (ver `TimelineEvents.astro`).
 *
 * Comprueba tres cosas:
 *
 *   1. En la portada, el nombre `poster-la-joya-extreme` lo lleva UN SOLO
 *      elemento (la copia visible): no hay colisión.
 *   2. Al abrir la ficha, la transición ocurre: durante ella hay una
 *      animación de `::view-transition-*(poster-la-joya-extreme)`.
 *   3. La navegación es de CLIENTE (el morph lo dispara el router de Astro:
 *      con `window.location.href` la página se recarga entera y el morph no
 *      se ve).
 *
 * Uso:  node tools/check-morph.mjs [url]
 */
import { chromium } from 'playwright-core';

const URL = process.argv[2] ?? 'http://127.0.0.1:4323/';
const CHROME = process.env.CHROME_PATH ?? '/usr/bin/google-chrome-stable';
const SLUG = 'la-joya-extreme';
const NOMBRE = `poster-${SLUG}`;

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

// --- 1. El nombre del morph no puede estar duplicado -------------------------
const nombres = await page.evaluate(() => {
  const cuenta = {};
  for (const el of document.querySelectorAll('*')) {
    const nombre = getComputedStyle(el).viewTransitionName;
    if (!nombre || nombre === 'none') continue;
    cuenta[nombre] = (cuenta[nombre] ?? 0) + 1;
  }
  return cuenta;
});

const duplicados = Object.entries(nombres).filter(([, n]) => n > 1);
ok(
  (nombres[NOMBRE] ?? 0) === 1,
  `el nombre "${NOMBRE}" lo lleva un solo elemento (${nombres[NOMBRE] ?? 0})`
);
ok(
  duplicados.length === 0,
  `no hay ningún nombre de view-transition duplicado${
    duplicados.length ? ` (${duplicados.map(([n, c]) => `${n} ×${c}`).join(', ')})` : ''
  }`
);

// --- 2. Vigilar las animaciones de la transición -----------------------------
await page.evaluate(() => {
  window.__morph = { visto: false, pseudo: [] };
  const iv = setInterval(() => {
    let animaciones = [];
    try {
      animaciones = document.getAnimations();
    } catch {
      animaciones = [];
    }
    for (const anim of animaciones) {
      const pseudo = anim?.effect?.pseudoElement ?? '';
      if (!pseudo) continue;
      if (!window.__morph.pseudo.includes(pseudo)) window.__morph.pseudo.push(pseudo);
      if (pseudo.includes('poster-')) window.__morph.visto = true;
    }
  }, 20);
  setTimeout(() => clearInterval(iv), 10000);
});

// --- 3. Navegar a la ficha ----------------------------------------------------
// El clic va en el TÍTULO de la tarjeta: es el enlace que el router de Astro
// intercepta. La marca en `window` comprueba que la navegación es de cliente
// (si se recargara la página, la marca desaparecería).
await page.evaluate(() => {
  window.__vivo = 'si';
});

await page
  .locator(`.event-card[data-event-id="${SLUG}"] .event-card__main-link`)
  .first()
  .click();

await page.waitForTimeout(2500);

const estado = await page.evaluate(() => ({
  morph: window.__morph ?? { visto: false, pseudo: [] },
  vivo: window.__vivo ?? null,
  ruta: location.pathname,
}));

ok(
  estado.morph.visto,
  `durante la transición hay una animación del póster (${estado.morph.pseudo
    .filter((p) => p.includes('poster-'))
    .join(', ') || 'ninguna'})`
);
ok(
  estado.ruta.includes(`/fechas/${SLUG}`),
  `la ficha se abrió (${estado.ruta})`
);
ok(estado.vivo === 'si', 'la navegación es de cliente (no hay recarga completa)');

// --- 4. El clic DELEGADO (el que no es un <a>) -------------------------------
// El clic anterior cayó en `.event-card__main-link`, que es un <a> real: lo
// intercepta el router de Astro y NUNCA llega al delegado de `EventCard.astro`
// (que hace `if (target.closest('a')) return`). Si el delegado volviera a
// `window.location.href`, la navegación sería una recarga completa y este test
// seguiría en verde. Por eso se hace un segundo clic sobre la IMAGEN de la
// tarjeta: ahí no hay <a> y sí pasa por el camino nuevo.
await page.goto(URL, { waitUntil: 'networkidle' });
await page.waitForTimeout(1200);

await page.evaluate(() => {
  window.__vivoDelegado = 'si';
});

await page
  .locator(`.event-card[data-event-id="${SLUG}"] .event-card__media img`)
  .first()
  .click({ force: true });

await page.waitForTimeout(2500);

const delegado = await page.evaluate(() => ({
  vivo: window.__vivoDelegado ?? null,
  ruta: location.pathname,
}));

ok(
  delegado.ruta.includes(`/fechas/${SLUG}`),
  `el clic delegado (no un <a>) también abre la ficha (${delegado.ruta})`
);
ok(
  delegado.vivo === 'si',
  'el clic delegado navega con el router de Astro (no recarga la página)'
);

await browser.close();
console.log(fallos.length === 0 ? '\nTodo en verde.' : `\n${fallos.length} comprobación(es) fallida(s).`);
process.exit(fallos.length === 0 ? 0 : 1);
