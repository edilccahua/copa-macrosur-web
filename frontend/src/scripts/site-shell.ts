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
import { navigate } from 'astro:transitions/client';

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
  let currentLabel: string | null = null;

  for (const link of links) {
    const active = matches(pathname, link.dataset.navMatch ?? '');
    link.classList.toggle('is-active', active);
    if (active) {
      link.setAttribute('aria-current', 'page');
      if (!currentLabel) {
        currentLabel = link.dataset.navLabel ?? link.textContent?.trim() ?? null;
      }
    } else {
      link.removeAttribute('aria-current');
    }
  }

  // La MARCA (logo) no se marca nunca: "KÚSPIDE" e "INICIO" llevan a la
  // misma página y el que queda activo es "INICIO".

  // El indicador de sección de la barra (móvil): sólo el nombre, sin
  // descripciones ("INICIO", "FECHAS", "CLASIFICACIONES"…).
  const aqui = document.querySelector<HTMLElement>('[data-nav-current-label]');
  if (aqui) {
    aqui.textContent = currentLabel ?? 'INICIO';
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

/** A partir de aquí el nav de escritorio sustituye al cajón. */
const DESKTOP_BREAKPOINT = 900;

function drawerIsOpen(): boolean {
  return document.getElementById('site-header')?.classList.contains('is-open') ?? false;
}

/**
 * El cajón de navegación.
 *
 * Es SUPERPUESTO al contenido (no lo empuja): el contenido no da ningún salto
 * al abrirlo. Al abrirse, el foco entra en el cajón; al cerrarse, vuelve al
 * botón. Con el teclado, el foco queda atrapado dentro mientras esté abierto.
 */
function setDrawer(open: boolean): void {
  const header = document.getElementById('site-header');
  const button = document.getElementById('nav-toggle');
  if (!header) return;
  if (open === drawerIsOpen()) return;

  header.classList.toggle('is-open', open);
  button?.setAttribute('aria-expanded', String(open));

  if (open) {
    // El foco entra en el cajón. Se aplaza un fotograma porque el cajón
    // acaba de pasar de `visibility: hidden` a visible: sin esperar, el
    // navegador lo sigue considerando oculto y `focus()` no hace nada.
    requestAnimationFrame(() => {
      const first = document.querySelector<HTMLElement>('#nav-panel a');
      first?.focus({ preventScroll: true });
    });
  } else {
    button?.focus({ preventScroll: true });
  }
}

/** Elementos enfocables del cajón, en orden. */
function drawerFocusables(): HTMLElement[] {
  return [
    ...document.querySelectorAll<HTMLElement>('#nav-panel a[href], #nav-panel button:not([disabled])')
  ];
}

/** Mantiene el foco dentro del cajón mientras esté abierto. */
function trapDrawerFocus(event: KeyboardEvent): void {
  if (event.key !== 'Tab' || !drawerIsOpen()) return;
  const focusables = drawerFocusables();
  if (focusables.length === 0) return;

  const first = focusables[0];
  const last = focusables[focusables.length - 1];
  const active = document.activeElement;

  if (event.shiftKey && active === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && active === last) {
    event.preventDefault();
    first.focus();
  }
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
      setDrawer(!drawerIsOpen());
      return;
    }

    // El velo cierra el cajón.
    if (target.closest('#nav-scrim')) {
      setDrawer(false);
      return;
    }

    // Clic fuera: el menú móvil se cierra.
    const header = document.getElementById('site-header');
    if (header?.classList.contains('is-open') && !target.closest('#site-header')) {
      setDrawer(false);
    }

    // Un enlace del cajón: se cierra al navegar.
    if (target.closest('#nav-panel a')) {
      setDrawer(false);
    }

    // Anclas del menú (p.ej. "FECHAS" → /#fechas): el router de Astro no
    // desplaza al ancla, así que se resuelve aquí.
    const anchorLink = target.closest('a[data-nav-anchor]');
    if (anchorLink) {
      const href = anchorLink.getAttribute('href') ?? '';
      const url = new URL(href, window.location.href);
      if (url.hash) {
        event.preventDefault();
        if (url.pathname === window.location.pathname) {
          history.pushState({}, '', url.pathname + url.hash);
          scrollToHash(url.hash);
        } else {
          pendingAnchor = url.hash;
          navigate(url.pathname + url.hash);
        }
      }
    }
  });

  // Escape cierra el cajón; Tab queda atrapado dentro mientras esté abierto.
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      if (drawerIsOpen()) {
        event.preventDefault();
        setDrawer(false);
      }
      return;
    }
    trapDrawerFocus(event);
  });

  // Al pasar a escritorio el cajón se cierra (el nav hace ese papel).
  window.addEventListener('resize', () => {
    if (window.innerWidth >= DESKTOP_BREAKPOINT && drawerIsOpen()) {
      setDrawer(false);
    }
  });

  // El velo se traga la rueda: con el cajón abierto la página no se desplaza
  // por detrás. (El scroll propio del cajón sí funciona.)
  document.addEventListener(
    'wheel',
    (event) => {
      if (drawerIsOpen() && !(event.target as Element | null)?.closest('#nav-panel')) {
        event.preventDefault();
      }
    },
    { passive: false }
  );
}

