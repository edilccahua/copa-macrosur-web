/**
 * page-ruler.ts — la regleta de scroll del borde derecho.
 *
 * Vive FUERA del módulo de movimiento a propósito: la regleta tiene que
 * estar en TODAS las páginas (incluidas las de datos, como la de
 * clasificaciones), pero el módulo de movimiento arrastra GSAP y Lenis, que
 * AGENTS.md prohíbe cargar en `/en-vivo` y `/admin/juez`. Aquí no hay
 * ninguna de las dos cosas: el scroll se hace con la API nativa y, si la
 * página tiene Lenis, se le pide el desplazamiento a través de
 * `window.__kuspideLenis`.
 *
 * Geometría copiada de `copiaartcraft/src/components/PageRuler.astro`: la
 * banda va pegada al **borde inferior del menú** (`inset-block:
 * var(--header-offset) 0`), ni por encima (sus marcas se dibujarían sobre
 * la cabecera) ni con hueco (parecería un elemento aparte). La escala
 * arranca en ese borde y sube con el scroll.
 *
 * Para que la banda no se coma los clics del menú, el regulador entero es
 * `pointer-events: none` y sólo `.ruler__grab` —que empieza bajo la
 * cabecera— es agarrable.
 */

let cleanup: (() => void) | null = null;
/** El elemento al que se inicializó la regleta (cambia en cada navegación). */
let currentBand: HTMLElement | null = null;

/** El Lenis de la página, si esta página lo tiene. */
function currentLenis(): { scrollTo: (t: number, o?: unknown) => void } | null {
  return (window as any).__kuspideLenis ?? null;
}

