/**
 * site-shell.ts — el shell del sitio bajo el router de Astro.
 *
 * Este módulo se carga en TODAS las páginas y es deliberadamente pequeño:
 * no trae GSAP ni Lenis (AGENTS.md §2 los prohíbe en `/en-vivo` y
 * `/admin/juez`). El movimiento pesado se carga bajo demanda, con
 * `import()` dinámico, sólo en las páginas que lo necesitan.
 *
 * De él salen tres cosas:
 *
 *  1. El comportamiento de la cabecera (tema, menú móvil). Va DELEGADO en
 *     `document` a propósito: con el router, la cabecera se recrea al
 *     cambiar de página y un listener atado al elemento se perdería (o, si
 *     el script se re-ejecutara, se duplicaría). Delegar en `document`
 *     resuelve las dos cosas de un tiro: un solo registro, siempre vivo.
 *
 *  2. El estado activo del menú. La cabecera PERSISTE entre navegaciones
 *     (`transition:persist`), así que el HTML del servidor no vuelve a
 *     pintarse: el estado se recalcula en el cliente a partir de la ruta.
 *
 *  3. El ciclo de vida del movimiento: se destruye el de la página que sale
 *     y se arma el de la que entra.
 */

/** Rutas que consideran activo un item del menú. */
function matches(pathname: string, matchList: string): boolean {
  const path = pathname.replace(/\/+$/, '') || '/';
  return matchList
    .split('|')
    .filter(Boolean)
    .some((prefix) =>
      prefix === '/' ? path === '/' : path === prefix || path.startsWith(prefix + '/')
    );
}

/**
 * Recalcula el item activo de la barra y del panel móvil.
 * Se llama en el primer pintado y antes de cada intercambio de página
 * (`astro:before-swap`), para que la pastilla activa ya sea la correcta en
 * el fotograma en que se ve la página nueva.
 */
export function applyActiveNav(pathname: string): void {
  const links = document.querySelectorAll<HTMLElement>('[data-nav-match]');
  for (const link of links) {
    const active = matches(pathname, link.dataset.navMatch ?? '');
    link.classList.toggle('is-active', active);
    if (active) {
      link.setAttribute('aria-current', 'page');
    } else {
      link.removeAttribute('aria-current');
    }
  }

  // La marca (logo) es el equivalente de "Inicio": activa en la portada.
  const brand = document.querySelector<HTMLElement>('.hdr__brand');
  if (brand) {
    if (pathname === '/') brand.setAttribute('aria-current', 'page');
    else brand.removeAttribute('aria-current');
  }
}

// ── Tema ─────────────────────────────────────────────────────────────────────

const THEME_KEY = 'kuspide-theme';

export function readStoredTheme(): 'light' | 'dark' | null {
  try {
    const v = localStorage.getItem(THEME_KEY);
    return v === 'light' || v === 'dark' ? v : null;
  } catch {
    return null;
  }
}

/**
 * El tema EFECTIVO es `data-theme` o, si no hay, la preferencia del sistema.
 * Antes el botón mostraba siempre la luna cuando `data-theme` no estaba
 * puesto, así que con el sistema en oscuro el sitio se veía oscuro pero el
 * icono pedía "ponerse oscuro": el conmutador no cambiaba nada. Ahora
 * `data-theme` SIEMPRE refleja el tema real.
 */
export function effectiveTheme(): 'light' | 'dark' {
  const attr = document.documentElement.getAttribute('data-theme');
  if (attr === 'light' || attr === 'dark') return attr;
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

export function applyTheme(theme: 'light' | 'dark', persist = true): void {
  document.documentElement.setAttribute('data-theme', theme);
  if (persist) {
    try {
      localStorage.setItem(THEME_KEY, theme);
    } catch {
      /* almacenamiento no disponible: el tema dura lo que la página */
    }
  }
}

/** Reaplica el tema tras un intercambio de página (el `<html>` se reemplaza). */
function restoreTheme(): void {
  const stored = readStoredTheme();
  if (stored) {
    document.documentElement.setAttribute('data-theme', stored);
  } else {
    const os = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', os);
  }
}

// ── Comportamiento de la cabecera (delegado) ─────────────────────────────────

function toggleMobileMenu(open: boolean): void {
  const header = document.getElementById('site-header');
  const button = document.getElementById('nav-toggle');
  if (!header) return;
  header.classList.toggle('is-open', open);
  button?.setAttribute('aria-expanded', String(open));
}

function initDelegatedHandlers(): void {
  document.addEventListener('click', (event) => {
    const target = event.target as Element | null;
    if (!target) return;

    // Conmutador de tema.
    const themeButton = target.closest('#theme-toggle');
    if (themeButton) {
      event.preventDefault();
      applyTheme(effectiveTheme() === 'dark' ? 'light' : 'dark');
      return;
    }

    // Botón del menú móvil.
    const navButton = target.closest('#nav-toggle');
    if (navButton) {
      event.preventDefault();
      const header = document.getElementById('site-header');
      toggleMobileMenu(!(header?.classList.contains('is-open') ?? false));
      return;
    }

    // Clic fuera: el menú móvil se cierra.
    const header = document.getElementById('site-header');
    if (header?.classList.contains('is-open') && !target.closest('#site-header')) {
      toggleMobileMenu(false);
    }
  });

  // Escape cierra el menú móvil.
  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    const header = document.getElementById('site-header');
    if (header?.classList.contains('is-open')) {
      toggleMobileMenu(false);
      document.getElementById('nav-toggle')?.focus();
    }
  });
}

