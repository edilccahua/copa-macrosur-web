<script lang="ts">
  interface Props {
    stageName: string;
    distanceKm: number;
    elevationGainM: number;
    gpxUrl?: string;
  }

  let { stageName, distanceKm, elevationGainM, gpxUrl }: Props = $props();

  interface TrackPoint {
    distKm: number;
    ele: number;
    lat: number;
    lon: number;
  }

  let points = $state<TrackPoint[]>([]);
  let activeDistance = $state<number>(0);

  // Haversine simple para parseo cliente
  function haversine(lat1: number, lon1: number, lat2: number, lon2: number): number {
    const R = 6371;
    const dLat = ((lat2 - lat1) * Math.PI) / 180;
    const dLon = ((lon2 - lon1) * Math.PI) / 180;
    const a =
      Math.sin(dLat / 2) * Math.sin(dLat / 2) +
      Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLon / 2) * Math.sin(dLon / 2);
    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  }

  $effect(() => {
    if (!gpxUrl) return;
    fetch(gpxUrl)
      .then((res) => res.text())
      .then((xmlStr) => {
        const parser = new DOMParser();
        const xml = parser.parseFromString(xmlStr, 'application/xml');
        const trkpts = xml.querySelectorAll('trkpt');
        if (trkpts.length === 0) return;

        const parsed: TrackPoint[] = [];
        let totalD = 0;
        let lastPt: { lat: number; lon: number } | null = null;

        trkpts.forEach((pt) => {
          const lat = parseFloat(pt.getAttribute('lat') || '0');
          const lon = parseFloat(pt.getAttribute('lon') || '0');
          const ele = parseFloat(pt.querySelector('ele')?.textContent || '0');

          if (lastPt) {
            totalD += haversine(lastPt.lat, lastPt.lon, lat, lon);
          }
          parsed.push({ distKm: totalD, ele: Math.round(ele), lat, lon });
          lastPt = { lat, lon };
        });

        // Muestrear a máx 100 puntos para SVG suave
        const step = Math.max(1, Math.floor(parsed.length / 100));
        points = parsed.filter((_, i) => i % step === 0);
      })
      .catch(() => {});
  });

  // Punto activo interpolado
  let activePoint = $derived.by(() => {
    if (points.length === 0) {
      return {
        distKm: activeDistance,
        ele: Math.round(2300 + Math.sin(activeDistance / 10) * 450 + (activeDistance / Math.max(1, distanceKm)) * elevationGainM * 0.4),
        pct: (activeDistance / Math.max(1, distanceKm)) * 100
      };
    }
    const maxD = points[points.length - 1].distKm;
    const targetD = (activeDistance / Math.max(1, distanceKm)) * maxD;
    const closest = points.reduce((prev, curr) =>
      Math.abs(curr.distKm - targetD) < Math.abs(prev.distKm - targetD) ? curr : prev
    );
    return {
      distKm: activeDistance,
      ele: closest.ele,
      pct: (activeDistance / Math.max(1, distanceKm)) * 100
    };
  });

  // SVG path de elevación
  let svgPath = $derived.by(() => {
    if (points.length === 0) return '';
    const minEle = Math.min(...points.map((p) => p.ele));
    const maxEle = Math.max(...points.map((p) => p.ele));
    const eleRange = maxEle - minEle || 1;
    const maxD = points[points.length - 1].distKm || 1;

    const coords = points.map((p) => {
      const x = (p.distKm / maxD) * 100;
      const y = 90 - ((p.ele - minEle) / eleRange) * 75;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    });

    return `M 0,95 L ${coords.join(' L ')} L 100,95 Z`;
  });
</script>

<div class="route-map-box">
  <div class="route-header">
    <div class="route-title font-mono">[ PERFIL TÉCNICO Y ALTIMETRÍA GPX ]</div>
    <div class="route-metrics font-mono">
      <span>DISTANCIA: <strong>{distanceKm} KM</strong></span>
      <span>DESNIVEL (+): <strong>+{elevationGainM} M</strong></span>
    </div>
  </div>

  <!-- Contenedor del Mapa Estilizado Oscuro -->
  <div class="map-visual">
    <div class="map-overlay">
      <div class="map-tag font-mono">[ TELEMETRÍA DE CARRERA // VISUALIZADOR TOPO ]</div>

      {#if svgPath}
        <svg class="elev-svg" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
          <path d={svgPath} class="elev-polygon" />
        </svg>
      {/if}

      <div class="map-marker" style={`left: ${Math.min(96, Math.max(4, activePoint.pct))}%;`}>
        <div class="marker-line"></div>
        <div class="marker-dot"></div>
        <div class="marker-tooltip font-mono">
          KM {activeDistance.toFixed(1)} // {activePoint.ele} MSNM
        </div>
      </div>
    </div>
  </div>

  <!-- Gráfico de Altimetría Interactivo -->
  <div class="elevation-profile-box">
    <div class="elev-label font-mono">[ DESLIZAR CURSOR PARA INSPECCIONAR SECTOR Y GRADIENTE ]</div>
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
      <span>0.0 KM [PARTIDA]</span>
      <span>{(distanceKm / 2).toFixed(1)} KM [SECTOR CUMBRE]</span>
      <span>{distanceKm.toFixed(1)} KM [META]</span>
    </div>
  </div>

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

  .map-visual {
    position: relative;
    height: 20rem;
    background: #0d0f12;
    background-image: radial-gradient(rgba(255, 255, 255, 0.08) 1px, transparent 1px);
    background-size: 1.5rem 1.5rem;
    overflow: hidden;
  }

  .map-overlay {
    position: absolute;
    inset: 0;
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

  .elev-svg {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    z-index: 1;
  }

  .elev-polygon {
    fill: rgba(255, 85, 0, 0.18);
    stroke: #ff5500;
    stroke-width: 1.5;
  }

  .map-marker {
    position: absolute;
    top: 0;
    bottom: 0;
    transform: translateX(-50%);
    display: flex;
    flex-direction: column;
    align-items: center;
    z-index: 3;
    pointer-events: none;
    transition: left 0.05s ease-out;
  }

  .marker-line {
    flex: 1;
    width: 1px;
    background: rgba(255, 255, 255, 0.3);
  }

  .marker-dot {
    width: 0.625rem;
    height: 0.625rem;
    background: #ff5500;
    border: 2px solid #ffffff;
    box-shadow: 0 0 0.625rem rgba(255, 85, 0, 0.8);
  }

  .marker-tooltip {
    margin-top: 0.5rem;
    margin-bottom: 1.5rem;
    padding: 0.25rem 0.625rem;
    background: #000000;
    color: #ffffff;
    font-size: 0.6875rem;
    white-space: nowrap;
    border: 1px solid rgba(255, 255, 255, 0.2);
    letter-spacing: 0.05em;
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
