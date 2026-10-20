<script lang="ts">
  /**
   * RouteMapGpx.svelte — el mapa y el perfil de una ruta.
   *
   * Dibuja la geometría REAL de la carrera (`Stage.route_geojson`, que la BD
   * guarda ya simplificada a ≤500 puntos) proyectada sobre un lienzo SVG, con
   * los checkpoints de la fecha (Partida, intermedios, Meta) y un perfil de
   * altimetría sincronizado con el cursor.
   *
   * Nada de lo que se ve está inventado: si la fecha no tiene geometría, el
   * componente lo dice en vez de fabricar una silueta.
   */
  import type { Checkpoint, RouteGeoJson } from '../../lib/api';

  interface Props {
    stageName: string;
    routeGeoJson: RouteGeoJson | null;
    checkpoints: Checkpoint[];
    distanceKm: number;
    elevationGainM: number;
    gpxUrl?: string;
  }

  let { stageName, routeGeoJson, checkpoints, distanceKm, elevationGainM, gpxUrl }: Props = $props();

  /** Un punto de la traza, ya normalizado a un lienzo de 100 × 100. */
  interface ProjectedPoint {
    /** Coordenada en el lienzo (0..100). */
    x: number;
    y: number;
    /** Kilómetro del recorrido. */
    km: number;
    /** Altitud en metros. */
    ele: number;
  }

  let activeKm = $state(0);

  /**
   * Proyecta la geometría a un lienzo conservando la proporción real del
   * circuito (un circuito de MTB no se deforma) y dejando un margen del 6%.
   *
   * El lienzo se dimensiona con la proporción de la traza: un circuito
   * alargado no tiene que dejar el 60% del alto vacío.
   */
  let projection = $derived.by(() => {
    const coords = routeGeoJson?.features?.[0]?.geometry?.coordinates ?? [];
    if (coords.length < 2) return { points: [] as ProjectedPoint[], width: 100, height: 100 };

    const lons = coords.map((c) => c[0]);
    const lats = coords.map((c) => c[1]);
    const minLon = Math.min(...lons);
    const maxLon = Math.max(...lons);
    const minLat = Math.min(...lats);
    const maxLat = Math.max(...lats);

    const spanLon = maxLon - minLon || 1e-9;
    const spanLat = maxLat - minLat || 1e-9;
    // Un grado de longitud a esta latitud es más corto que uno de latitud:
    // se compensa para no deformar el circuito.
    const latScale = Math.cos((minLat * Math.PI) / 180) || 1;
    const spanX = spanLon * latScale;
    const spanY = spanLat;

    const margin = 6;
    // Se escala para que la dimensión dominante ocupe el lienzo, y el alto
    // del lienzo se deriva de la proporción real de la traza.
    const scale = (100 - margin * 2) / Math.max(spanX, spanY);
    const width = spanX * scale + margin * 2;
    const height = spanY * scale + margin * 2;

    const points = coords.map((c) => {
      const lon = c[0];
      const lat = c[1];
      const ele = c[2] ?? 0;
      const km = c[3] ?? 0;
      return {
        x: margin + (lon - minLon) * latScale * scale,
        y: height - margin - (lat - minLat) * scale,
        km,
        ele,
      };
    });

    return { points, width, height };
  });

  let projected = $derived(projection.points);

  /** La traza como un `d` de SVG. */
  let tracePath = $derived(
    projected.length > 0
      ? `M ${projected.map((p) => `${p.x.toFixed(2)},${p.y.toFixed(2)}`).join(' L ')}`
      : ''
  );

  /** El perfil de altimetría, normalizado a su propio alto. */
  let elevationPath = $derived.by(() => {
    if (projected.length < 2) return { area: '', line: '', min: 0, max: 0 };
    const eles = projected.map((p) => p.ele);
    const min = Math.min(...eles);
    const max = Math.max(...eles);
    const range = max - min || 1;
    const maxKm = projected[projected.length - 1].km || 1;

    const points = projected.map((p) => {
      const x = (p.km / maxKm) * 100;
      const y = 92 - ((p.ele - min) / range) * 82;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    });

    return {
      area: `M 0,100 L ${points.join(' L ')} L 100,100 Z`,
      line: `M ${points.join(' L ')}`,
      min,
      max,
    };
  });

  /** El punto de la traza más cercano al kilómetro activo. */
  let activePoint = $derived.by(() => {
    if (projected.length === 0) return null;
    const totalKm = projected[projected.length - 1].km || distanceKm || 1;
    const target = (activeKm / (distanceKm || totalKm)) * totalKm;
    let best = projected[0];
    let bestDist = Math.abs(best.km - target);
    for (const p of projected) {
      const d = Math.abs(p.km - target);
      if (d < bestDist) {
        bestDist = d;
        best = p;
      }
    }
    return best;
  });

  /** El punto de un checkpoint, localizado en la traza por su kilómetro. */
  function checkpointPoint(cp: Checkpoint): ProjectedPoint | null {
    if (projected.length === 0) return null;
    const totalKm = projected[projected.length - 1].km || 1;
    const targetKm = (cp.distance_from_start_km / (distanceKm || totalKm)) * totalKm;
    let best = projected[0];
    let bestDist = Math.abs(best.km - targetKm);
    for (const p of projected) {
      const d = Math.abs(p.km - targetKm);
      if (d < bestDist) {
        bestDist = d;
        best = p;
      }
    }
    return best;
  }

  let hasGeometry = $derived(projected.length > 1);
