/**
 * showcase-motion.ts — movimiento del escaparate.
 *
 * Los parámetros NO están inventados: se extrajeron del bundle del original.
 * Los nombres de easing y los números sobreviven a la minificación.
 *
 *   Lenis           new Lenis({ lerp: 0.12, anchors: true })
 *   Revelado        from { autoAlpha: 0, y: 28, filter: "blur(8px)" }
 *                   to   { autoAlpha: 1, y: 0,  filter: "blur(0px)",
 *                          duration: 0.9, ease: "power3.out", clearProps: "all" }
 *   Entrada del nav #site-nav > div > *  from { autoAlpha: 0, y: -6 }
 *                   to { duration: 0.5, stagger: 0.08, ease: "power2.out" }
 *   Trazo           scaleX 0 -> 1, duration 0.7, ease "power2.out"
 *   Celdas          scale 0 -> 1 y opacity 0 -> 1, duration 0.35
 *   Disparador      ScrollTrigger start "top 88%", once: true
 *   Cascada         delay = (x del elemento dentro de su padre) * 0.18
 *
 * Límites que impone AGENTS.md:
 *   - esto se importa ÚNICAMENTE desde el layout de escaparate;
 *   - con `prefers-reduced-motion: reduce` no se inicializa nada y las clases
 *     quedan visibles (el CSS nunca las oculta).
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
 */
const INTRO = {
  instrAt: 0.7,
  wordAt: 0.35,
  wordDur: 0.85,
  copyAt: 1.05,
};

/** Separación extra con la que arrancan las letras del rótulo, en px. */
const WORD_SPREAD = 70;

const NAV_FROM = { autoAlpha: 0, y: -6 };
const NAV_TO = {
  autoAlpha: 1,
  y: 0,
  duration: 0.5,
  stagger: 0.08,
  ease: 'power2.out',
  clearProps: 'all',
};

const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

declare global {
  interface Window {
    /** El módulo avisa que arrancó; el seguro del <head> lo consulta. */
    __motionReady?: boolean;
  }
}

// El scroll suave y los revelados se apagan con `prefers-reduced-motion`.
// El regulador NO: es un control de navegación y debe funcionar siempre.
const lenisInstance = reduceMotion ? null : init();

initRuler(lenisInstance);