// ── Ciclo de vida del movimiento ─────────────────────────────────────────────

type MotionModule = {
  init: () => void;
  teardown: () => void;
};

let motion: MotionModule | null = null;
let motionLoading: Promise<MotionModule | null> | null = null;

/**
 * El módulo de movimiento se carga SÓLO si la página lo pide
 * (`[data-motion-page]`). Así `/en-vivo` y `/admin/juez` nunca descargan GSAP.
 */
async function ensureMotion(): Promise<MotionModule | null> {
  if (motion) return motion;
  if (!document.querySelector('[data-motion-page]')) return null;
  if (!motionLoading) {
    motionLoading = import('./showcase-motion')
      .then((mod) => {
        motion = mod as MotionModule;
        return motion;
      })
      .catch((err) => {
        console.error('No se pudo cargar el módulo de movimiento', err);
        return null;
      });
  }
  return motionLoading;
}

/** ¿La página actual pide movimiento? */
function pageWantsMotion(): boolean {
  return !!document.querySelector('[data-motion-page]');
}

/**
 * En una navegación, los elementos que quedan POR DEBAJO del pliegue se
 * ocultan para que aparezcan al hacer scroll. Los que ya están a la vista
 * NO se ocultan: entran con el fundido de la transición y no hay un
 * fotograma en blanco.
 */
function armBelowTheFoldReveals(): void {
  const limit = window.innerHeight * 0.92;
  const pending = document.querySelectorAll<HTMLElement>('[data-reveal]');
  for (const el of pending) {
    if (el.getBoundingClientRect().top > limit) {
      el.classList.add('is-reveal-pending');
    }
  }
}

/** Red de seguridad: si el movimiento no se pudo cargar, nada queda invisible. */
function releasePendingReveals(): void {
  document.querySelectorAll('.is-reveal-pending').forEach((el) => {
    el.classList.remove('is-reveal-pending');
  });
}

function initRouter(): void {
  // Al salir de una página, se destruye su movimiento (Lenis, ScrollTrigger).
  document.addEventListener('astro:before-preparation', () => {
    motion?.teardown();
  });

  // Antes del intercambio se corrige el item activo: la cabecera persiste y
  // su HTML no se vuelve a pintar.
  document.addEventListener('astro:before-swap', (event) => {
    const to = (event as CustomEvent & { to?: URL }).to;
    const pathname = to?.pathname ?? window.location.pathname;
    applyActiveNav(pathname);
  });

  // Tras el intercambio: el `<html>` es nuevo, así que se repone el tema y
  // se ocultan los elementos que quedan fuera de pantalla.
  document.addEventListener('astro:after-swap', () => {
    restoreTheme();
    if (pageWantsMotion()) armBelowTheFoldReveals();
  });

  // La página ya está en su sitio: se arma el movimiento de esta página.
  document.addEventListener('astro:page-load', async () => {
    restoreTheme();
    applyActiveNav(window.location.pathname);
    if (!pageWantsMotion()) {
      releasePendingReveals();
      return;
    }
    const mod = await ensureMotion();
    if (mod) {
      mod.init();
    } else {
      releasePendingReveals();
    }
  });
}

// ── Arranque ─────────────────────────────────────────────────────────────────

initDelegatedHandlers();
initRouter();
applyActiveNav(window.location.pathname);
restoreTheme();

// La primera carga de una página de escaparate pide su movimiento.
if (pageWantsMotion()) {
  void ensureMotion().then((mod) => mod?.init());
}
