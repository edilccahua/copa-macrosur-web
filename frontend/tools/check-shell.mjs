/**
 * check-shell.mjs — regresión del SHELL del sitio bajo el router.
 *
 * Comprueba las cuatro cosas que se rompieron alguna vez y que no se
 * pueden volver a romper sin que salte:
 *
 *   1. La navegación es de CLIENTE: no hay recarga completa (una marca en
 *      `window` debe sobrevivir al cambio de página).
 *   2. La cabecera PERSISTE y su animación de entrada NO se repite: al
 *      navegar, la opacidad de la barra no debe caer a 0.
 *   3. El item activo del menú se actualiza al navegar.
 *   4. El conmutador de tema y el menú son CLICABLES en todos los anchos:
 *      el elemento que hay debajo del puntero debe ser el esperado (antes el
 *      regulador lateral se comía los clics del extremo derecho entre 768 y
 *      1171 px).
 *
 * Uso:  node tools/check-shell.mjs [url]
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
await page.waitForTimeout(1500);

// 1 + 2 + 3: navegación de cliente
await page.evaluate(() => {
  window.__marcador = 'vivo';
});

await page.evaluate(() => {
  window.__op = [];
  const iv = setInterval(() => {
    const b = document.querySelector('.hdr__brand');
    if (b) window.__op.push(Number(getComputedStyle(b).opacity));
  }, 60);
  setTimeout(() => clearInterval(iv), 3000);
});

await page.getByRole('link', { name: 'CLASIFICACIONES', exact: true }).first().click();
await page.waitForTimeout(2600);

const estado = await page.evaluate(() => ({
  marcador: window.__marcador,
  ruta: location.pathname,
  activo: [...document.querySelectorAll('.hdr__link.is-active')].map((a) => a.textContent.trim()),
  opacidades: window.__op || []
}));

ok(estado.marcador === 'vivo', 'la navegación es de cliente (no hay recarga completa)');
ok(estado.ruta.includes('ranking-general'), `la ruta cambió a ${estado.ruta}`);
ok(
  estado.activo.includes('CLASIFICACIONES'),
  `el item activo se actualizó (${JSON.stringify(estado.activo)})`
);
const minOp = Math.min(...estado.opacidades);
ok(
  minOp > 0.9,
  `la cabecera no desaparece al navegar (opacidad mínima ${minOp.toFixed(2)})`
);

// 4: el conmutador de tema y el menú son clicables en todos los anchos
// (antes el regulador lateral se comía los clics del extremo derecho)
for (const width of [768, 900, 1024, 1280]) {
  await page.setViewportSize({ width, height: 800 });
  await page.waitForTimeout(350);
  const golpe = await page.evaluate(() => {
    const theme = document.getElementById('theme-toggle');
    const thR = theme.getBoundingClientRect();
    const enTema = document.elementFromPoint(thR.x + thR.width / 2, thR.y + thR.height / 2);
    const links = [...document.querySelectorAll('.hdr__link')];
    const first = links[0].getBoundingClientRect();
    const last = links[links.length - 1].getBoundingClientRect();
    return {
      temaOk: !!(enTema && enTema.closest('#theme-toggle')),
      menuVisible: first.left >= 0 && last.right <= window.innerWidth + 1,
      vw: window.innerWidth
    };
  });
  ok(golpe.menuVisible, `${width}px · el menú completo cabe en la pantalla`);
  ok(golpe.temaOk, `${width}px · el conmutador de tema es clicable`);
}

await browser.close();
console.log(fallos.length === 0 ? '\nTodo en verde.' : `\n${fallos.length} comprobación(es) fallida(s).`);
process.exit(fallos.length === 0 ? 0 : 1);