function init(): Lenis {
  // Avisa al seguro del <head> que el módulo sí arrancó: así no se quita la
  // clase `motion-ready` a los 3s.
  window.__motionReady = true;

  /* ── Scroll suave ─────────────────────────────────────────────────────── */
  const lenis = new Lenis({ lerp: 0.12, anchors: true });

  lenis.on('scroll', ScrollTrigger.update);
  gsap.ticker.add((time) => lenis.raf(time * 1000));
  gsap.ticker.lagSmoothing(0);

  /* ── Entrada del hero y de la barra de navegación ─────────────────────── */
  initIntro();

  /* ── Trazo de línea y rótulos (los `data-draw-*` del original) ─────────── */
  for (const block of document.querySelectorAll<HTMLElement>('[data-draw]')) {
    const tick = block.querySelector<HTMLElement>('[data-draw-tick]');
    const eyebrows = [...block.querySelectorAll<HTMLElement>('[data-draw-eyebrow]')];
    const cells = [...block.querySelectorAll<HTMLElement>('[data-draw-cell]')];

    if (tick) gsap.set(tick, { scaleX: 0 });
    if (cells.length > 0) gsap.set(cells, { scale: 0, opacity: 0 });

    ScrollTrigger.create({
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
  }

  /* ── Revelado con desenfoque, con cascada horizontal ─────────────────── */
  const revealItems = [...document.querySelectorAll<HTMLElement>('[data-reveal]')];

  for (const el of revealItems) {
    const parent = el.parentElement;
    const delay =
      parent && parent.getBoundingClientRect().width > 0
        ? ((el.getBoundingClientRect().left - parent.getBoundingClientRect().left) /
            parent.getBoundingClientRect().width) *
          CASCADE_MAX
        : 0;

    gsap.set(el, REVEAL_FROM);

    ScrollTrigger.create({
      trigger: el,
      start: 'top 88%',
      once: true,
      onEnter: () => {
        // Quitamos el atributo ANTES de animar, no al terminar.
        // Si se quita en `onComplete`, `clearProps: "all"` borra los estilos en
        // línea un fotograma antes de que corra el callback: en ese hueco el
        // elemento vuelve a coincidir con la regla de motion.css y da un salto
        // de visible a oculto (medido: 1 salto a los ~1040 ms).
        // Quitándolo ahora, los estilos en línea de `gsap.set` mantienen el
        // estado inicial escondido y al limpiarse el elemento ya es visible.
        el.removeAttribute('data-reveal');
        gsap.to(el, { ...REVEAL_TO, delay });
      },
    });
  }

  // Las fuentes tardan: recalculamos las posiciones cuando terminan de cargar.
  document.fonts?.ready.then(() => ScrollTrigger.refresh());

  return lenis;
}

/**
 * Entrada del hero, con los tiempos medidos del `introTuner` del original.
 *
 * 1. El nav entra en cascada, esperando `instrAt`.
 * 2. El rótulo se forma: las letras convergen desde una separación mayor.
 *    El original interpola cada letra con `baseX`, `metrics.adv` y `fontPx` y
 *    un easeInOutCubic sobre `wordDur`; acá se aproxima con `power2.inOut`, que
 *    es la misma familia de curva.
 * 3. El bloque de texto se revela con el desenfoque medido.
 *
 * No hay tarjetas flotantes: son imágenes de la marca que no tenemos.
 */
function initIntro() {
  const letters = [...document.querySelectorAll<HTMLElement>('[data-hero-wordmark] [data-letter]')];

  // Sin rótulo no hay intro. Antes el menú se volvía a animar en TODAS las
  // páginas al navegar, y se veía mal: sólo la home tiene secuencia de entrada.
  if (letters.length === 0) return;

  const timeline = gsap.timeline();

  const navItems = document.querySelectorAll('.hdr__bar > *');
  if (navItems.length > 0) {
    timeline.to({}, { duration: INTRO.instrAt }, 0);
    timeline.fromTo(navItems, NAV_FROM, NAV_TO, INTRO.instrAt);
  }

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
        stagger: 0.08,
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

/**
 * Regulador lateral: cinta métrica + control de scroll.
 *
 * Es un `role="scrollbar"` de verdad, sondeado del original:
 *   - clic en y=300  → scrollY=1424   (240/840 = 28,6% de 4912 ≈ 1403)
 *   - clic en y=700  → scrollY=3788   (640/840 = 76,2% de 4912 ≈ 3743)
 *   - arrastrar desplaza de forma continua
 *   - `aria-valuenow` de 0 a 100
 * El mapeo es el inverso de la línea de lectura:
 *   progreso = (y − 60) / (alto de ventana − 60)
 *
 * La lectura es un contador de rodillo: tres columnas de dígitos 0-9, como el
 * `ruler-digit-col` del original.
 */
function initRuler(lenis: Lenis | null) {
  const band = document.querySelector<HTMLElement>('[data-ruler]');
  if (!band) return;

  const scale = band.querySelector<HTMLElement>('[data-ruler-scale]');
  const readout = band.querySelector<HTMLElement>('[data-ruler-readout]');
  const thumb = band.querySelector<HTMLElement>('[data-ruler-thumb]');
  const strips = [...band.querySelectorAll<HTMLElement>('.ruler-digit-strip')];

  /** Desplazamiento inicial medido de la escala. */
  const OFFSET = 60;
  /** Alto de cada dígito del rodillo, en rem (coincide con el CSS). */
  const DIGIT_REM = 0.625;

  const metrics = () => ({
    documentHeight: document.documentElement.scrollHeight,
    viewport: window.innerHeight,
  });

  const progressFromY = (y: number) => {
    const { viewport } = metrics();
    return Math.min(1, Math.max(0, (y - OFFSET) / Math.max(1, viewport - OFFSET)));
  };

  const scrollToProgress = (progress: number, immediate = false) => {
    const { documentHeight, viewport } = metrics();
    const target = progress * Math.max(0, documentHeight - viewport);
    if (lenis) {
      // Durante el arrastre NO salto instantáneo: una duración corta deja un
      // retardo leve y agradable en vez de un salto seco.
      lenis.scrollTo(target, immediate ? { immediate: true } : { duration: 0.2 });
    } else {
      window.scrollTo({ top: target, behavior: immediate ? 'auto' : 'smooth' });
    }
  };

  const update = () => {
    const { documentHeight, viewport } = metrics();
    const scrolled = window.scrollY;
    const usable = Math.max(1, viewport - OFFSET);
    const active = band.classList.contains('is-active');

    // La MISMA escala se comprime: de la altura del documento (58,2px por
    // unidad) a la ventana (8,4px por unidad). Una sola escala, así que no
    // puede verse duplicada.
    if (scale) {
      scale.style.height = `${active ? usable : documentHeight}px`;
      scale.style.transform = `translateY(${active ? OFFSET : OFFSET - scrolled}px)`;
    }

    const maximum = Math.max(1, documentHeight - viewport);
    const progress = Math.min(1, Math.max(0, scrolled / maximum));

    if (readout) {
      readout.style.transform = `translateY(${OFFSET + progress * usable}px)`;
    }

    // Pulgar: alto proporcional a la porción visible del documento, y baja
    // acompañando el scroll. Medido: 128px de alto, 316px de desplazamiento a
    // scroll 1800 en su página.
    if (thumb) {
      const thumbHeight = Math.max(
        24,
        usable * (usable / Math.max(1, documentHeight - OFFSET))
      );
      thumb.style.height = `${thumbHeight}px`;
      thumb.style.transform = `translateY(${OFFSET + progress * (usable - thumbHeight)}px)`;
    }

    // Contador de rodillo: cada columna se desplaza hasta su dígito.
    const value = String(Math.round(progress * 100)).padStart(3, '0');
    for (const [index, strip] of strips.entries()) {
      const digit = Number(value[index] ?? 0);
      strip.style.transform = `translateY(${-digit * DIGIT_REM}rem)`;
    }

    band.setAttribute('aria-valuenow', String(Math.round(progress * 100)));
  };

  /**
   * Estado de interacción para el pulgar y los tests. La COMPRESIÓN de la escala
   * la gobierna el CSS con `:hover`, así que aunque este estado se pierda, la
   * compresión no se cae.
   */
  let settleTimer: number | undefined;
  const setActive = (next: boolean) => {
    if (band.classList.contains('is-active') === next) return;
    if (!next) {
      // Deja la transición encendida un instante para que la vuelta sea suave.
      band.classList.add('is-settling');
      window.clearTimeout(settleTimer);
      settleTimer = window.setTimeout(() => band.classList.remove('is-settling'), 340);
    }
    band.classList.toggle('is-active', next);
    update();
  };

  band.addEventListener('pointerenter', () => setActive(true));
  band.addEventListener('pointerleave', () => {
    if (!band.classList.contains('is-scrubbing')) setActive(false);
  });
  band.addEventListener('focus', () => setActive(true));
  band.addEventListener('blur', () => {
    if (!band.classList.contains('is-scrubbing')) setActive(false);
  });

  // Interacción: clic para saltar a esa altura, arrastre para desplazar.
  const beginDrag = (event: PointerEvent) => {
    event.preventDefault();
    // SIN `band.focus()`: al enfocar por puntero, el navegador dibuja el anillo
    // de foco y se ve una línea azul que el original no tiene. El teclado sigue
    // funcionando porque la banda es enfocable por tabulación.
    band.classList.add('is-scrubbing');
    setActive(true);
    scrollToProgress(progressFromY(event.clientY));

    const move = (moveEvent: PointerEvent) => {
      // Sin `immediate`: el arrastre sigue al puntero con un retardo corto.
      scrollToProgress(progressFromY(moveEvent.clientY));
    };
    const end = () => {
      band.classList.remove('is-scrubbing');
      if (!band.matches(':hover')) setActive(false);
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', end);
      window.removeEventListener('pointercancel', end);
    };

    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', end);
    window.addEventListener('pointercancel', end);
  };

  // Accesibilidad: si es un control con `role="scrollbar"`, tiene que
  // responder al teclado (Inicio/Fin y flechas).
  const onKeyDown = (event: KeyboardEvent) => {
    const { viewport, documentHeight } = metrics();
    const targets: Record<string, number> = {
      ArrowUp: window.scrollY - viewport * 0.2,
      ArrowDown: window.scrollY + viewport * 0.2,
      PageUp: window.scrollY - viewport,
      PageDown: window.scrollY + viewport,
      Home: 0,
      End: documentHeight,
    };
    const target = targets[event.key];
    if (target === undefined) return;
    event.preventDefault();
    if (lenis) lenis.scrollTo(target);
    else window.scrollTo({ top: target });
  };

  band.addEventListener('pointerdown', beginDrag);
  band.addEventListener('keydown', onKeyDown);
  window.addEventListener('scroll', update, { passive: true });
  window.addEventListener('resize', update);
  document.fonts?.ready.then(update);

  update();
}
