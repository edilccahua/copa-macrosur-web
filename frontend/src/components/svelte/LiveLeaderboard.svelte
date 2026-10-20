<script lang="ts">
  import { API_V1 } from '../../lib/api';

  interface LeaderboardRow {
    entry_id: number;
    bib_number: number;
    rider_name: string;
    team_name: string;
    category_name: string;
    elapsed_ms: number;
    formatted_time: string;
    category_rank: number;
    points_earned: number;
    just_finished?: boolean;
  }

  interface Props {
    stageId: number;
    stageName?: string;
  }

  let { stageId, stageName = 'Carrera en Vivo' }: Props = $props();

  /**
   * Estado de la conexión. Antes sólo había "conectado" y "no conectado", y
   * el estado inicial caía en el segundo: la página arrancaba SIEMPRE
   * diciendo "RECONECTANDO" (un error que no existía) hasta que el
   * `EventSource` abría.
   */
  type ConnState = 'conectando' | 'vivo' | 'reconectando';

  let connState = $state<ConnState>('conectando');
  let rows = $state<LeaderboardRow[]>([]);
  let lastEventMsg = $state<string>('Conectando a la central de cronometraje...');

  async function loadSnapshot() {
    try {
      const res = await fetch(`${API_V1}/stages/${stageId}/live-summary`);
      if (res.ok) {
        const data = await res.json();
        rows = data.leaderboard || [];
        lastEventMsg = `Snapshot inicial sincronizado (${rows.length} ciclistas en meta).`;
      }
    } catch (e) {
      console.warn('Fallo al obtener snapshot inicial', e);
    }
  }

  $effect(() => {
    loadSnapshot();

    const url = `${API_V1}/stages/${stageId}/stream`;
    const eventSource = new EventSource(url);

    eventSource.onopen = () => {
      connState = 'vivo';
      lastEventMsg = 'Canal SSE activo. Esperando marcaciones de meta...';
    };

    eventSource.addEventListener('timing-update', (event) => {
      try {
        const payload = JSON.parse(event.data);
        lastEventMsg = `Meta cruzada: #${payload.bib_number} ${payload.rider_name} (${payload.formatted_time})`;

        // Buscar si ya existe la fila
        const existingIdx = rows.findIndex((r) => r.bib_number === payload.bib_number);
        const newRow: LeaderboardRow = {
          entry_id: payload.stage_entry_id || Date.now(),
          bib_number: payload.bib_number,
          rider_name: payload.rider_name,
          team_name: payload.team_name,
          category_name: payload.category_name,
          elapsed_ms: payload.elapsed_ms,
          formatted_time: payload.formatted_time,
          category_rank: payload.provisional_category_rank || 1,
          points_earned: 0,
          just_finished: true
        };

        if (existingIdx >= 0) {
          rows[existingIdx] = newRow;
        } else {
          rows.unshift(newRow);
        }

        // El resalte se apaga pasado un momento. IMPORTANTE: hay que leer la
        // fila POR EL PROXY (`rows[i]`), no mutar el objeto crudo: el proxy
        // es lo que avisa a la vista, y mutar el original no dispara nada
        // (el resalte se quedaba puesto para siempre).
        const rowIndex = rows.findIndex((r) => r.bib_number === payload.bib_number);
        setTimeout(() => {
          if (rowIndex >= 0 && rows[rowIndex]) {
            rows[rowIndex].just_finished = false;
          }
        }, 4000);
      } catch (err) {
        console.error('Error parseando SSE', err);
      }
    });

    eventSource.addEventListener('wave-started', (event) => {
      try {
        const payload = JSON.parse(event.data);
        lastEventMsg = `Manga largada: ${payload.wave_name}`;
      } catch (e) {}
    });

    eventSource.onerror = () => {
      connState = 'reconectando';
      lastEventMsg = 'Reconectando con la central de cronometraje...';
    };

    return () => {
      eventSource.close();
    };
  });
</script>

