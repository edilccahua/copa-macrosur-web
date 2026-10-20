<script lang="ts">
  /**
   * LiveSection.svelte — sección 04 · Transmisión de la portada.
   *
   * El estado lo resuelve el backend (`GET /public/live-status`, specs/02 §6):
   *   · live          → enlace activo a /en-vivo
   *   · before_start  → hoy hay carrera, pero aún no son las 08:00
   *   · closed        → el admin cerró la transmisión
   *   · no_race_today → hoy no hay carrera; se anuncia la próxima
   *
   * La isla refresca cada minuto para encenderse a las 08:00 sin recargar y
   * apagarse cuando el organizador cierra. No carga GSAP ni Lenis.
   */
  import { API_V1, type LiveStatus } from '../lib/api';
  import { formatStageDate } from '../lib/stages';
  import { toDisplayTime } from '../lib/datetime';

  interface Props {
    initial: LiveStatus;
  }

  let { initial }: Props = $props();

  let status = $state<LiveStatus>(initial);

  $effect(() => {
    let cancelled = false;

    const refresh = async () => {
      try {
        const res = await fetch(`${API_V1}/public/live-status`, { cache: 'no-store' });
        if (res.ok && !cancelled) status = await res.json();
      } catch {
        /* Se conserva el último estado conocido. */
      }
    };

    const id = window.setInterval(refresh, 60_000);
    const onVisible = () => {
      if (document.visibilityState === 'visible') void refresh();
    };
    document.addEventListener('visibilitychange', onVisible);

    // Sincroniza al hidratar: la página pudo renderizarse antes de las 08:00
    // o antes de que el admin cerrara.
    void refresh();

    return () => {
      cancelled = true;
      window.clearInterval(id);
      document.removeEventListener('visibilitychange', onVisible);
    };
  });

  const stage = $derived(status.stage);
  const isLive = $derived(status.state === 'live');
  const isBefore = $derived(status.state === 'before_start');
  const isClosed = $derived(status.state === 'closed');
  const stageName = $derived(
    stage ? stage.name.replace(/^Fecha\s+\d+\s*:\s*/i, '') : ''
  );
  const metaLine = $derived(
    stage
      ? `${formatStageDate(stage.date)} · ${stageName} · ${toDisplayTime(stage.start_time)}`
      : ''
  );
  const resultsHref = $derived(
    stage ? `/ranking-general?modo=fecha&fecha=${stage.stage_number}` : '/ranking-general'
  );

  const chip = $derived(
    isLive
      ? 'EN VIVO'
      : isBefore
        ? 'HOY · ABRE 08:00'
        : isClosed
          ? 'TRANSMISIÓN FINALIZADA'
          : 'SEGUIMIENTO DE LLEGADAS'
  );

  const title = $derived(
    isLive
      ? 'LA META, EN TIEMPO REAL.'
      : isBefore
        ? 'HOY ABRE LA TRANSMISIÓN.'
        : isClosed
          ? 'LA TRANSMISIÓN CERRÓ.'
          : 'LA META, EN TIEMPO REAL.'
  );

  const body = $derived(
    isLive
      ? `Sigue las llegadas de ${stageName} a medida que los ciclistas cruzan la meta: tiempo, categoría y puesto provisional.`
      : isBefore
        ? `Hoy se corre ${stageName}. La transmisión de llegadas se abre a las 08:00; vuelve a esta sección a esa hora.`
        : isClosed
          ? 'La transmisión de llegadas terminó. Consulta la clasificación oficial de la fecha.'
          : 'El día de la carrera vas a poder seguir cada llegada a meta: tiempo, categoría y puesto provisional, a medida que los ciclistas cruzan la línea.'
  );
</script>

<article
  class="live"
  class:is-live={isLive}
  class:is-before={isBefore}
  class:is-closed={isClosed}
