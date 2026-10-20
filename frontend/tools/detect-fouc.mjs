/**
 * detect-fouc.mjs — ¿el contenido se pinta visible ANTES de que el CSS lo
 * oculte?
 *
 * La hipótesis que hay que refutar: el estado inicial de las animaciones lo
 * aplica JavaScript DESPUÉS del primer pintado, de modo que durante uno o
 * más fotogramas el usuario ve la página completa y de golpe las tarjetas
 * desaparecen y saltan 28px. Eso era el "carga completo al milisegundo y
 * se apila raro".
 *
 * Cómo: instalamos un bucle de rAF ANTES de que exista la página, que
 * registra la opacidad de los elementos revelados desde el primerísimo
 * fotograma. Si alguno se ve (opacidad > 0) ANTES de que el CSS lo oculte,
 * hay destello.
 *
 * Uso:  node tools/detect-fouc.mjs [url]
 */
import { chromium } from 'playwright-core';

const URL = process.argv[2] ?? 'http://127.0.0.1:4323/';
const CHROME = process.env.CHROME_PATH ?? '/usr/bin/google-chrome-stable';

const browser = await chromium.launch({
  executablePath: CHROME,
  args: ['--no-sandbox', '--disable-gpu', '--hide-scrollbars'],
});

const context = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  colorScheme: 'light',
});
const page = await context.newPage();

// Se ejecuta antes que cualquier script de la página.
await page.addInitScript(() => {
  window.__trace = [];
  const t0 = performance.now();
  const record = () => {
    const els = document.querySelectorAll('[data-reveal], [data-draw-eyebrow]');
    for (const el of els) {
      const cs = getComputedStyle(el);
      window.__trace.push({
        t: Math.round(performance.now() - t0),
        op: Number(cs.opacity),
        vis: cs.visibility,
        cls: (el.className || '').toString().slice(0, 30)
      });
    }
    if (window.__trace.length > 4000) return;
    requestAnimationFrame(record);
  };
  requestAnimationFrame(record);
});

await page.goto(URL, { waitUntil: 'networkidle' });
await page.waitForTimeout(1200);

const trace = await page.evaluate(() => window.__trace || []);

// Un elemento cuenta como "destello" si se ve en algún fotograma y luego
// desaparece (opacidad 0) — es el patrón del salto.
const porElemento = new Map();
for (const row of trace) {
  const key = row.t + '|' + row.cls;
  if (!porElemento.has(row.cls)) porElemento.set(row.cls, []);
  porElemento.get(row.cls).push(row);
}

let destellos = 0;
const ejemplos = [];
for (const [cls, rows] of porElemento) {
  let visto = false;
  for (const r of rows) {
    if (r.op > 0.05 && r.vis !== 'hidden') {
      visto = true;
    } else if (visto && r.op <= 0.05) {
      destellos++;
      if (ejemplos.length < 5) ejemplos.push({ cls, t: r.t, op: r.op });
      break;
    }
  }
}

console.log(`URL: ${URL}`);
console.log(`muestras: ${trace.length} · elementos: ${porElemento.size}`);
if (destellos === 0) {
  console.log('OK — sin destello: ningún elemento se pintó visible antes de ocultarse.');
} else {
  console.log(`FALLO — ${destellos} elemento(s) se pintaron visibles y luego se ocultaron:`);
  for (const e of ejemplos) console.log('   ', e);
}

await browser.close();
process.exit(destellos === 0 ? 0 : 1);
