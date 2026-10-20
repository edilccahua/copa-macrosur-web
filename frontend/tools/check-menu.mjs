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

// 2. El menú está centrado
const medidas = await page.evaluate(() => {
  const links = [...document.querySelectorAll('.hdr__link')];
  const first = links[0].getBoundingClientRect();
  const last = links[links.length - 1].getBoundingClientRect();
  const brand = document.querySelector('.hdr__brand').getBoundingClientRect();
  const right = document.querySelector('.hdr__right').getBoundingClientRect();
  return {
    izq: Math.round(first.left - brand.right),
    der: Math.round(right.left - last.right)
  };
});
ok(
  Math.abs(medidas.izq - medidas.der) <= 2,
  `el menú está centrado (${medidas.izq} px a la izquierda, ${medidas.der} a la derecha)`
);

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

await browser.close();
console.log(fallos.length === 0 ? '\nTodo en verde.' : `\n${fallos.length} comprobación(es) fallida(s).`);
process.exit(fallos.length === 0 ? 0 : 1);