>
  <div class="live__copy">
    <p class="live__chip font-mono">
      <span class="live__dot" aria-hidden="true"></span>
      {chip}
    </p>

    <h3 class="live__title">{title}</h3>
    <p class="live__body">{body}</p>

    <ul class="live__specs font-mono">
      <li>LLEGADAS</li>
      <li>TIEMPO</li>
      <li>CATEGORÍA</li>
      <li>PUESTO</li>
    </ul>

    {#if stage}
      <p class="live__meta font-mono">{metaLine}</p>
    {/if}

    {#if isLive}
      <a class="live__cta" href="/en-vivo">
        VER LLEGADAS EN VIVO <span aria-hidden="true">→</span>
      </a>
    {:else if isClosed}
      <a class="live__cta" href={resultsHref}>
        VER RESULTADOS <span aria-hidden="true">→</span>
      </a>
    {:else}
      <p class="live__note font-mono">REVISA ESTA SECCIÓN EL DÍA DE LA CARRERA</p>
    {/if}
  </div>

  <div class="live__media">
    <div class="live__poster-wrap">
      {#if stage?.poster_url}
        <img
          class="live__poster"
          src={stage.poster_url}
          alt={`Póster de ${stageName}`}
          loading="lazy"
        />
      {:else}
        <div class="live__fallback" aria-hidden="true">META</div>
      {/if}

      <div class="live__signal" aria-hidden="true">
        <span></span>
        <span></span>
        <span></span>
      </div>
    </div>

    <!-- La meta: una línea de cuadros horizontal, como el arco de llegada. -->
    <div class="live__finishbar">
      <p class="live__stamp font-mono">META · 08:00 → CIERRE</p>
      <span class="live__finish" aria-hidden="true"></span>
    </div>
  </div>
</article>

<style>
  .live {
    --live-accent: var(--copa-gold);
    position: relative;
    display: grid;
    grid-template-columns: 1fr;
    margin-top: 1.5rem;
    margin-bottom: 4rem;
    background: var(--bg-raised);
    border: var(--hairline) solid var(--line);
    overflow: hidden;
  }

  /* Sin borde de acento superior: la tarjeta respira por su contenido. */
  .live.is-live {
    --live-accent: var(--status-down);
  }

  .live.is-closed {
    --live-accent: var(--muted);
  }

  .live__copy {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    justify-content: center;
    gap: 0.75rem;
    padding: 1.5rem;
  }

  .live__chip {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    margin: 0;
    padding: 0.3rem 0.625rem;
    font-size: 0.625rem;
    font-weight: 700;
    letter-spacing: 0.14em;
    color: var(--ink);
    border: var(--hairline) solid var(--line);
    background: var(--bg);
  }

  .live__dot {
    width: 0.375rem;
    height: 0.375rem;
    flex: 0 0 auto;
    background: var(--live-accent);
  }

  .is-live .live__dot {
    animation: live-pulse 1.4s ease-in-out infinite;
    box-shadow: 0 0 0.5rem var(--live-accent);
  }

  .live__title {
    margin: 0;
    max-width: 15ch;
    font-family: var(--font-display);
    font-size: clamp(1.65rem, 3vw, 2.35rem);
    font-weight: var(--font-weight-medium);
    line-height: 1.02;
    letter-spacing: var(--tracking-tight);
    color: var(--ink-strong);
  }

  .live__body {
    margin: 0;
    max-width: 46ch;
    font-size: var(--text-sm);
    line-height: var(--leading-relaxed);
    color: var(--muted);
  }

  .live__meta {
    margin: 0;
    font-size: 0.6875rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--faint);
  }

  .live__specs {
    display: flex;
    flex-wrap: wrap;
    gap: 0.375rem;
    margin: 0.25rem 0 0;
    padding: 0;
    list-style: none;
  }

  .live__specs li {
    padding: 0.2rem 0.45rem;
    font-size: 0.5625rem;
    letter-spacing: 0.1em;
    color: var(--muted);
    border: var(--hairline) solid var(--line);
  }

  .live__cta {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    margin-top: 0.5rem;
    padding: 0.75rem 1rem;
    font-family: var(--font-mono);
    font-size: 0.6875rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    color: var(--invert-fg);
    background: var(--invert-bg);
    text-decoration: none;
    transition: background var(--default-transition-duration)
      var(--default-transition-timing-function);
  }

  .live__cta:hover {
    background: var(--live-accent);
    color: var(--invert-fg);
  }

  .live.is-closed .live__cta:hover {
    background: var(--ink);
  }

  .live__note {
    margin: 0.5rem 0 0;
    padding-top: 0.75rem;
    font-size: 0.625rem;
    letter-spacing: 0.14em;
    color: var(--copa-gold);
    border-top: var(--hairline) solid var(--line);
  }

  /* ── La pieza gráfica ─────────────────────────────────────────────── */
  .live__media {
    display: flex;
    flex-direction: column;
    background: var(--bg-sunken);
    border-top: var(--hairline) solid var(--line);
  }

  /* El póster es 4:5 (720 × 900). El bloque usa SU proporción: así no se
     recorta ni la fecha ni la lista de categorías del cartel. */
  .live__poster-wrap {
    position: relative;
    width: 100%;
    aspect-ratio: 4 / 5;
    overflow: hidden;
  }

  .live__poster {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .live__fallback {
    position: absolute;
    inset: 0;
    display: grid;
    place-items: center;
    font-family: var(--font-display);
    font-size: clamp(4rem, 14vw, 9rem);
    letter-spacing: var(--tracking-tight);
    color: var(--line-strong);
  }

  /* La meta: una línea de cuadros horizontal, como el arco de llegada. */
  .live__finishbar {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.6rem 0.75rem;
    background: var(--bg-raised);
    border-top: var(--hairline) solid var(--line);
  }

  .live__finish {
    flex: 1;
    height: 0.75rem;
    background: repeating-conic-gradient(
        var(--invert-bg) 0% 25%,
        var(--invert-fg) 0% 50%
      )
      0 0 / 12px 12px;
  }

  .live__signal {
    position: absolute;
    top: 1rem;
    right: 1rem;
    width: 2.5rem;
    height: 2.5rem;
  }

  .live__signal::after {
    content: '';
    position: absolute;
    inset: calc(50% - 3px);
    width: 6px;
    height: 6px;
    background: var(--live-accent);
  }

  .live__signal span {
    position: absolute;
    inset: 0;
    border: 1px solid var(--live-accent);
    border-radius: 50%;
    opacity: 0;
  }

  .is-live .live__signal span {
    animation: live-ring 2.4s ease-out infinite;
  }

  .is-live .live__signal span:nth-child(2) {
    animation-delay: 0.8s;
  }

  .is-live .live__signal span:nth-child(3) {
    animation-delay: 1.6s;
  }

  .live__stamp {
    margin: 0;
    padding: 0.25rem 0.5rem;
    white-space: nowrap;
    font-size: 0.625rem;
    letter-spacing: 0.12em;
    color: var(--ink);
    border: var(--hairline) solid var(--line);
    background: var(--bg);
  }

  @keyframes live-pulse {
    0%,
    100% {
      opacity: 1;
    }
    50% {
      opacity: 0.3;
    }
  }

  @keyframes live-ring {
    0% {
      transform: scale(0.25);
      opacity: 0.9;
    }
    100% {
      transform: scale(1.15);
      opacity: 0;
    }
  }

  @media (min-width: 48em) {
    .live {
      grid-template-columns: minmax(0, 1.45fr) minmax(18rem, 0.75fr);
    }

    .live__copy {
      padding: 2rem;
    }

    .live__media {
      border-top: 0;
      border-left: var(--hairline) solid var(--line);
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .is-live .live__dot,
    .is-live .live__signal span {
      animation: none;
    }
  }
</style>
