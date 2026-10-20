<script lang="ts">
  /**
   * EventCountdown.svelte — Temporizador Deportivo de Alta Precisión
   * Svelte 5 Runes puro ($state, $derived, $effect, $props).
   * Estética GetArtCraft con Geist Mono y números tabulares fijos.
   */
  interface Props {
    targetDate?: string;
    label?: string;
    /** La hora de largada en formato de lectura ("08:00 HRS"). */
    displayTime?: string;
    /**
     * Estado REAL de la fecha (de la BD). Antes el componente decidía solo:
     * cuando pasaba la fecha se ponía "¡ETAPA EN DISPUTA!" aunque la carrera
     * ya hubiera terminado. Ahora el estado lo dice la base de datos.
     */
    status?: 'UPCOMING' | 'REGISTRATION_OPEN' | 'LIVE' | 'FINISHED' | string;
  }

  let {
    targetDate = '',
    label = 'LARGADA OFICIAL',
    displayTime = '08:00 HRS',
    status = 'UPCOMING'
  }: Props = $props();

  function getDiffMs(): number {
    const target = new Date(targetDate).getTime();
    if (Number.isNaN(target)) return 0;
    const now = Date.now();
    return Math.max(0, target - now);
  }

  let diff = $state(getDiffMs());

  $effect(() => {
    diff = getDiffMs();
    const interval = setInterval(() => {
      diff = getDiffMs();
    }, 1000);

    return () => clearInterval(interval);
  });

  let days = $derived(Math.floor(diff / (1000 * 60 * 60 * 24)));
  let hours = $derived(Math.floor((diff / (1000 * 60 * 60)) % 24));
  let minutes = $derived(Math.floor((diff / (1000 * 60)) % 60));
  let seconds = $derived(Math.floor((diff / 1000) % 60));
  let isPast = $derived(diff <= 0);

  /** El estado que se muestra: lo manda la BD, no la fecha. */
  let state = $derived<'countdown' | 'live' | 'finished' | 'passed'>(
    status === 'LIVE'
      ? 'live'
      : status === 'FINISHED'
        ? 'finished'
        : isPast
          ? 'passed'
          : 'countdown'
  );

  function pad(n: number): string {
    return String(n).padStart(2, '0');
  }
</script>

<div class="countdown" aria-label="Cuenta regresiva para la carrera">
  <div class="countdown__header">
    <span class="countdown__pulse" aria-hidden="true"></span>
    <span class="countdown__kicker">[ {label} ]</span>
    <span class="countdown__time-target">{displayTime} · PE</span>
  </div>

  {#if state === 'live'}
    <div class="countdown__live-badge">
      <span class="countdown__live-dot"></span>
      <span class="countdown__live-text">¡ETAPA EN DISPUTA!</span>
    </div>
  {:else if state === 'finished'}
    <div class="countdown__live-badge countdown__live-badge--done">
      <span class="countdown__live-text">ETAPA FINALIZADA</span>
    </div>
  {:else if state === 'passed'}
    <div class="countdown__live-badge countdown__live-badge--done">
      <span class="countdown__live-text">FECHA PASADA</span>
    </div>
  {:else}
    <div class="countdown__digits">
      <div class="countdown__block">
        <span class="countdown__val">{pad(days)}</span>
        <span class="countdown__unit">DÍAS</span>
      </div>

      <span class="countdown__sep" aria-hidden="true">:</span>

      <div class="countdown__block">
        <span class="countdown__val">{pad(hours)}</span>
        <span class="countdown__unit">HRS</span>
      </div>

      <span class="countdown__sep" aria-hidden="true">:</span>

      <div class="countdown__block">
        <span class="countdown__val">{pad(minutes)}</span>
        <span class="countdown__unit">MIN</span>
      </div>

      <span class="countdown__sep" aria-hidden="true">:</span>

      <div class="countdown__block countdown__block--active">
        <span class="countdown__val">{pad(seconds)}</span>
        <span class="countdown__unit">SEG</span>
      </div>
    </div>
  {/if}
</div>

<style>
  .countdown {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 0.375rem;
    padding: 0.625rem 0.875rem;
    background: var(--bg-sunken);
    border: var(--hairline) solid var(--line);
    border-radius: 0;
  }

  .countdown__header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-family: var(--font-mono);
    font-size: 0.625rem;
    font-weight: var(--font-weight-medium);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: var(--faint);
  }

  .countdown__pulse {
    width: 0.375rem;
    height: 0.375rem;
    background: var(--accent);
    animation: countdown-pulse 1.8s ease-in-out infinite;
  }

  .countdown__kicker {
    color: var(--muted);
  }

  .countdown__time-target {
    color: var(--faint);
  }

  .countdown__digits {
    display: flex;
    align-items: center;
    gap: 0.375rem;
  }

  .countdown__block {
    display: flex;
    flex-direction: column;
    align-items: center;
    min-width: 2.375rem;
    padding: 0.25rem 0.375rem;
    background: var(--bg-raised);
    border: var(--hairline) solid var(--line);
    border-radius: 0;
  }

  .countdown__block--active {
    border-color: var(--line-strong);
  }

  .countdown__val {
    font-family: var(--font-mono);
    font-size: 1.125rem;
    font-weight: 600;
    line-height: 1.1;
    font-variant-numeric: tabular-nums;
    letter-spacing: -0.02em;
    color: var(--ink-strong);
  }

  .countdown__unit {
    font-family: var(--font-mono);
    font-size: 0.5625rem;
    font-weight: var(--font-weight-medium);
    letter-spacing: 0.08em;
    color: var(--faint);
  }

  .countdown__sep {
    font-family: var(--font-mono);
    font-size: 1rem;
    font-weight: 300;
    line-height: 1;
    color: var(--faint);
    transform: translateY(-0.25rem);
    user-select: none;
  }

  .countdown__live-badge {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.375rem 0.75rem;
    background: var(--bg-raised);
    border: var(--hairline) solid var(--accent);
    font-family: var(--font-mono);
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    color: var(--accent);
  }

  .countdown__live-dot {
    width: 0.5rem;
    height: 0.5rem;
    border-radius: 50%;
    background: var(--accent);
    box-shadow: 0 0 6px var(--accent);
    animation: countdown-pulse 1s infinite alternate;
  }

  @keyframes countdown-pulse {
    0% {
      opacity: 0.4;
      transform: scale(0.9);
    }
    100% {
      opacity: 1;
      transform: scale(1.1);
    }
  }

  @media (max-width: 30em) {
    .countdown {
      width: 100%;
      box-sizing: border-box;
    }
    .countdown__digits {
      width: 100%;
      justify-content: space-between;
    }
    .countdown__block {
      flex: 1;
      min-width: 0;
    }
  }
</style>
