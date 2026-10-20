/**
 * showcase-motion.ts — movimiento del escaparate.
 *
 * Los parámetros NO están inventados: se extrajeron del bundle del original.
 * Los nombres de easing y los números sobreviven a la minificación.
 *
 *   Lenis           new Lenis({ lerp: 0.25, anchors: true })
 *   Revelado        from { autoAlpha: 0, y: 28, filter: "blur(8px)" }
 *                   to   { autoAlpha: 1, y: 0,  filter: "blur(0px)",
 *                          duration: 0.9, ease: "power3.out", clearProps: "all" }
 *   Trazo           scaleX 0 -> 1, duration 0.7, ease "power2.out"
 *   Celdas          scale 0 -> 1 y opacity 0 -> 1, duration 0.35
 *   Disparador      ScrollTrigger start "top 88%", once: true
 *   Cascada         delay = (x del elemento dentro de su padre) * 0.18
 *
 * Límites que impone AGENTS.md:
 *   - esto se importa ÚNICAMENTE desde el layout de escaparate, y con
 *     `import()` dinámico: `/en-vivo` y `/admin/juez` no lo descargan;
 *   - con `prefers-reduced-motion: reduce` no se inicializa nada y las clases
 *     quedan visibles (el CSS nunca las oculta).
 *
 * CICLO DE VIDA: este módulo exporta `init()` y `teardown()`. Con el router
 * de Astro el movimiento se rearma en cada página: `init()` destruye lo que
 * hubiera (por si acaso) y monta el de la página actual; `teardown()` se
 * llama al salir de la página.
 */
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import Lenis from 'lenis';
// La hoja de Lenis es OBLIGATORIA: sin ella `html.lenis` no recibe `height: auto`
// y el navegador conserva su propio scroll suave, que compite con Lenis.
import 'lenis/dist/lenis.css';

gsap.registerPlugin(ScrollTrigger);

/** Revelado, tal como está en el original. */
const REVEAL_FROM = { autoAlpha: 0, y: 28, filter: 'blur(8px)' };
const REVEAL_TO = {
  autoAlpha: 1,
  y: 0,
  filter: 'blur(0px)',
  duration: 0.9,
  ease: 'power3.out',
  overwrite: true,
  // El original usa `clearProps: "all"`, pero eso borra el atributo `style`
  // COMPLETO, no sólo lo que animó GSAP. Listamos las propiedades animadas para
  // que nunca pueda llevarse por delante estilos ajenos.
  clearProps: 'opacity,visibility,transform,filter',
};

/** Máximo retardo de la cascada horizontal, medido. */
const CASCADE_MAX = 0.18;

/**
 * Tiempos de la entrada del hero, extraídos del `introTuner` del original:
 *   instrAt 0.70 → el nav entra en cascada
 *   wordAt  0.35 → el rótulo empieza a formarse
 *   wordDur 0.85 → duración de la formación de la palabra
 *   copyAt  1.05 → el titular y el texto se revelan
 *
 * **AJUSTADOS (20-Oct-2026).** Con los tiempos del original el hero se
 * quedaba en blanco demasiado: el contenido está oculto desde el primer
 * pintado (para que no haya destello) y la intro no empezaba hasta un segundo
 * después de que cargara el módulo. Medido: 2,4 s hasta que se veía el
 * último texto. Con estos valores el hero está completo en ~1,3 s y la
 * entrada sigue siendo una cascada (el rótulo se forma y el texto sale
 * detrás), no un salto seco.
 */
const INTRO = {
  wordAt: 0.12,
  wordDur: 0.7,
  copyAt: 0.5,
};

/** Separación extra con la que arrancan las letras del rótulo, en px. */
const WORD_SPREAD = 70;

const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

declare global {
  interface Window {
    /** El módulo avisa que arrancó; el seguro del <head> lo consulta. */
    __motionReady?: boolean;
  }
}

// ── Estado del módulo ───────────────────────────────────────────────────────

let lenisInstance: Lenis | null = null;
let triggers: ScrollTrigger[] = [];

/**
 * Desplaza hasta un elemento, dejando la cabecera pegada arriba.
 * Lo expone el shell (`window.__kuspideScrollTo`) para resolver las anclas
 * del menú: el router de Astro no desplaza al ancla.
 */