export function initPageRuler(): void {
  const el = document.querySelector<HTMLElement>('[data-ruler]');
  if (!el) return;
  // Con el router, el <body> se reemplaza en cada navegación: la regleta de
  // la página nueva es OTRO elemento. Si fuera el mismo, ya está
  // inicializada; si es otro, se desmonta la anterior (que si no dejaría
  // listeners de scroll acumulados) y se inicializa la nueva.
  if (cleanup && currentBand === el) return;
  destroyPageRuler();

  const band = el;
  currentBand = band;

  const scale = band.querySelector<HTMLElement>('[data-ruler-scale]');
  const readout = band.querySelector<HTMLElement>('[data-ruler-readout]');
  const thumb = band.querySelector<HTMLElement>('[data-ruler-thumb]');
  const strips = [...band.querySelectorAll<HTMLElement>('.ruler-digit-strip')];

  /**
   * La banda empieza en el borde inferior del menú. Todo lo que mide la
   * regleta es RELATIVO a ese borde: así la escala queda pegada al menú
   * (no parece un elemento aparte) y nunca se dibuja por encima de él.
   */
  const BAND_TOP = Math.round(band.getBoundingClientRect().top) || 50;
  /** Margen de la lectura numérica dentro de la banda. */
  const READOUT_TOP = 10;

  /**
   * El alto del documento se MIDE UNA VEZ y se vuelve a medir cuando cambia
   * el tamaño o terminan de cargar las fuentes. Antes se leía
   * `document.documentElement.scrollHeight` en CADA evento de scroll, lo que
   * provoca un layout síncrono forzado por fotograma.
   */
  let documentHeight = document.documentElement.scrollHeight;

  const measure = () => {
    documentHeight = document.documentElement.scrollHeight;
  };

  const metrics = () => ({
    documentHeight,
    viewport: window.innerHeight
  });

  const DIGIT_REM = 0.625;

  const progressFromY = (y: number) => {
    const { viewport } = metrics();
    return Math.min(1, Math.max(0, (y - BAND_TOP) / Math.max(1, viewport - BAND_TOP)));
  };

  const scrollToProgress = (progress: number, immediate = false) => {
    const { documentHeight: docH, viewport } = metrics();
    const target = progress * Math.max(0, docH - viewport);
    const lenis = currentLenis();
    if (lenis) {
      // Durante el arrastre NO salto instantáneo: una duración corta deja un
      // retardo leve y agradable en vez de un salto seco.
      lenis.scrollTo(target, immediate ? { immediate: true } : { duration: 0.2 });
    } else {
      window.scrollTo({ top: target, behavior: immediate ? 'auto' : 'smooth' });
    }
  };

  const update = () => {
    const { documentHeight: docH, viewport } = metrics();
    const scrolled = window.scrollY;
    const usable = Math.max(1, viewport - BAND_TOP);
    const active = band.classList.contains('is-active');

    // La MISMA escala se comprime: de la altura del documento (58,2px por
    // unidad) a la ventana (8,4px por unidad). Una sola escala, así que no
    // puede verse duplicada. En reposo, la escala arranca pegada al borde
    // inferior del menú y sube con el scroll.
    if (scale) {
      scale.style.height = `${active ? usable : docH}px`;
      scale.style.transform = `translateY(${active ? 0 : -scrolled}px)`;
    }

    const maximum = Math.max(1, docH - viewport);
    const progress = Math.min(1, Math.max(0, scrolled / maximum));

    if (readout) {
      readout.style.transform = `translateY(${READOUT_TOP + progress * usable}px)`;
    }

    // Pulgar: alto proporcional a la porción visible del documento, y baja
    // acompañando el scroll.
    if (thumb) {
      const thumbHeight = Math.max(24, usable * (usable / Math.max(1, docH - BAND_TOP)));
      thumb.style.height = `${thumbHeight}px`;
      thumb.style.transform = `translateY(${READOUT_TOP + progress * (usable - thumbHeight)}px)`;
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
   * Estado de interacción para el pulgar y los tests. La COMPRESIÓN de la
   * escala la gobierna el CSS con `:hover`, así que aunque este estado se
   * pierda, la compresión no se cae.
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

  /**
   * Las escrituras de estilo se agrupan en un fotograma: en cada evento de
   * scroll se pide UNA actualización y se aplica en el siguiente `rAF`.
   */
  let frame = 0;
  const schedule = () => {
    if (frame) return;
    frame = requestAnimationFrame(() => {
      frame = 0;
      update();
    });
  };

  const beginDrag = (event: PointerEvent) => {
    event.preventDefault();
    // SIN `band.focus()`: al enfocar por puntero, el navegador dibuja el
    // anillo de foco y se ve una línea azul que el original no tiene.
    band.classList.add('is-scrubbing');
    setActive(true);
    scrollToProgress(progressFromY(event.clientY));

    const move = (moveEvent: PointerEvent) => {
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
    const { viewport, documentHeight: docH } = metrics();
    const targets: Record<string, number> = {
      ArrowUp: window.scrollY - viewport * 0.2,
      ArrowDown: window.scrollY + viewport * 0.2,
      PageUp: window.scrollY - viewport,
      PageDown: window.scrollY + viewport,
      Home: 0,
      End: docH
    };
    const target = targets[event.key];
    if (target === undefined) return;
    event.preventDefault();
    const lenis = currentLenis();
    if (lenis) lenis.scrollTo(target);
    else window.scrollTo({ top: target });
  };

  band.addEventListener('pointerenter', () => setActive(true));
  band.addEventListener('pointerleave', () => {
    if (!band.classList.contains('is-scrubbing')) setActive(false);
  });
  band.addEventListener('focus', () => setActive(true));
  band.addEventListener('blur', () => {
    if (!band.classList.contains('is-scrubbing')) setActive(false);
  });
  band.addEventListener('pointerdown', beginDrag);
  band.addEventListener('keydown', onKeyDown);

  const onResize = () => {
    measure();
    schedule();
  };
  window.addEventListener('scroll', schedule, { passive: true });
  window.addEventListener('resize', onResize);
  document.fonts?.ready.then(() => {
    measure();
    schedule();
  });

  // El documento puede cambiar de alto sin que cambie el tamaño de la
  // ventana (imágenes que cargan, contenido que se despliega).
  const observer = new ResizeObserver(() => {
    measure();
    schedule();
  });
  observer.observe(document.body);

  update();

  cleanup = () => {
    if (frame) cancelAnimationFrame(frame);
    window.clearTimeout(settleTimer);
    observer.disconnect();
    window.removeEventListener('scroll', schedule);
    window.removeEventListener('resize', onResize);
    band.removeEventListener('pointerdown', beginDrag);
    band.removeEventListener('keydown', onKeyDown);
  };
}

export function destroyPageRuler(): void {
  cleanup?.();
  cleanup = null;
  currentBand = null;
}
