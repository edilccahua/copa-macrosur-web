<script lang="ts">
  /**
   * RouteMapGpx.svelte — el perfil de etapa de una carrera.
   *
   * Dibuja la geometría REAL de la ruta (`Stage.route_geojson`, ya simplificada
   * a 500 puntos) como una silueta de altimetría, al estilo del perfil de
   * etapa del Tour: la silueta, los puertos con su categoría, las líneas de
   * msnm y el kilometraje.
   *
   * La escala vertical se DECLARA en pantalla. Una ruta de 40 km con 650 m
   * de desnivel dibujada a escala isométrica sería una línea casi plana: el
   * perfil la exagera para que se lea, y dice cuánto la exagera.
   *
   * Nada de lo que se ve está inventado: si la fecha no tiene geometría, el
   * bloque lo dice en vez de fabricar una silueta.
   */
  import type { Checkpoint, RouteProfile, Summit } from '../../lib/api';

  interface Props {
    stageName: string;
    routeProfile: RouteProfile | null;
    summits: Summit[];
    checkpoints: Checkpoint[];
    gpxUrl?: string;
  }

  let { stageName, routeProfile, summits, checkpoints, gpxUrl }: Props = $props();

  let activeKm = $state(0);

  /** El lienzo del perfil: 1000 × 620 unidades de viewBox. */
  const W = 1000;
  const H = 620;
  const PAD_L = 62;
  const PAD_R = 26;
  /** La franja superior donde viven los puertos. */
  const PAD_T = 118;
  const PAD_B = 66;
  const PLOT_W = W - PAD_L - PAD_R;
  const PLOT_H = H - PAD_T - PAD_B;

  /** El perfil, sus alturas y el punto activo. */
  let profile = $derived(routeProfile);
  let points = $derived(profile?.points ?? []);

  /** El rango de altitudes, redondeado a decenas para las líneas de msnm. */
  let elevationRange = $derived.by(() => {
    if (points.length === 0) return { min: 0, max: 0 };
    const rawMin = Math.min(...points.map((p) => p.ele));
    const rawMax = Math.max(...points.map((p) => p.ele));
    const min = Math.floor(rawMin / 50) * 50;
    const max = Math.ceil(rawMax / 50) * 50;
    return { min, max: max > min ? max : min + 50 };
  });

  /**
   * La exageración vertical del gráfico.
   *
   * El perfil mapea el rango REAL de altitudes a todo el alto del lienzo (es
   * lo que hace el perfil del Tour: el eje Y lleva las altitudes en msnm).
   *
   * Eso estira la vertical: el lienzo es mucho más ancho que alto, así que un
   * desnivel pequeño necesita MUCHAS más unidades verticales que las que
   * ocuparía a escala isométrica. La exageración es ese factor, y se
   * DECLARA en pantalla: un lector de mapas necesita saber cuánto se
   * exageró, porque una subida del 8% no se ve como una del 8% en un perfil
   * con ×29.
   */
  let exaggeration = $derived.by(() => {
    if (!profile || points.length === 0) return 1;
    const span = elevationRange.max - elevationRange.min;
    if (span <= 0) return 1;
    const distance_m = (profile.distance_km || 1) * 1000;
    // Metros horizontales por unidad de lienzo, contra metros verticales.
    const metresPerUnitX = distance_m / PLOT_W;
    const metresPerUnitY = span / PLOT_H;
    const factor = metresPerUnitX / metresPerUnitY;
    return factor >= 10 ? Math.round(factor) : Math.max(1, Math.round(factor));
  });

  /** X de un kilómetro. */
  function xOf(km: number): number {
    const total = profile?.distance_km || 1;
    return PAD_L + (km / total) * PLOT_W;
  }

  /** Y de una altitud: el rango real ocupa todo el alto del gráfico. */
  function yOf(ele: number): number {
    const { min, max } = elevationRange;
    const span = max - min || 1;
    const ratio = (ele - min) / span;
    return PAD_T + PLOT_H - ratio * PLOT_H;
  }

  /** La silueta de la ruta, como `d` de SVG. */
  let tracePath = $derived(
    points.length > 1
      ? `M ${points.map((p) => `${xOf(p.km).toFixed(1)},${yOf(p.ele).toFixed(1)}`).join(' L ')}`
      : ''
  );

  /** El área bajo la silueta. */
  let areaPath = $derived(
    points.length > 1
      ? `${tracePath} L ${xOf(points[points.length - 1].km).toFixed(1)},${(PAD_T + PLOT_H).toFixed(1)} L ${xOf(points[0].km).toFixed(1)},${(PAD_T + PLOT_H).toFixed(1)} Z`
      : ''
  );

  /** Las líneas de msnm: cinco horizontales con su etiqueta. */
  let gridLines = $derived.by(() => {
    const { min, max } = elevationRange;
    const step = Math.max(1, Math.round((max - min) / 4 / 50) * 50) || 50;
    const lines: { y: number; label: string }[] = [];
    for (let value = min; value <= max; value += step) {
      lines.push({ y: yOf(value), label: `${value}` });
    }
    return lines;
  });

  /** Las marcas de kilometraje en el eje inferior. */
  let kmTicks = $derived.by(() => {
    const total = profile?.distance_km || 0;
    if (total <= 0) return [];
    const step = total > 40 ? 10 : total > 15 ? 5 : 2;
    const ticks: { x: number; label: string }[] = [];
    for (let km = 0; km <= total + 0.01; km += step) {
      ticks.push({ x: xOf(km), label: km.toFixed(0) });
    }
    return ticks;
  });

  /**
   * Los checkpoints, separados para que sus etiquetas no se pisen con las
   * de los puertos: van en la franja de abajo, con su línea punteada.
   */
  let checkpointMarks = $derived.by(() => {
    if (points.length === 0) return [];
    return checkpoints.map((checkpoint) => {
      const total = profile?.distance_km || 1;
      const target = (checkpoint.distance_from_start_km / total) * total;
      let best = points[0];
      let bestDist = Math.abs(best.km - target);
      for (const point of points) {
        const distance = Math.abs(point.km - target);
        if (distance < bestDist) {
          bestDist = distance;
          best = point;
        }
      }
      return { checkpoint, point: best };
    });
  });

  /** El punto de la traza más cercano al kilómetro activo. */
  let activePoint = $derived.by(() => {
    if (points.length === 0) return null;
    const total = profile?.distance_km || 1;
    const target = (activeKm / total) * total;
    let best = points[0];
    let bestDist = Math.abs(best.km - target);
    for (const point of points) {
      const distance = Math.abs(point.km - target);
      if (distance < bestDist) {
        bestDist = distance;
        best = point;
      }
    }
    return best;
  });

  /** El punto de un checkpoint, localizado por su kilómetro. */
  function checkpointAt(checkpoint: Checkpoint) {
    const total = profile?.distance_km || 1;
    const target = (checkpoint.distance_from_start_km / total) * total;
    let best = points[0];
    let bestDist = Math.abs(best.km - target);
    for (const point of points) {
      const distance = Math.abs(point.km - target);
      if (distance < bestDist) {
        bestDist = distance;
        best = point;
      }
    }
    return best;
  }

  /** El color de la categoría de un puerto, al estilo del Tour. */  function categoryColor(category: string): string {
    switch (category) {
      case 'HC':
        return '#e0368f';
      case '1':
        return '#e0368f';
      case '2':
        return '#f26b1d';
      case '3':
        return '#2f7bf5';
      case '4':
        return '#7bb51c';
      default:
        return '#70707c';
    }
  }

  /** La categoría se lee con su número Romano, como en el Tour. */
  function categoryLabel(category: string): string {
    if (!category) return '';
    return category === 'HC' ? 'HC' : category;
  }

  let hasProfile = $derived(points.length > 1);
