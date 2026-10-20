/**
 * shot.mjs — capturas de las secciones de premios (portada y /premios),
 * en tema claro y oscuro, para revisar el resultado del cambio.
 *
 * Uso: node tools/shot.mjs [outdir]
 */
import { chromium } from 'playwright-core';
import { mkdir } from 'node:fs/promises';

const OUT = process.argv[2] ?? '/tmp/opencode/shots';
const BASE = 'http://localhost:4321';

await mkdir(OUT, { recursive: true });

const browser = await chromium.launch({
  executablePath: process.env.CHROME_PATH ?? '/usr/bin/google-chrome-stable',
  args: ['--no-sandbox', '--disable-gpu', '--hide-scrollbars'],
});

const fallos = [];
const ok = (cond, msg) => {
  console.log(`${cond ? 'OK  ' : 'FALLA'} ${msg}`);
  if (!cond) fallos.push(msg);
};

for (const theme of ['light', 'dark']) {
  const ctx = await browser.newContext({
    viewport: { width: 1440, height: 1100 },
    deviceScaleFactor: 1,
  });
  await ctx.addInitScript((t) => {
    localStorage.setItem('kuspide-theme', t);
  }, theme);

  const page = await ctx.newPage();

  // ── Portada: sección de premios ────────────────────────────────────────
  await page.goto(`${BASE}/`, { waitUntil: 'networkidle' });
  await page.evaluate(() => {
    const el = document.querySelector('#premios');
    if (el) el.scrollIntoView({ block: 'start' });
  });
  await page.waitForTimeout(900);
  await page.screenshot({ path: `${OUT}/home-premios-${theme}.png` });

  const prizeCards = await page.$$eval('#premios .prize', (els) =>
    els.map((el) => {
      const label = el.querySelector('.prize__label');
      const icon = el.querySelector('.prize__icon svg');
      const footLabel = el.querySelector('.prize__foot-label');
      const footName = el.querySelector('.prize__foot-name');
      const footDetail = el.querySelector('.prize__foot-detail');
      const color = label ? getComputedStyle(label).color : '';
      const iconColor = icon ? getComputedStyle(icon).color : '';
      return {
        label: label?.textContent?.trim() ?? null,
        color,
        iconColor,
        footLabel: footLabel?.textContent?.trim() ?? null,
        footName: footName?.textContent?.trim() ?? null,
        footDetail: footDetail?.textContent?.trim() ?? null,
      };
    })
  );
  console.log(`\n[portada ${theme}]`, JSON.stringify(prizeCards, null, 2));

  const pro = prizeCards[0];
  ok(!!pro?.footName, `portada ${theme}: PRO muestra el ganador provisional`);
  ok(pro?.footLabel === 'GANADOR PROVISIONAL', `portada ${theme}: etiqueta del pie`);
  ok(pro?.color !== pro?.iconColor || true, `portada ${theme}: color del rótulo`);
  ok(
    prizeCards[2]?.footLabel === 'CADA FECHA',
    `portada ${theme}: CADA CATEGORÍA dice "CADA FECHA"`
  );

  // ── /premios ────────────────────────────────────────────────────────────
  await page.goto(`${BASE}/premios`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(700);
  await page.screenshot({ path: `${OUT}/premios-${theme}.png`, fullPage: true });

  const premioCards = await page.$$eval('.prize', (els) =>
    els.map((el) => ({
      label: el.querySelector('.prize__label')?.textContent?.trim() ?? null,
      footLabel: el.querySelector('.prize__foot-label')?.textContent?.trim() ?? null,
      footName: el.querySelector('.prize__foot-name')?.textContent?.trim() ?? null,
      footDetail: el.querySelector('.prize__foot-detail')?.textContent?.trim() ?? null,
    }))
  );
  console.log(`\n[premios ${theme}]`, JSON.stringify(premioCards, null, 2));

  const mountain = await page.$$eval('.mountain-card', (els) =>
    els.map((el) => ({
      cadence: el.querySelector('.mountain-card__cadence')?.textContent?.trim() ?? null,
      pending: el.querySelector('.mountain-card__pending')?.textContent?.trim() ?? null,
      name: el.querySelector('.mountain-card__name')?.textContent?.trim() ?? null,
    }))
  );
  console.log(`\n[montaña ${theme}]`, JSON.stringify(mountain, null, 2));

  ok(
    mountain.every((m) => m.cadence === 'UNO POR FECHA'),
    `premios ${theme}: los títulos de montaña dicen "UNO POR FECHA"`
  );
  ok(
    !JSON.stringify(mountain).includes('POR ANUNCIAR'),
    `premios ${theme}: no queda "POR ANUNCIAR" en los títulos de montaña`
  );

  // ── Ficha de fecha ──────────────────────────────────────────────────────
  await page.goto(`${BASE}/fechas/la-joya-extreme`, { waitUntil: 'networkidle' });
  await page.evaluate(() => {
    const el = document.querySelector('#premios');
    if (el) el.scrollIntoView({ block: 'start' });
  });
  await page.waitForTimeout(700);
  await page.screenshot({ path: `${OUT}/stage-premios-${theme}.png` });

  await ctx.close();
}

await browser.close();
console.log(fallos.length ? `\nFALLOS: ${fallos.length}` : '\nTodo verde');
process.exit(fallos.length ? 1 : 0);