function scrollToElement(target: Element): void {
  // El alto de la cabecera se MIDE (cambia con el breakpoint) en vez de
  // leer el token: `getPropertyValue('--nav-height')` devuelve "3.0625rem",
  // y `parseFloat` de eso da 3, no 49. Con 3 px de margen, el destino
  // quedaba tapado por el menú.
  const header = document.getElementById('site-header');
  const headerOffset = header ? Math.round(header.getBoundingClientRect().height) : 50;
  const offset = -(headerOffset + 8);

  if (lenisInstance) {
    lenisInstance.scrollTo(target as HTMLElement, { offset });
    return;
  }
  const top = target.getBoundingClientRect().top + window.scrollY + offset;
  window.scrollTo({ top, behavior: 'smooth' });
}

// ── API pública ─────────────────────────────────────────────────────────────

/** Monta el movimiento de la página actual. */
export function init(): void {
  teardown();

  if (reduceMotion) {
    // Sin movimiento: nada se oculta y nada se anima.
    document.querySelectorAll('.is-reveal-pending').forEach((el) => el.classList.remove('is-reveal-pending'));
    return;
  }

  window.__motionReady = true;
  (window as any).__kuspideScrollTo = scrollToElement;

  /* ── Scroll suave ─────────────────────────────────────────────────────── */
  /*
   * `lerp` es la fracción del recorrido pendiente que se cubre en cada
   * fotograma (a 60 fps):
   *
   *   0.12 → el 63 % del recorrido en 150 ms, el 95 % en 415 ms
   *   0.25 → el 63 % en 70 ms,  el 95 % en 180 ms
   *
   * El 0.12 es el del original (getartcraft.com) y se nota demasiado
   * "tarde": la página tarda en responder a la rueda y el recorrido se
   * alarga con una cola larga. 0.25 deja un retardo corto y elegante
   * (justo el que pide el sitio) sin esa demora.
   */
  const lenis = new Lenis({ lerp: 0.25, anchors: true });
  lenisInstance = lenis;
  // El global que espera el timeline (`TimelineEvents.astro`): con él, el
  // marcador de la espina se actualiza en cada fotograma de Lenis y no
  // sólo cuando salta el scroll nativo.
  (window as any).lenis = lenis;

  lenis.on('scroll', ScrollTrigger.update);
  gsap.ticker.add((time) => lenis.raf(time * 1000));
  gsap.ticker.lagSmoothing(0);

  /* ── Entrada del hero ─────────────────────────────────────────────────── */
  initIntro();

  /* ── Trazo de línea y rótulos (los `data-draw-*` del original) ─────────── */
  for (const block of document.querySelectorAll<HTMLElement>('[data-draw]')) {
    const tick = block.querySelector<HTMLElement>('[data-draw-tick]');
    const eyebrows = [...block.querySelectorAll<HTMLElement>('[data-draw-eyebrow]')];
    const cells = [...block.querySelectorAll<HTMLElement>('[data-draw-cell]')];

    if (tick) gsap.set(tick, { scaleX: 0 });
    if (cells.length > 0) gsap.set(cells, { scale: 0, opacity: 0 });

    const trigger = ScrollTrigger.create({
      trigger: block,
      start: 'top 88%',
      once: true,
      onEnter: () => {
        const tl = gsap.timeline();

        // Los atributos se quitan ANTES de animar. Si se quitaran al terminar,
        // `clearProps` borra los estilos en línea primero y el elemento vuelve
        // a coincidir con la regla de motion.css que lo oculta: un salto de un
        // fotograma. El estado inicial ya está puesto por CSS o por `gsap.set`.
        if (tick) {
          tick.removeAttribute('data-draw-tick');
          tl.to(tick, { scaleX: 1, duration: 0.7, ease: 'power2.out' }, 0);
        }

        for (const eyebrow of eyebrows) eyebrow.removeAttribute('data-draw-eyebrow');
        if (eyebrows.length > 0) {
          // `stagger: 0.08` es el valor medido en el bundle del original.
          tl.fromTo(eyebrows, REVEAL_FROM, { ...REVEAL_TO, stagger: 0.08 }, 0.15);
        }

        for (const cell of cells) cell.removeAttribute('data-draw-cell');
        if (cells.length > 0) {
          tl.to(cells, { scale: 1, opacity: 1, duration: 0.35, ease: 'power2.out' }, 0.15);
        }
      },
    });
    triggers.push(trigger);
  }

  /* ── Revelado con desenfoque, con cascada horizontal ─────────────────── */
  // En la PRIMERA carga se ocultan TODOS (lo hace el CSS con `motion-ready`).
  // En una NAVEGACIÓN sólo se ocultan los que ya venían marcados como
  // pendientes (los que estaban fuera de pantalla): los que se ven entran
  // con el fundido de la transición, sin un fotograma en blanco.
  const firstLoad = document.documentElement.classList.contains('motion-ready');

  const revealItems = [...document.querySelectorAll<HTMLElement>('[data-reveal]')];

  for (const el of revealItems) {
    const pending = el.classList.contains('is-reveal-pending');
    if (!firstLoad && !pending) continue;

    const parent = el.parentElement;
    const delay =
      parent && parent.getBoundingClientRect().width > 0
        ? ((el.getBoundingClientRect().left - parent.getBoundingClientRect().left) /
            parent.getBoundingClientRect().width) *
          CASCADE_MAX
        : 0;

    gsap.set(el, REVEAL_FROM);

    const trigger = ScrollTrigger.create({
      trigger: el,
      start: 'top 88%',
      once: true,
      onEnter: () => {
        // Quitamos el atributo ANTES de animar, no al terminar.
        // Si se quita en `onComplete`, `clearProps` borra los estilos en
        // línea un fotograma antes de que corra el callback: en ese hueco el
        // elemento vuelve a coincidir con la regla de motion.css y da un salto
        // de visible a oculto (medido: 1 salto a los ~1040 ms).
        el.removeAttribute('data-reveal');
        // La clase pendiente se quita con el mismo criterio: mientras dure la
        // animación manda el estilo en línea; al limpiarse, el elemento tiene
        // que quedar visible.
        el.classList.remove('is-reveal-pending');
        gsap.to(el, { ...REVEAL_TO, delay });
      },
    });
    triggers.push(trigger);
  }

  // Las fuentes tardan: recalculamos las posiciones cuando terminan de cargar.
  document.fonts?.ready.then(() => ScrollTrigger.refresh());

  /* ── El regulador lateral NO se inicializa aquí ──────────────────────────
     Vive en `page-ruler.ts`, que está en todas las páginas y no arrastra
     GSAP ni Lenis. Aquí sólo le enseñamos la instancia de Lenis para que
     sus saltos de scroll sean suaves. */
  (window as any).__kuspideLenis = lenis;
}

