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

/**
 * Transición suave del tema.
 *
 * Sin esto, al cambiar `data-theme` los colores saltan de golpe. Se pone una
 * clase en el `<html>` que fuerza una transición de 420 ms en las propiedades
 * de color, se fuerza el reflow (para que el navegador tome el estado
 * inicial con la transición ya puesta) y se quita la clase al terminar.
 */
function switchTheme(theme: 'light' | 'dark'): void {
  const root = document.documentElement;
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  if (reduce) {
    applyTheme(theme);
    return;
  }

  root.classList.add('theme-switching');
  // Reflow: sin esto el navegador no sabe que hay una transición pendiente.
  void root.offsetHeight;
  applyTheme(theme);

  window.clearTimeout(switchTimer);
  switchTimer = window.setTimeout(() => {
    root.classList.remove('theme-switching');
  }, 460);
}

let switchTimer: number | undefined;

/**
 * Aviso de PRIMERA VISITA: un globo que señala el botón del tema.
 *
 * Sólo aparece una vez en la vida del navegador (queda marcado en
 * `localStorage`) y se retira solo a los 4,5 s. También se retira si el
 * usuario toca el conmutador o hace scroll.
 */
const HINT_KEY = 'kuspide-theme-hint';
const HINT_MS = 4500;

function showThemeHintOnce(): void {
  const hint = document.querySelector<HTMLElement>('[data-theme-hint]');
  if (!hint) return;

  let seen = false;
  try {
    seen = localStorage.getItem(HINT_KEY) === '1';
  } catch {
    seen = false;
  }
  if (seen) return;

  // Se marca ANTES de mostrarlo: si algo falla a medio camino, el aviso no
  // vuelve a aparecer en la siguiente visita.
  try {
    localStorage.setItem(HINT_KEY, '1');
  } catch {
    /* sin almacenamiento: el aviso volverá, pero no rompe nada */
  }

  hint.hidden = false;
  requestAnimationFrame(() => hint.classList.add('is-visible'));

  const hide = () => {
    hint.classList.remove('is-visible');
    window.setTimeout(() => {
      hint.hidden = true;
    }, 320);
  };

  // Sólo el tiempo y el propio conmutador lo retiran. NO se cierra al
  // hacer scroll: al cargar la página hay scrolls programáticos (Lenis,
  // ScrollTrigger, el anclaje del navegador) y el aviso se iba solo al
  // instante, sin que el usuario lo hubiera visto.
  window.setTimeout(hide, HINT_MS);
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

    // Conmutador de tema. El botón ocupa TODA la celda: no hay que
    // apuntarle al icono.
    const themeButton = target.closest('#theme-toggle');
    if (themeButton) {
      event.preventDefault();
      switchTheme(effectiveTheme() === 'dark' ? 'light' : 'dark');
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

    // Anclas del menú (p.ej. "FECHAS" → /#fechas): se resuelven en el
    // manejador de CAPTURA de abajo, antes que el router de Astro.
  });

  /*
    Anclas internas: "FECHAS" → /#fechas, y las del índice de secciones
    (href="#premios").

    POR QUÉ EN FASE DE CAPTURA, Y NO EN BURBUJA
    -------------------------------------------
    El router de Astro (`ClientRouter`) también intercepta los clics en `<a>`
    y, si el evento NO está cancelado, lanza una navegación. Para una ancla
    eso significa re-pedir la página y cambiarla entera: el elemento al que
    queremos ir y la instancia de Lenis desaparecen a mitad del recorrido, y
    el salto nativo del navegador deja el destino bajo la cabecera fija.

    El router sólo se aparta si ve `ev.defaultPrevented` (ClientRouter.astro:
    "ev.defaultPrevented" en la lista de casos en los que no navega). Como
    nuestro manejador estaba en fase de burbuja, se ejecutaba DESPUÉS del
    router: para entonces la navegación ya estaba en marcha, y el
    `preventDefault()` llegaba tarde. Con el manejador en captura, el
    `preventDefault()` va primero y el router se aparta: el ancla se resuelve
    aquí, sin recargar nada.

    POR QUÉ `replaceState` Y NO `pushState`
    ----------------------------------------
    `pushState` con un objeto de estado vacío BORRA el estado que Astro
    guarda en cada entrada del historial (`{ index, scrollX, scrollY }`).
    `index` es lo que Astro usa para saber si el usuario va hacia delante o
    hacia atrás (`onPopState`: `nextIndex > currentHistoryIndex`): al perder
    esa cuenta, el botón "atrás" empieza a clasificar mal las navegaciones y
    el `index` acaba siendo `NaN`. A partir de ahí el router se comporta de
    forma errática y las anclas dejan de funcionar.

    Con `replaceState` la URL refleja la sección (se puede compartir) sin
    crear una entrada nueva ni tocar el estado del router.
  */
  document.addEventListener(
    'click',
    (event) => {
      const target = event.target as Element | null;
      if (!target) return;

      const anchorLink = target.closest('a[data-nav-anchor]');
      if (!anchorLink) return;

      const href = anchorLink.getAttribute('href') ?? '';
      const url = new URL(href, window.location.href);
      if (!url.hash) return;

      event.preventDefault();

      if (url.pathname === window.location.pathname) {
        // Misma página: solo hay que desplazarse. Se conserva el estado que
        // Astro guarda en la entrada (su `index` y su posición guardada).
        history.replaceState(
          { ...(history.state ?? {}) },
          '',
          url.pathname + url.hash,
        );
        scrollToHash(url.hash);
      } else {
        // Otra página: la navega el router y el ancla se aplica al montar.
        pendingAnchor = url.hash;
        navigate(url.pathname + url.hash);
      }
    },
    true,
  );

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

