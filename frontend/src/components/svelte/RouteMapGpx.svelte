<script lang="ts">
  interface Props {
    stageName: string;
    distanceKm: number;
    elevationGainM: number;
    gpxUrl?: string;
  }

  let { stageName, distanceKm, elevationGainM, gpxUrl }: Props = $props();

  let activeDistance = $state<number>(0);
  let hoveredElev = $derived(
    Math.round(2300 + Math.sin(activeDistance / 10) * 450 + (activeDistance / distanceKm) * elevationGainM * 0.4)
  );
</script>

<div class="route-map-box">
  <div class="route-header">
    <div class="route-title">Ruta Oficial y Perfil Altimétrico</div>
    <div class="route-metrics font-mono">
      <span>Distancia: <strong>{distanceKm} km</strong></span>
      <span>Desnivel (+): <strong>+{elevationGainM} m</strong></span>
    </div>
  </div>

  <!-- Contenedor del Mapa Estilizado Oscuro -->
  <div class="map-visual">
    <div class="map-overlay">
      <div class="map-tag font-mono">MAPA INTERACTIVO TOPO MTB</div>
      <div class="map-marker" style={`left: ${Math.min(95, Math.max(5, (activeDistance / distanceKm) * 100))}%;`}>
        <div class="marker-dot"></div>
        <div class="marker-tooltip font-mono">KM {activeDistance.toFixed(1)} ({hoveredElev} msnm)</div>
      </div>
    </div>
  </div>

  <!-- Gráfico de Altimetría Interactivo -->
  <div class="elevation-profile-box">
    <div class="elev-label font-mono">PERFIL DE ELEVACIÓN (DESLIZAR PARA INSPECCIONAR SUBIDA)</div>
    <div class="slider-wrapper">
      <input
        type="range"
        min="0"
        max={distanceKm}
        step="0.5"
        bind:value={activeDistance}
        class="elev-slider"
      />
    </div>
    <div class="elev-axis font-mono">
      <span>0 km (Partida)</span>
      <span>{(distanceKm / 2).toFixed(1)} km (Cumbre)</span>
      <span>{distanceKm} km (Meta)</span>
    </div>
  </div>

  {#if gpxUrl}
    <div class="gpx-download-bar">
      <a href={gpxUrl} download class="btn-gpx-download font-mono">
        📥 DESCARGAR ARCHIVO GPX OFICIAL ({stageName})
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
    font-size: 0.875rem;
    font-weight: 800;
    letter-spacing: 0.08em;
    text-transform: uppercase;
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

  .map-visual {
    position: relative;
    height: 320px;
    background: #14171c;
    background-image: radial-gradient(rgba(255, 255, 255, 0.08) 1px, transparent 1px);
    background-size: 24px 24px;
    overflow: hidden;
  }

  .map-overlay {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
  }

  .map-tag {
    position: absolute;
    top: 1rem;
    left: 1.5rem;
    font-size: 0.625rem;
    color: rgba(255, 255, 255, 0.6);
    letter-spacing: 0.12em;
  }

  .map-marker {
    position: absolute;
    top: 45%;
    transform: translate(-50%, -50%);
    display: flex;
    flex-direction: column;
    align-items: center;
    transition: left 0.1s ease-out;
  }

  .marker-dot {
    width: 14px;
    height: 14px;
    background: #ff5500;
    border: 2px solid #ffffff;
    box-shadow: 0 0 12px rgba(255, 85, 0, 0.8);
  }

  .marker-tooltip {
    margin-top: 0.5rem;
    padding: 0.25rem 0.5rem;
    background: #000000;
    color: #ffffff;
    font-size: 0.6875rem;
    white-space: nowrap;
    border: 1px solid rgba(255, 255, 255, 0.2);
  }

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

  .slider-wrapper {
    margin-block: 0.5rem;
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
    margin-top: 0.5rem;
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
    letter-spacing: 0.1em;
  }

  .btn-gpx-download:hover {
    background: #ff5500;
  }

  .font-mono {
    font-family: var(--font-mono, monospace);
    font-variant-numeric: tabular-nums;
  }
</style>