/** Destruye el movimiento de la página que sale. */
export function teardown(): void {
  for (const trigger of triggers) trigger.kill();
  triggers = [];

  delete (window as any).__kuspideScrollTo;
  delete (window as any).__kuspideLenis;
  delete (window as any).lenis;

  if (lenisInstance) {
    lenisInstance.destroy();
    lenisInstance = null;
  }

  // Los elementos que quedaron marcados como pendientes y no llegaran a
  // animarse se sueltan: nada puede quedar invisible.
  document.querySelectorAll('.is-reveal-pending').forEach((el) => el.classList.remove('is-reveal-pending'));
}

/**
 * Entrada del hero, con los tiempos medidos del `introTuner` del original.
 *
 * 1. El rótulo se forma: las letras convergen desde una separación mayor.
 *    El original interpola cada letra con `baseX`, `metrics.adv` y `fontPx` y
 *    un easeInOutCubic sobre `wordDur`; acá se aproxima con `power2.inOut`, que
 *    es la misma familia de curva.
 * 2. El bloque de texto se revela con el desenfoque medido.
 *
 * La BARRA ya no se anima aquí: su entrada es una animación CSS (ver
 * SiteHeader.astro) para que no dependa de que GSAP haya cargado y no haya
 * destello. Como la cabecera persiste entre navegaciones, esa animación
 * ocurre UNA sola vez por sesión.
 */
function initIntro() {
  const letters = [...document.querySelectorAll<HTMLElement>('[data-hero-wordmark] [data-letter]')];

  // Sin rótulo no hay intro.
  if (letters.length === 0) return;

  const timeline = gsap.timeline();

  {
    const middle = (letters.length - 1) / 2;
    for (const [index, letter] of letters.entries()) {
      const offset = (index - middle) * WORD_SPREAD;
      timeline.fromTo(
        letter,
        { x: offset, autoAlpha: 0 },
        { x: 0, autoAlpha: 1, duration: INTRO.wordDur, ease: 'power2.inOut' },
        INTRO.wordAt
      );
    }
  }

  const copy = [...document.querySelectorAll<HTMLElement>('[data-hero-copy]')];
  if (copy.length > 0) {
    timeline.fromTo(
      copy,
      REVEAL_FROM,
      {
        ...REVEAL_TO,
        // El revelado del scroll dura 0,9 s; el del hero, menos: el texto está
        // escondido desde el primer pintado y cada décima cuenta para quien
        // llega a la portada.
        duration: 0.6,
        stagger: 0.06,
        onStart: () => {
          // El atributo se quita ANTES de que `clearProps` borre los estilos en
          // línea; si no, el elemento volvería a coincidir con motion.css y
          // daría un salto de un fotograma.
          for (const element of copy) element.removeAttribute('data-hero-copy');
        },
      },
      INTRO.copyAt
    );
  }
}