</script>

<div class="route-map-box">
  <div class="route-header">
    <div class="route-title font-mono">[ PERFIL TÉCNICO Y RUTA DE CARRERA ]</div>
    <div class="route-metrics font-mono">
      <span>DISTANCIA: <strong>{distanceKm} KM</strong></span>
      <span>DESNIVEL (+): <strong>+{elevationGainM} M</strong></span>
    </div>
  </div>

  {#if hasGeometry}
    <!-- Mapa: la traza real de la carrera -->
    <div
      class="map-visual"
      style={`--map-ratio: ${projection.width.toFixed(2)} / ${projection.height.toFixed(2)}`}
    >
      <svg
        class="map-svg"
        viewBox={`0 0 ${projection.width.toFixed(2)} ${projection.height.toFixed(2)}`}
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label={`Trazado de la ruta de ${stageName}`}
      >
        <path d={tracePath} class="trace" />
        {#each checkpoints as cp (cp.name)}
          {@const p = checkpointPoint(cp)}
          {#if p}
            <g class="chk">
              <circle cx={p.x} cy={p.y} r="1.6" class="chk__dot" />
              <text
                x={p.x}
                y={p.y - (projection.height * 0.035 + 1)}
                class="chk__label"
                text-anchor="middle">{cp.name}</text>
            </g>
          {/if}
        {/each}
        {#if activePoint}
          <circle cx={activePoint.x} cy={activePoint.y} r="1.4" class="active-dot" />
        {/if}
      </svg>
      <div class="map-tag font-mono">[ TRAZADO GPS OFICIAL // {stageName} ]</div>
    </div>

    <!-- Altimetría: el mismo recorrido en vertical -->
    <div class="elevation-profile-box">
      <div class="elev-label font-mono">[ DESLIZAR PARA INSPECCIONAR SECTOR, ALTITUD Y PENDIENTE ]</div>

      <svg
        class="elev-svg"
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        role="img"
        aria-label={`Perfil de altimetría de ${stageName}`}
      >
        <path d={elevationPath.area} class="elev-area" />
        <path d={elevationPath.line} class="elev-line" />
        {#if activePoint}
          {@const maxKm = projected[projected.length - 1].km || 1}
          {@const x = (activePoint.km / maxKm) * 100}
          {@const range = elevationPath.max - elevationPath.min || 1}
          {@const y = 92 - ((activePoint.ele - elevationPath.min) / range) * 82}
          <line x1={x} y1="4" x2={x} y2="100" class="elev-cursor" />
          <circle cx={x} cy={y} r="1.6" class="elev-dot" />
        {/if}
      </svg>

      <div class="slider-wrapper">
        <input
          type="range"
          min="0"
          max={distanceKm}
          step="0.1"
          bind:value={activeKm}
          class="elev-slider"
          aria-label="Kilómetro del recorrido"
        />
      </div>

      <div class="elev-axis font-mono">
        <span>0.0 KM [PARTIDA]</span>
        <span>{(distanceKm / 2).toFixed(1)} KM [MEDIO]</span>
        <span>{distanceKm.toFixed(1)} KM [META]</span>
      </div>

      <div class="elev-readout font-mono">
        KM {activeKm.toFixed(1)} // {activePoint ? Math.round(activePoint.ele) : 0} MSNM
        {#if activePoint && projected.length > 0}
          // {activePoint.ele >= projected[0].ele ? '+' : ''}{Math.round(activePoint.ele - projected[0].ele)} M RESPECTO A LA PARTIDA
        {/if}
      </div>
    </div>
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
  .route-map-box {
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
    gap: 1.5rem;
    font-size: 0.75rem;
    color: var(--muted, #70707c);
  }

  .route-metrics strong {
    color: var(--ink, #101014);
  }

  /* Mapa */
  .map-visual {
    position: relative;
    /* La altura la fija la proporción real de la traza: un circuito alargado
       no tiene que dejar medio lienzo vacío. */
    aspect-ratio: var(--map-ratio, 4 / 3);
    min-height: 14rem;
    max-height: 32rem;
    background: #0d0f12;
    background-image: radial-gradient(rgba(255, 255, 255, 0.07) 1px, transparent 1px);
    background-size: 1.5rem 1.5rem;
    overflow: hidden;
  }

  .map-svg {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
  }

  .trace {
    fill: none;
    stroke: #ff5500;
    stroke-width: 1.1;
    stroke-linejoin: round;
    stroke-linecap: round;
    vector-effect: non-scaling-stroke;
  }

  .chk__dot {
    fill: #ffffff;
    stroke: #ff5500;
    stroke-width: 0.5;
    vector-effect: non-scaling-stroke;
  }

  .chk__label {
    fill: rgba(255, 255, 255, 0.75);
    font-family: var(--font-mono, monospace);
    font-size: 1.1px;
    letter-spacing: 0.04em;
    paint-order: stroke;
    stroke: rgba(13, 15, 18, 0.85);
    stroke-width: 0.28px;
  }

  .active-dot {
    fill: #ffffff;
    stroke: #ff5500;
    stroke-width: 0.7;
    vector-effect: non-scaling-stroke;
  }

  .map-tag {
    position: absolute;
    top: 1rem;
    left: 1.5rem;
    font-size: 0.625rem;
    color: rgba(255, 255, 255, 0.5);
    letter-spacing: 0.14em;
    z-index: 2;
  }

  /* Altimetría */
  .elevation-profile-box {
    padding: 1.25rem 1.5rem;
    border-top: var(--hairline, 1px) solid var(--line, rgba(16, 16, 20, 0.16));
  }

  .elev-label {
    font-size: 0.625rem;
    letter-spacing: 0.12em;
    color: var(--muted, #70707c);
    margin-bottom: 0.75rem;
  }

  .elev-svg {
    display: block;
    width: 100%;
    height: 7rem;
    background: var(--bg, #fbfbfd);
    border: var(--hairline, 1px) solid var(--line, rgba(16, 16, 20, 0.16));
  }

  .elev-area {
    fill: rgba(255, 85, 0, 0.16);
  }

  .elev-line {
    fill: none;
    stroke: #ff5500;
    stroke-width: 1;
    vector-effect: non-scaling-stroke;
  }

  .elev-cursor {
    stroke: rgba(16, 16, 20, 0.35);
    stroke-width: 0.4;
    vector-effect: non-scaling-stroke;
  }

  .elev-dot {
    fill: #ff5500;
    stroke: #ffffff;
    stroke-width: 0.5;
    vector-effect: non-scaling-stroke;
  }

  .slider-wrapper {
    margin-block: 0.75rem 0.5rem;
  }

  .elev-slider {
    width: 100%;
    accent-color: #ff5500;
    cursor: pointer;
  }

  .elev-axis {
    display: flex;
    justify-content: space-between;
    font-size: 0.6875rem;
    color: var(--muted, #70707c);
  }

  .elev-readout {
    margin-top: 0.5rem;
    font-size: 0.6875rem;
    color: var(--ink, #101014);
    font-variant-numeric: tabular-nums;
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
    background: #ff5500;
    color: #ffffff;
  }

  .font-mono {
    font-family: var(--font-mono, monospace);
    font-variant-numeric: tabular-nums;
  }
</style>
