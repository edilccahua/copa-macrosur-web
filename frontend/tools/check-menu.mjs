/**
 * check-menu.mjs — regresión del MENÚ del sitio.
 *
 * Comprueba lo que el menú tiene que cumplir:
 *   1. Los items son los del diseño: INICIO, FECHAS, CLASIFICACIONES,
 *      ESPECIALES y PREMIOS. Ni "Campeonato" (duplicaba el logo), ni
 *      "Inscripciones" (el CTA salía duplicado) ni el icono del juez.
 *   2. El menú está CENTRADO: el espacio a la izquierda del primer item y
 *      el de la derecha del último son iguales.
 *   3. El item activo es el correcto en cada ruta, y la MARCA (logo)
 *      nunca se marca: "KÚSPIDE" e "INICIO" llevan a la misma página pero
 *      el que queda activo es "INICIO".
 *   4. "FECHAS" lleva al calendario de la portada Y el scroll llega: el
 *      router de Astro no resuelve el ancla, lo hace el shell.
 *
 * Uso:  node tools/check-menu.mjs [url]
 */
import { chromium } from 'playwright-core';

const URL = process.argv[2] ?? 'http://127.0.0.1:4323/';
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
await page.waitForTimeout(1200);

// 1. Los items del menú
const items = await page.$$eval('.hdr__link', (as) => as.map((a) => a.textContent.trim()));
ok(
  JSON.stringify(items) === JSON.stringify(['INICIO', 'FECHAS', 'CLASIFICACIONES', 'ESPECIALES', 'PREMIOS']),
  `los items del menú son los del diseño (${JSON.stringify(items)})`
);
ok(!items.includes('INSCRIPCIÓN'), 'no hay CTA INSCRIPCIÓN en la barra');
ok(
  (await page.$('a[href*="admin/juez"]')) === null,
  'no hay ningún enlace al panel del juez en la cabecera'
);
ok(
  (await page.$('.hdr__panel-link[href*="admin/juez"]')) === null,
  'no hay ningún enlace al panel del juez en el panel móvil'
);

// 1b. El menú va PEGADO a la marca, como en getartcraft.com (no centrado)
const medidas = await page.evaluate(() => {
  const links = [...document.querySelectorAll('.hdr__link')];
  const first = links[0].getBoundingClientRect();
  const last = links[links.length - 1].getBoundingClientRect();
  const brand = document.querySelector('.hdr__brand').getBoundingClientRect();
  const right = document.querySelector('.hdr__right').getBoundingClientRect();
  return {
    pegado: Math.round(first.left - brand.right),
    huecoDerecha: Math.round(right.left - last.right)
  };
});
ok(
  medidas.pegado <= 24,
  `el menú arranca pegado a la marca (${medidas.pegado} px de separación)`
);
ok(
  medidas.huecoDerecha > 120,
  `el hueco grande queda a la derecha, como en la referencia (${medidas.huecoDerecha} px)`
);

// 2. La pastilla va sobre el TEXTO, no sobre la celda entera
// (como en getartcraft.com: un span con px-1.5 py-0.5 dentro del enlace),
// y el puntero muestra la MISMA pastilla invertida que el activo.
const pastilla = await page.evaluate(() => {
  const links = [...document.querySelectorAll('.hdr__link')];
  const activo = links.find((a) => a.classList.contains('is-active'));
  const chip = activo?.querySelector('.hdr__label');
  const celda = activo?.getBoundingClientRect();
  const chips = links.map((a) => a.querySelector('.hdr__label').getBoundingClientRect());
  let hueco = 0;
  for (let i = 1; i < chips.length; i++) {
    hueco = Math.max(hueco, Math.round(chips[i].left - chips[i - 1].right));
  }
  return {
    chipH: chip ? Math.round(chip.getBoundingClientRect().height) : 0,
    celdaH: celda ? Math.round(celda.height) : 0,
    chipW: chip ? Math.round(chip.getBoundingClientRect().width) : 0,
    celdaW: celda ? Math.round(celda.width) : 0,
    hueco
  };
});
ok(
  pastilla.chipH > 0 && pastilla.chipH < pastilla.celdaH,
  `la pastilla NO ocupa toda la celda (${pastilla.chipH}px de ${pastilla.celdaH}px)`
);
ok(
  pastilla.chipW < pastilla.celdaW,
  `la pastilla deja aire a los lados (${pastilla.chipW}px de ${pastilla.celdaW}px)`
);
ok(
  pastilla.hueco >= 20,
  `hay espacio entre los items (${pastilla.hueco}px entre pastillas; la referencia: 20px)`
);

// 2b. El puntero muestra la pastilla invertida, no sólo un cambio de color
const sinPuntero = await page.evaluate(() => {
  const links = [...document.querySelectorAll('.hdr__link')];
  const inactivo = links.find((a) => !a.classList.contains('is-active'));
  return getComputedStyle(inactivo.querySelector('.hdr__label')).backgroundColor;
});
ok(
  sinPuntero === 'rgba(0, 0, 0, 0)',
  `sin puntero, el item inactivo no tiene pastilla (${sinPuntero})`
);

const donde = await page.evaluate(() => {
  const links = [...document.querySelectorAll('.hdr__link')];
  const inactivo = links.find((a) => !a.classList.contains('is-active'));
  const r = inactivo.getBoundingClientRect();
  return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
});
await page.mouse.move(donde.x, donde.y);
await page.waitForTimeout(350);
const conPuntero = await page.evaluate(() => {
  const links = [...document.querySelectorAll('.hdr__link')];
  const sobre = links.find((a) => a.matches(':hover'));
  if (!sobre) return null;
  const chip = sobre.querySelector('.hdr__label');
  return { bg: getComputedStyle(chip).backgroundColor, color: getComputedStyle(chip).color };
});
ok(
  conPuntero !== null && conPuntero.bg !== 'rgba(0, 0, 0, 0)',
  `el puntero muestra la pastilla invertida (${conPuntero ? conPuntero.bg : 'sin hover'})`
);
await page.mouse.move(0, 400);
await page.waitForTimeout(250);