</script>

<div class="route-profile">
  <div class="route-header">
    <div class="route-title font-mono">[ PERFIL DE ETAPA ]</div>
    <div class="route-metrics font-mono">
      {#if profile}
        <span>DISTANCIA: <strong>{profile.distance_km} KM</strong></span>
        <span>DESNIVEL +: <strong>{profile.elevation_gain_m} M</strong></span>
        <span>DESNIVEL −: <strong>{profile.elevation_loss_m} M</strong></span>
        <span>PENDIENTE MEDIA: <strong>{profile.mean_grade_pct}%</strong></span>
        <span class="route-scale">ESCALA VERTICAL ×{exaggeration}</span>
      {/if}
    </div>
  </div>

  {#if hasProfile}
    <div class="chart">
      <svg
        class="chart-svg"
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label={`Perfil de altimetría de ${stageName}`}
      >
        <!-- Líneas de msnm -->
        {#each gridLines as line (line.label)}
          <line x1={PAD_L} y1={line.y} x2={W - PAD_R} y2={line.y} class="grid-line" />
          <text x={PAD_L - 8} y={line.y + 3.5} class="grid-label" text-anchor="end">
            {line.label}
          </text>
        {/each}

        <!-- Silueta -->
        <path d={areaPath} class="profile-area" />
        <path d={tracePath} class="profile-line" />

        <!-- Checkpoints -->
        {#each checkpointMarks as mark (mark.checkpoint.name)}
          <line
            x1={xOf(mark.point.km)}
            y1={PAD_T}
            x2={xOf(mark.point.km)}
            y2={PAD_T + PLOT_H}
            class="checkpoint-line"
          />
          <circle cx={xOf(mark.point.km)} cy={yOf(mark.point.ele)} r="4" class="checkpoint-dot" />
          <text
            x={xOf(mark.point.km)}
            y={PAD_T + PLOT_H + 16}
            class="checkpoint-label"
            text-anchor="middle"
          >
            {mark.checkpoint.name}
          </text>
        {/each}

        <!-- Puertos: la categoría en la caja, el nombre en columna vertical -->
        {#each summits as summit, summitIndex (summit.name + summit.distance_km)}
          {@const summitPoint = points.reduce((best, point) =>
            Math.abs(point.km - summit.distance_km) < Math.abs(best.km - summit.distance_km)
              ? point
              : best
          )}
          {@const tier = summitIndex % 3}
          {@const boxY = PAD_T - 78 + tier * 26}
          {@const flip = xOf(summitPoint.km) > W * 0.62}
          <line
            x1={xOf(summitPoint.km)}
            y1={yOf(summitPoint.ele)}
            x2={xOf(summitPoint.km)}
            y2={boxY + 18}
            class="summit-line"
            stroke={categoryColor(summit.category)}
          />
          <rect
            x={xOf(summitPoint.km) - 13}
            y={boxY + 2}
            width="26"
            height="17"
            class="summit-box"
            fill={categoryColor(summit.category)}
          />
          <text
            x={xOf(summitPoint.km)}
            y={boxY + 14}
            class="summit-category"
            text-anchor="middle"
            fill={categoryColor(summit.category)}
          >
            {categoryLabel(summit.category)}
          </text>
          <text
            x={flip ? xOf(summitPoint.km) + 18 : xOf(summitPoint.km) - 18}
            y={boxY + 8}
            class="summit-label"
            text-anchor={flip ? 'start' : 'end'}
          >
            {summit.name}
          </text>
          <text
            x={flip ? xOf(summitPoint.km) + 18 : xOf(summitPoint.km) - 18}
            y={boxY + 21}
            class="summit-meta"
            text-anchor={flip ? 'start' : 'end'}
          >
            {summit.distance_km.toFixed(1)} KM · {Math.round(summit.elevation_m)} M · +{summit.climb_gain_m} M
          </text>
        {/each}

        <!-- Cursor del kilometer activo -->
        {#if activePoint}
          <line
            x1={xOf(activePoint.km)}
            y1={PAD_T}
            x2={xOf(activePoint.km)}
            y2={PAD_T + PLOT_H}
            class="cursor-line"
          />
          <circle cx={xOf(activePoint.km)} cy={yOf(activePoint.ele)} r="4.5" class="cursor-dot" />
        {/if}
      </svg>

      <!-- Eje de kilometraje -->
      <div class="km-axis font-mono">
        {#each kmTicks as tick (tick.label)}
          <span class="km-tick" style={`left: ${(tick.x / W) * 100}%`}>{tick.label}</span>
        {/each}
      </div>
    </div>

    <div class="profile-controls">
      <input
        type="range"
        min="0"
        max={profile?.distance_km ?? 0}
        step="0.1"
        bind:value={activeKm}
        class="km-slider"
        aria-label="Kilómetro del recorrido"
      />
      <div class="profile-readout font-mono">
        {#if activePoint}
          KM {activePoint.km.toFixed(1)} // {Math.round(activePoint.ele)} MSNM
        {/if}
      </div>
    </div>

    {#if profile && !profile.geometry_covers_full_stage}
      <p class="lap-note font-mono">
        [ EL PERFIL MUESTRA UNA VUELTA ({profile.distance_km} KM) — LA CARRERA SON {profile.distance_km_stage} KM ]
      </p>
    {/if}
  {:else}
    <p class="route-empty font-mono">
      [ ESTA FECHA TODAVÍA NO TIENE TRAZADO GPS PUBLICADO — EL PERFIL SE PUBLICARÁ AL
      CONFIRMAR EL RECORRIDO ]
    </p>
  {/if}

  {#if gpxUrl}
    <div class="gpx-download-bar">
      <a href={gpxUrl} download class="btn-gpx-download font-mono">
        DESCARGAR TRACK GPX OFICIAL // {stageName} ↓
      </a>
    </div>
  {/if}
</div>

<style>
  .route-profile {
    border: var(--hairline, 1px) solid var(--line, rgba(16, 16, 20, 0.16));
    background: var(--bg-raised, #ffffff);
    margin-block: 2rem;
  }

  .route-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 1rem;
    padding: 1rem 1.5rem;
    border-bottom: var(--hairline, 1px) solid var(--line, rgba(16, 16, 20, 0.16));
    background: var(--bg, #fbfbfd);
  }

  .route-title {
    font-size: 0.75rem;
    font-weight: 800;
    letter-spacing: 0.12em;
    color: var(--accent, #ff5500);
  }

  .route-metrics {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem 1.25rem;
    font-size: 0.6875rem;
    color: var(--muted, #70707c);
  }

  .route-metrics strong {
    color: var(--ink, #101014);
  }

  .route-scale {
    padding: 0.1rem 0.4rem;
    border: var(--hairline, 1px) solid var(--line-strong, rgba(16, 16, 20, 0.4));
    color: var(--ink, #101014);
  }

  .chart {
    position: relative;
    padding: 1.5rem 1.5rem 0.5rem;
  }

  .chart-svg {
    display: block;
    width: 100%;
    height: auto;
  }

  /* Retícula de msnm */
  .grid-line {
    stroke: var(--line, rgba(16, 16, 20, 0.16));
    stroke-width: 1;
    vector-effect: non-scaling-stroke;
  }

  .grid-label {
    fill: var(--faint, rgba(16, 16, 20, 0.42));
    font-family: var(--font-mono, monospace);
    font-size: 10px;
    font-variant-numeric: tabular-nums;
  }

  /* Silueta */
  .profile-area {
    fill: var(--accent, #2d81ff);
    fill-opacity: 0.2;
  }

  .profile-line {
    fill: none;
    stroke: var(--accent, #2d81ff);
    stroke-width: 1.6;
    stroke-linejoin: round;
    vector-effect: non-scaling-stroke;
  }

  /* Checkpoints */
  .checkpoint-line {
    stroke: var(--line-strong, rgba(16, 16, 20, 0.4));
    stroke-width: 1;
    stroke-dasharray: 3 3;
    vector-effect: non-scaling-stroke;
  }

  .checkpoint-dot {
    fill: var(--bg-raised, #ffffff);
    stroke: var(--ink, #101014);
    stroke-width: 1.4;
    vector-effect: non-scaling-stroke;
  }

  .checkpoint-label {
    fill: var(--muted, #70707c);
    font-family: var(--font-mono, monospace);
    font-size: 9px;
    letter-spacing: 0.04em;
  }

  /* Puertos */
  .summit-line {
    stroke-width: 1;
    stroke-dasharray: 2 2;
    vector-effect: non-scaling-stroke;
  }

  .summit-box {
    stroke: none;
  }

  .summit-category {
    font-family: var(--font-mono, monospace);
    font-size: 10px;
    font-weight: 700;
  }

  .summit-label {
    fill: var(--ink, #101014);
    font-family: var(--font-display, sans-serif);
    font-size: 12px;
    font-weight: 620;
  }

  .summit-meta {
    fill: var(--faint, rgba(16, 16, 20, 0.42));
    font-family: var(--font-mono, monospace);
    font-size: 9px;
    font-variant-numeric: tabular-nums;
  }

  /* Cursor */
  .cursor-line {
    stroke: var(--ink, #101014);
    stroke-width: 1;
    stroke-opacity: 0.45;
    vector-effect: non-scaling-stroke;
  }

  .cursor-dot {
    fill: var(--ink, #101014);
    stroke: var(--bg-raised, #ffffff);
    stroke-width: 1.6;
    vector-effect: non-scaling-stroke;
  }

  /* Eje de kilometraje */
  .km-axis {
    position: relative;
    height: 1.25rem;
    margin-top: 0.25rem;
    font-size: 0.625rem;
    color: var(--faint, rgba(16, 16, 20, 0.42));
    font-variant-numeric: tabular-nums;
  }

  .km-tick {
    position: absolute;
    transform: translateX(-50%);
  }

  .profile-controls {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 0.5rem 1.5rem 1rem;
  }

  .km-slider {
    flex: 1;
    accent-color: var(--accent, #ff5500);
    cursor: pointer;
  }

  .profile-readout {
    flex: 0 0 auto;
    font-size: 0.6875rem;
    color: var(--ink, #101014);
    font-variant-numeric: tabular-nums;
  }

  .lap-note {
    margin: 0;
    padding: 0.75rem 1.5rem;
    border-top: var(--hairline, 1px) solid var(--line, rgba(16, 16, 20, 0.16));
    font-size: 0.625rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--muted, #70707c);
  }

  .route-empty {
    margin: 0;
    padding: 2.5rem 1.5rem;
    font-size: 0.6875rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--muted, #70707c);
    background: var(--bg, #fbfbfd);
  }

  .gpx-download-bar {
    padding: 1rem 1.5rem;
    background: var(--bg, #fbfbfd);
    border-top: var(--hairline, 1px) solid var(--line, rgba(16, 16, 20, 0.16));
    text-align: center;
  }

  .btn-gpx-download {
    display: inline-block;
    padding: 0.75rem 1.5rem;
    background: var(--invert-bg, #101014);
    color: var(--invert-fg, #ffffff);
    text-decoration: none;
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    transition: background 0.15s ease;
  }

  .btn-gpx-download:hover {
    background: var(--accent, #ff5500);
    color: #ffffff;
  }

  .font-mono {
    font-family: var(--font-mono, monospace);
    font-variant-numeric: tabular-nums;
  }
</style>
