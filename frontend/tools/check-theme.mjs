/**
 * check-theme.mjs — regresión del conmutador de tema.
 *
 * Comprueba cuatro cosas:
 *   1. El área CLICABLE es toda la celda del conmutador, no sólo el icono:
 *      hay que poder cambiar el tema apuntando al recuadro.
 *   2. En la PRIMERA visita aparece un aviso que señala el botón, cabe en
 *      pantalla y se retira solo a los ~4,5 s.
 *   3. El aviso NO vuelve a aparecer nunca (queda marcado en localStorage).
 *   4. El cambio de tema es SUAVE: se pone la clase `theme-switching` y los
 *      colores se interpolan en vez de saltar.
 *
 * Uso:  node tools/check-theme.mjs [url]
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

// ── 1. El aviso de primera visita ────────────────────────────────────────────
const primera = await browser.newContext({ viewport: { width: 1280, height: 800 } });
const p1 = await primera.newPage();
await p1.goto(URL, { waitUntil: 'networkidle' });
await p1.waitForTimeout(1200);

const aviso = await p1.evaluate(() => {
  const hint = document.querySelector('[data-theme-hint]');
  const btn = document.getElementById('theme-toggle');
  const celda = btn.closest('.hdr__cell');
  const hr = hint.getBoundingClientRect();
  const br = btn.getBoundingClientRect();
  const cr = celda.getBoundingClientRect();
  return {
    visible: !hint.hidden && Number(getComputedStyle(hint).opacity) > 0.9,
    dentro: hr.left >= 0 && hr.right <= window.innerWidth,
    ancho: Math.round(hr.width),
    // La flecha del globo tiene que caer sobre el icono: está a 16 px del
    // borde derecho del globo (5 px del centro de la flecha), y el icono va
    // en el centro del botón.
    flechaSobreIcono:
      Math.abs(hr.right - 21 - (br.x + br.width / 2)) < 4,
    // El botón tiene que ocupar la celda entera.
    botonOcupaCelda:
      Math.abs(br.width - cr.width) < 2 && Math.abs(br.height - cr.height) < 2,
    marcado: localStorage.getItem('kuspide-theme-hint')
  };
});
ok(aviso.visible, 'el aviso de primera visita aparece');
ok(aviso.dentro, 'el aviso cabe entero en la pantalla');
ok(aviso.flechaSobreIcono, 'la flecha del aviso apunta al icono');
ok(aviso.botonOcupaCelda, 'el botón del tema ocupa TODA la celda (área clicable)');
ok(aviso.marcado === '1', 'la visita queda registrada (no vuelve a salir)');

// ── 2. El aviso desaparece solo ─────────────────────────────────────────────
await p1.waitForTimeout(4200);
ok(
  await p1.evaluate(() => {
    const h = document.querySelector('[data-theme-hint]');
    return h.hidden || Number(getComputedStyle(h).opacity) < 0.1;
  }),
  'el aviso se retira solo a los ~4,5 s'
);

// ── 3. Segunda visita: no aparece ───────────────────────────────────────────
// En el MISMO contexto (la misma "sesión del navegador"): recargar la página
// es lo que hace el usuario al volver al sitio.
await p1.goto(URL, { waitUntil: 'networkidle' });
await p1.waitForTimeout(1200);
ok(
  await p1.evaluate(() => {
    const h = document.querySelector('[data-theme-hint]');
    return h.hidden || Number(getComputedStyle(h).opacity) < 0.1;
  }),
  'en la segunda visita el aviso NO aparece'
);

// ── 4. El cambio de tema es suave y funciona desde cualquier punto de la celda
await p1.evaluate(() => {
  window.__temas = [];
  const observer = new MutationObserver(() => {
    window.__temas.push(document.documentElement.getAttribute('data-theme'));
  });
  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ['data-theme', 'class']
  });
  window.__clase = () => document.documentElement.classList.contains('theme-switching');
});

// Se hace clic en el BORDE de la celda, no sobre el icono.
const borde = await p1.evaluate(() => {
  const r = document.getElementById('theme-toggle').getBoundingClientRect();
  return { x: Math.round(r.x + 5), y: Math.round(r.y + r.height / 2) };
});
const antes = await p1.evaluate(() => document.documentElement.getAttribute('data-theme'));
await p1.mouse.click(borde.x, borde.y);
await p1.waitForTimeout(120);

const durante = await p1.evaluate(() => ({
  clase: document.documentElement.classList.contains('theme-switching'),
  tema: document.documentElement.getAttribute('data-theme')
}));
ok(durante.clase, 'el cambio de tema activa la transición (clase theme-switching)');
ok(durante.tema !== antes, `el tema cambia (${antes} → ${durante.tema})`);

await p1.waitForTimeout(600);
ok(
  await p1.evaluate(() => !document.documentElement.classList.contains('theme-switching')),
  'la clase de transición se retira al terminar'
);

// ── 5. El tema del dispositivo se respeta ───────────────────────────────────
const oscuro = await browser.newContext({
  viewport: { width: 1280, height: 800 },
  colorScheme: 'dark'
});
const p3 = await oscuro.newPage();
await p3.goto(URL, { waitUntil: 'networkidle' });
await p3.waitForTimeout(900);
const temaOscurp = await p3.evaluate(() => ({
  attr: document.documentElement.getAttribute('data-theme'),
  fondo: getComputedStyle(document.body).backgroundColor,
  luna: getComputedStyle(document.querySelector('.i-moon')).display,
  sol: getComputedStyle(document.querySelector('.i-sun')).display
}));
ok(temaOscurp.attr === 'dark', 'sin preferencia guardada, se respeta el tema del dispositivo (oscuro)');
ok(temaOscurp.sol === 'block' && temaOscurp.luna === 'none', 'el icono refleja el tema real');
await oscuro.close();

// ── 6. Los cortes de la barra: el indicador es sólo de móvil ────────────────
for (const [w, h] of [[1280, 800], [390, 780]]) {
  const c = await browser.newContext({ viewport: { width: w, height: h }, isMobile: w < 500 });
  const q = await c.newPage();
  await q.goto(URL, { waitUntil: 'networkidle' });
  await q.waitForTimeout(900);
  const d = await q.evaluate(() => ({
    indicador: getComputedStyle(document.querySelector('.hdr__here')).display,
    nav: getComputedStyle(document.querySelector('.hdr__nav')).display,
    whatsapp: getComputedStyle(document.querySelector('.hdr__cell--hide-sm')).display
  }));
  if (w >= 900) {
    ok(d.indicador === 'none', `${w}px · el indicador de sección está oculto (es de móvil)`);
    ok(d.nav === 'flex', `${w}px · el nav se ve`);
    ok(d.whatsapp === 'flex', `${w}px · el contacto de WhatsApp se ve`);
  } else {
    ok(d.indicador === 'flex', `${w}px · el indicador de sección se ve`);
    ok(d.nav === 'none', `${w}px · el nav se oculta`);
    ok(d.whatsapp === 'none', `${w}px · el contacto de WhatsApp se oculta`);
  }
  await c.close();
}

await primera.close();
await browser.close();
console.log(fallos.length === 0 ? '\nTodo en verde.' : `\n${fallos.length} comprobación(es) fallida(s).`);
process.exit(fallos.length === 0 ? 0 : 1);