// 3. El item activo por ruta
const rutas = [
  ['/', 'INICIO'],
  ['/fechas/la-joya-extreme', 'FECHAS'],
  ['/ranking-general', 'CLASIFICACIONES'],
  ['/corredor/cualquiera', 'CLASIFICACIONES'],
  ['/equipos/cualquiera', 'CLASIFICACIONES'],
  ['/eventos-especiales', 'ESPECIALES'],
  ['/premios', 'PREMIOS']
];
for (const [ruta, esperado] of rutas) {
  await page.goto(URL.replace(/\/$/, '') + ruta, { waitUntil: 'networkidle' });
  await page.waitForTimeout(700);
  const activo = await page.$$eval('.hdr__link.is-active', (as) => as.map((a) => a.textContent.trim()));
  ok(
    activo.length === 1 && activo[0] === esperado,
    `${ruta} → activo "${esperado}" (${JSON.stringify(activo)})`
  );
  const marca = await page.$eval('.hdr__brand', (a) => a.getAttribute('aria-current'));
  ok(marca === null, `${ruta} → la marca (logo) no se marca`);
}

// 4. "FECHAS" lleva al calendario Y hace scroll
await page.goto(URL.replace(/\/$/, '') + '/ranking-general', { waitUntil: 'networkidle' });
await page.waitForTimeout(900);
await page.getByRole('link', { name: 'FECHAS', exact: true }).first().click();
await page.waitForTimeout(2500);
const tras = await page.evaluate(() => {
  const el = document.getElementById('fechas');
  return {
    path: location.pathname,
    scrollY: Math.round(window.scrollY),
    calendarioY: el ? Math.round(el.getBoundingClientRect().top) : -999
  };
});
ok(tras.path === '/', `FECHAS lleva a la portada (${tras.path})`);
ok(
  tras.scrollY > 100 && tras.calendarioY > -50 && tras.calendarioY < 120,
  `FECHAS desplaza al calendario (scrollY=${tras.scrollY}, calendario a ${tras.calendarioY}px)`
);

// 5. Móvil: cajón superpuesto, con la página actual marcada
const movil = await browser.newPage({ viewport: { width: 390, height: 780 }, isMobile: true, hasTouch: true });
await movil.goto(URL.replace(/\/$/, '') + '/ranking-general', { waitUntil: 'networkidle' });
await movil.waitForTimeout(900);

ok(
  (await movil.$eval('.hdr__nav', (n) => getComputedStyle(n).display)) === 'none',
  'en móvil el nav de escritorio está oculto'
);
ok(await movil.isVisible('#nav-toggle'), 'en móvil se ve el botón del menú');

const antesDeAbrir = await movil.evaluate(() => ({
  scrollY: Math.round(window.scrollY),
  topContenido: Math.round(document.querySelector('main')?.getBoundingClientRect().top ?? 0)
}));

await movil.click('#nav-toggle');
await movil.waitForTimeout(600);

const abierto = await movil.evaluate(() => {
  const drawer = document.getElementById('nav-panel');
  const cs = drawer ? getComputedStyle(drawer) : null;
  const activo = drawer?.querySelector('.hdr__drawer-link.is-active');
  return {
    visible: cs ? cs.visibility === 'visible' && Number(cs.opacity) > 0.9 : false,
    posicion: cs?.position,
    items: drawer ? [...drawer.querySelectorAll('.hdr__drawer-link')].map((a) => a.textContent.trim()) : [],
    activo: activo?.textContent.trim() ?? null,
    actual: document.querySelector('[data-nav-current] strong')?.textContent.trim() ?? null,
    focoDentro: !!document.querySelector('#nav-panel')?.contains(document.activeElement),
    topContenido: Math.round(document.querySelector('main')?.getBoundingClientRect().top ?? 0)
  };
});
ok(abierto.visible, 'el cajón se abre (visible)');
ok(abierto.posicion === 'fixed', 'el cajón es superpuesto (fixed), no empuja la página');
ok(
  abierto.topContenido === antesDeAbrir.topContenido,
  'abrir el cajón NO desplaza el contenido'
);
ok(
  JSON.stringify(abierto.items) ===
    JSON.stringify(['INICIO', 'FECHAS', 'CLASIFICACIONES', 'ESPECIALES', 'PREMIOS']),
  `el cajón tiene los destinos (${JSON.stringify(abierto.items)})`
);
ok(abierto.activo === 'CLASIFICACIONES', `el cajón marca la página actual (${abierto.activo})`);
ok(abierto.actual === 'CLASIFICACIONES', `el cajón dice en qué página estamos (${abierto.actual})`);
ok(abierto.focoDentro, 'al abrir, el foco entra en el cajón');

await movil.keyboard.press('Escape');
await movil.waitForTimeout(400);
ok(
  !(await movil.evaluate(() => document.getElementById('site-header')?.classList.contains('is-open'))),
  'Escape cierra el cajón'
);

await browser.close();
console.log(fallos.length === 0 ? '\nTodo en verde.' : `\n${fallos.length} comprobación(es) fallida(s).`);
process.exit(fallos.length === 0 ? 0 : 1);