/**
 * La entrada de la barra se desactiva en cuanto termina.
 *
 * Al navegar, el router reinserta la cabecera persistente en el body nuevo
 * y ESO REINICIA las animaciones CSS del elemento: la barra se borraba y
 * volvía a entrar en cada clic (justo lo que no queremos). Con la clase
 * `is-ready`, la animación ocurre una vez por sesión y nunca más.
 */
function armHeaderIntroOnce(): void {
  const header = document.getElementById('site-header');
  if (!header) return;
  if (header.classList.contains('is-ready')) return;

  const finish = () => header.classList.add('is-ready');

  document.addEventListener(
    'animationend',
    (event) => {
      const target = event.target as Element | null;
      if (target && target.closest('.hdr__bar')) finish();
    },
    { once: false }
  );

  // Red de seguridad: si la animación no llega a terminar ( Reduced motion la
  // deja en 0,01 ms y dispara `animationend`; si el navegador no la soporta,
  // no dispara nada), la cabecera se fija visible equally.
  window.setTimeout(finish, 2000);
}

// ── Anclas dentro de la página ──────────────────────────────────────────────

/**
 * El item "FECHAS" apunta a `/#fechas` (la sección del calendario de la
 * portada). El router de Astro **no resuelve el ancla**: verificado, la ruta
 * cambia pero el scroll se queda en 0 y el fragmento llega a perderse. Por
 * eso el ancla se resuelve aquí, con la API `navigate()` del router:
 *
 *   - si ya estamos en la portada → scroll suave al elemento;
 *   - si no → se navega a la portada y, al terminar, se desplaza al elemento.
 */
let pendingAnchor: string | null = null;

function scrollToHash(hash: string): void {
  const id = hash.replace(/^#/, '');
  if (!id) return;
  const target = document.getElementById(id);
  if (!target) return;

  // El módulo de movimiento expone el desplazamiento para no duplicar la
  // lógica de Lenis.
  const scroll = (window as any).__kuspideScrollTo;
  if (typeof scroll === 'function') {
    scroll(target);
  } else {
    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
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
  // su HTML no se vuelve a pintar. El cajón se cierra: si no, quedaría
  // abierto sobre la página nueva.
  document.addEventListener('astro:before-swap', (event) => {
    const to = (event as Event & { to?: URL }).to;
    const pathname = to?.pathname ?? window.location.pathname;
    applyActiveNav(pathname);
    if (drawerIsOpen()) {
      document.getElementById('site-header')?.classList.remove('is-open');
      document.getElementById('nav-toggle')?.setAttribute('aria-expanded', 'false');
    }
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

    // Si la navegación trajo un ancla (p.ej. "FECHAS" → /#fechas desde otra
    // página), se desplaza al elemento: el router no lo hace.
    const anchor = pendingAnchor ?? window.location.hash;
    if (anchor) {
      pendingAnchor = null;
      // Dos fotogramas: el primero para que el DOM esté montado y el
      // segundo para que las fuentes y las imágenes ya den su altura.
      requestAnimationFrame(() => requestAnimationFrame(() => scrollToHash(anchor)));
    }
  });
}

// ── Arranque ─────────────────────────────────────────────────────────────────

initDelegatedHandlers();
initRouter();
applyActiveNav(window.location.pathname);
restoreTheme();
armHeaderIntroOnce();

// La primera carga de una página de escaparate pide su movimiento.
if (pageWantsMotion()) {
  void ensureMotion().then((mod) => mod?.init());
}