<div class="live-leaderboard">
  <div class="live-status-bar">
    <div class="status-indicator">
      <span class="live-dot" class:is-live={connState === 'vivo'}></span>
      <span class="status-text">
        {connState === 'vivo'
          ? 'TRANSMISIÓN EN VIVO'
          : connState === 'conectando'
            ? 'CONECTANDO'
            : 'RECONECTANDO'}
      </span>
    </div>
    <div class="event-ticker font-mono">{lastEventMsg}</div>
  </div>

  <div class="table-wrap">
    <table class="live-table">
      <thead>
        <tr>
          <th class="col-rank">Puesto</th>
          <th class="col-bib">Dorsal</th>
          <th>Ciclista</th>
          <th>Categoría</th>
          <th>Club / Team</th>
          <th class="col-time">Tiempo Oficial</th>
        </tr>
      </thead>
      <tbody>
        {#if rows.length === 0}
          <tr>
            <td colspan="6" class="waiting-cell font-mono">
              Esperando el primer corredor en cruzar la línea de meta...
            </td>
          </tr>
        {:else}
          {#each rows as row (row.bib_number)}
            <tr class:highlight-row={row.just_finished}>
              <td class="col-rank font-mono">{row.category_rank}°</td>
              <td class="col-bib font-mono bib-tag">#{row.bib_number}</td>
              <td class="rider-name-cell">{row.rider_name}</td>
              <td><span class="badge-cat">{row.category_name}</span></td>
              <td class="team-cell">{row.team_name}</td>
              <td class="col-time font-mono time-bold">{row.formatted_time}</td>
            </tr>
          {/each}
        {/if}
      </tbody>
    </table>
  </div>
</div>

<style>
  .live-leaderboard {
    border: var(--hairline, 1px) solid var(--line, rgba(16, 16, 20, 0.16));
    background: var(--bg-raised, #ffffff);
    margin-block: 2rem;
  }

  .live-status-bar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    padding: 1rem 1.5rem;
    background: var(--bg, #fbfbfd);
    border-bottom: var(--hairline, 1px) solid var(--line, rgba(16, 16, 20, 0.16));
  }

  .status-indicator {
    display: flex;
    align-items: center;
    gap: 0.625rem;
  }

  .live-dot {
    width: 0.625rem;
    height: 0.625rem;
    background: #70707c;
    display: inline-block;
  }

  .live-dot.is-live {
    background: #ff3b30;
    box-shadow: 0 0 0.5rem rgba(255, 59, 48, 0.6);
    animation: pulse 1.5s infinite;
  }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
  }

  .status-text {
    font-size: 0.6875rem;
    font-weight: 800;
    letter-spacing: 0.15em;
    color: var(--ink, #101014);
  }

  .event-ticker {
    font-size: 0.75rem;
    color: var(--muted, #70707c);
  }

  .font-mono {
    font-family: var(--font-mono, monospace);
    font-variant-numeric: tabular-nums;
  }

  .table-wrap {
    overflow-x: auto;
  }

  .live-table {
    width: 100%;
    border-collapse: collapse;
    text-align: left;
    font-size: 0.8125rem;
  }

  .live-table th {
    padding: 0.75rem 1.25rem;
    font-size: 0.6875rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--muted, #70707c);
    border-bottom: var(--hairline, 1px) solid var(--line, rgba(16, 16, 20, 0.16));
    background: var(--bg, #fbfbfd);
  }

  .live-table td {
    padding: 0.875rem 1.25rem;
    border-bottom: var(--hairline, 1px) solid var(--line, rgba(16, 16, 20, 0.16));
  }

  .highlight-row {
    background: rgba(255, 85, 0, 0.08);
    animation: flash 1s ease-out;
  }

  @keyframes flash {
    0% { background: rgba(255, 85, 0, 0.3); }
    100% { background: rgba(255, 85, 0, 0.08); }
  }

  .col-rank {
    width: 4.375rem;
    font-weight: 800;
  }

  .col-bib {
    width: 5rem;
  }

  .bib-tag {
    font-weight: 800;
    color: var(--ink, #101014);
  }

  .col-time {
    text-align: right;
    width: 8.125rem;
  }

  .time-bold {
    font-weight: 800;
    font-size: 0.9375rem;
  }

  .badge-cat {
    display: inline-block;
    padding: 0.2rem 0.5rem;
    font-size: 0.6875rem;
    background: var(--bg, #fbfbfd);
    border: var(--hairline, 1px) solid var(--line, rgba(16, 16, 20, 0.16));
  }

  .waiting-cell {
    text-align: center;
    padding: 4rem 1rem;
    color: var(--muted, #70707c);
  }
</style>