// ── Barra de avance de lectura ───────────────────────────────────────────────

/**
 * Una línea bajo el menú que se llena según lo scrolleado.
 *
 * Sólo se ve donde NO hay regulador lateral (por debajo de 48em): en
 * escritorio el regulador lateral ya dice en qué parte de la página estás, y
 * en el móvil no hay ninguna otra indicación.
 */
let progressEl: HTMLElement | null = null;
let progressFrame = 0;

function updateReadingProgress(): void {
  progressFrame = 0;
  if (!progressEl) {
    progressEl = document.querySelector<HTMLElement>('[data-read-progress]');
  }
  if (!progressEl) return;

  const max = document.documentElement.scrollHeight - window.innerHeight;
  const ratio = max > 0 ? Math.min(1, Math.max(0, window.scrollY / max)) : 0;
  progressEl.style.transform = `scaleX(${ratio})`;
}

/** Las escrituras se agrupan en un fotograma. */
function scheduleReadingProgress(): void {
  if (progressFrame) return;
  progressFrame = requestAnimationFrame(updateReadingProgress);
}

// ── Ciclo de vida del movimiento ─────────────────────────────────────────────

type MotionModule = {
  init: () => void;
  teardown: () => void;
};

type RulerModule = {
  initPageRuler: () => void;
  destroyPageRuler: () => void;
};

let motion: MotionModule | null = null;
let motionLoading: Promise<MotionModule | null> | null = null;
let ruler: RulerModule | null = null;
let rulerLoading: Promise<RulerModule | null> | null = null;

/**
 * El regulador de scroll vive en `page-ruler.ts`, que no arrastra GSAP ni
 * Lenis: así está en TODAS las páginas (incluidas las de datos) sin que
 * `/en-vivo` ni `/admin/juez` descarguen las librerías pesadas.
 */
async function ensureRuler(): Promise<RulerModule | null> {
  if (ruler) return ruler;
  if (!document.querySelector('[data-ruler]')) return null;
  if (!rulerLoading) {
    rulerLoading = import('./page-ruler')
      .then((mod) => {
        ruler = mod as RulerModule;
        return ruler;
      })
      .catch((err) => {
        console.error('No se pudo cargar el regulador de scroll', err);
        return null;
      });
  }
  return rulerLoading;
}

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
  // Al salir de una página, se destruye su movimiento (Lenis, ScrollTrigger)
  // y su regulador: el <body> se reemplaza y la regleta nueva es otro
  // elemento (si no se desmontara, los listeners de scroll se acumularían).
  document.addEventListener('astro:before-preparation', () => {
    motion?.teardown();
    ruler?.destroyPageRuler();
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
    // La barra de avance se recalcula: al navegar, el scroll vuelve arriba.
    scheduleReadingProgress();

    // El regulador de scroll está en todas las páginas.
    const rul = await ensureRuler();
    rul?.initPageRuler();

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
showThemeHintOnce();

// Barra de avance de lectura: en todas las páginas.
window.addEventListener('scroll', scheduleReadingProgress, { passive: true });
window.addEventListener('resize', scheduleReadingProgress);
scheduleReadingProgress();

// La primera carga de una página de escaparate pide su movimiento.
if (pageWantsMotion()) {
  void ensureMotion().then((mod) => mod?.init());
}

// El regulador de scroll: en todas las páginas.
void ensureRuler().then((mod) => mod?.initPageRuler());
