<script lang="ts">
  interface RiderStanding {
    standing_id: number;
    rider_id: number;
    rider_name: string;
    rider_slug: string;
    team_name: string;
    team_slug: string | null;
    category_id: number;
    category_name: string;
    current_rank: number;
    previous_rank: number | null;
    rank_delta: number;
    total_points: number;
    first_places_count: number;
    total_elapsed_ms: number;
    formatted_total_time: string;
    stages_completed: number;
  }

  interface TeamStanding {
    team_id: number;
    team_name: string;
    team_slug: string;
    logo_url: string | null;
    current_rank: number;
    previous_rank: number | null;
    rank_delta: number;
    total_points: number;
    first_places: number;
    second_places: number;
    third_places: number;
    total_riders: number;
    total_elapsed_ms: number;
    formatted_total_time: string;
  }

  interface CategoryItem {
    id: number;
    name: string;
    short_code: string;
  }

  interface Props {
    initialIndividual?: RiderStanding[];
    initialTeams?: TeamStanding[];
    categories?: CategoryItem[];
  }

  let { initialIndividual = [], initialTeams = [], categories = [] }: Props = $props();

  // Estados reactivos con Runes ($state)
  let activeTab = $state<'individual' | 'teams'>('individual');
  let selectedCategory = $state<string>('TODAS');
  let searchQuery = $state<string>('');

  // Filtros derivados reactivos ($derived)
  let filteredIndividual = $derived(
    initialIndividual.filter((r) => {
      const matchCat =
        selectedCategory === 'TODAS' ||
        r.category_name.toUpperCase().includes(selectedCategory.toUpperCase()) ||
        selectedCategory.toUpperCase().includes(r.category_name.toUpperCase());
      const query = searchQuery.toLowerCase().trim();
      const matchQuery =
        !query ||
        r.rider_name.toLowerCase().includes(query) ||
        r.team_name.toLowerCase().includes(query);
      return matchCat && matchQuery;
    })
  );

  let filteredTeams = $derived(
    initialTeams.filter((t) => {
      const query = searchQuery.toLowerCase().trim();
      return !query || t.team_name.toLowerCase().includes(query);
    })
  );
</script>

<div class="standings-box">
  <!-- Selector de Pestañas Principal -->
  <div class="tab-bar">
    <button
      class="tab-btn"
      class:is-active={activeTab === 'individual'}
      onclick={() => (activeTab = 'individual')}
    >
      Clasificación Individual
    </button>
    <button
      class="tab-btn"
      class:is-active={activeTab === 'teams'}
      onclick={() => (activeTab = 'teams')}
    >
      Copa de Equipos
    </button>
  </div>

  <!-- Barra de Filtros y Buscador -->
  <div class="filter-bar">
    {#if activeTab === 'individual'}
      <div class="cat-select-wrapper">
        <label for="cat-select" class="sr-only">Filtrar por Categoría</label>
        <select id="cat-select" bind:value={selectedCategory} class="cat-select">
          <option value="TODAS">TODAS LAS CATEGORÍAS</option>
          {#each categories as cat}
            <option value={cat.name}>{cat.name}</option>
          {/each}
        </select>
      </div>
    {/if}

    <div class="search-input-wrapper">
      <input
        type="search"
        placeholder={activeTab === 'individual' ? 'Buscar ciclista o club...' : 'Buscar equipo...'}
        bind:value={searchQuery}
        class="search-input"
      />
    </div>
  </div>

  <!-- Tabla Individual -->
  {#if activeTab === 'individual'}
    <div class="table-scroll">
      <table class="data-table">
        <thead>
          <tr>
            <th class="col-rank">Puesto</th>
            <th class="col-delta">Delta</th>
            <th>Ciclista</th>
            <th>Categoría</th>
            <th>Equipo / Club</th>
            <th class="col-num">Puntos</th>
            <th class="col-num">Victorias</th>
            <th class="col-num">Tiempo Neto</th>
          </tr>
        </thead>
        <tbody>
          {#if filteredIndividual.length === 0}
            <tr>
              <td colspan="8" class="empty-cell">No se encontraron corredores con los criterios seleccionados.</td>
            </tr>
          {:else}
            {#each filteredIndividual as rider}
              <tr>
                <td class="col-rank font-mono">{rider.current_rank}°</td>
                <td class="col-delta">
                  {#if rider.rank_delta > 0}
                    <span class="delta-up font-mono">▲ +{rider.rank_delta}</span>
                  {:else if rider.rank_delta < 0}
                    <span class="delta-down font-mono">▼ {rider.rank_delta}</span>
                  {:else}
                    <span class="delta-eq font-mono">=</span>
                  {/if}
                </td>
                <td>
                  <a href={`/corredor/${rider.rider_slug}`} class="rider-link">
                    {rider.rider_name}
                  </a>
                </td>
                <td><span class="badge-cat">{rider.category_name}</span></td>
                <td>
                  {#if rider.team_slug}
                    <a href={`/equipos/${rider.team_slug}`} class="team-link">{rider.team_name}</a>
                  {:else}
                    <span class="team-free">{rider.team_name}</span>
                  {/if}
                </td>
                <td class="col-num font-mono points-highlight">{rider.total_points} pts</td>
                <td class="col-num font-mono">{rider.first_places_count}</td>
                <td class="col-num font-mono time-mono">{rider.formatted_total_time}</td>
              </tr>
            {/each}
          {/if}
        </tbody>
      </table>
    </div>
  {:else}
    <!-- Tabla Equipos -->
    <div class="table-scroll">
      <table class="data-table">
        <thead>
          <tr>
            <th class="col-rank">Puesto</th>
            <th class="col-delta">Delta</th>
            <th>Equipo / Club</th>
            <th class="col-num">Puntos</th>
            <th class="col-num">Oros (1°)</th>
            <th class="col-num">Platas (2°)</th>
            <th class="col-num">Bronces (3°)</th>
            <th class="col-num">Corredores</th>
          </tr>
        </thead>
        <tbody>
          {#if filteredTeams.length === 0}
            <tr>
              <td colspan="8" class="empty-cell">No se encontraron equipos registrados.</td>
            </tr>
          {:else}
            {#each filteredTeams as team}
              <tr>
                <td class="col-rank font-mono">{team.current_rank}°</td>
                <td class="col-delta">
                  {#if team.rank_delta > 0}
                    <span class="delta-up font-mono">▲ +{team.rank_delta}</span>
                  {:else if team.rank_delta < 0}
                    <span class="delta-down font-mono">▼ {team.rank_delta}</span>
                  {:else}
                    <span class="delta-eq font-mono">=</span>
                  {/if}
                </td>
                <td>
                  <a href={`/equipos/${team.team_slug}`} class="rider-link">
                    {team.team_name}
                  </a>
                </td>
                <td class="col-num font-mono points-highlight">{team.total_points} pts</td>
                <td class="col-num font-mono medal-gold">{team.first_places}</td>
                <td class="col-num font-mono medal-silver">{team.second_places}</td>
                <td class="col-num font-mono medal-bronze">{team.third_places}</td>
                <td class="col-num font-mono">{team.total_riders}</td>
              </tr>
            {/each}
          {/if}
        </tbody>
      </table>
    </div>
  {/if}
</div>

<style>
  .standings-box {
    border: var(--hairline, 1px) solid var(--line, rgba(16, 16, 20, 0.16));
    background: var(--bg-raised, #ffffff);
    margin-block: 2rem;
  }

  .tab-bar {
    display: flex;
    border-bottom: var(--hairline, 1px) solid var(--line, rgba(16, 16, 20, 0.16));
  }

  .tab-btn {
    flex: 1;
    padding: 1rem 1.5rem;
    background: transparent;
    border: none;
    border-right: var(--hairline, 1px) solid var(--line, rgba(16, 16, 20, 0.16));
    font-family: inherit;
    font-size: 0.75rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: var(--muted, #70707c);
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .tab-btn:last-child {
    border-right: none;
  }

  .tab-btn.is-active {
    background: var(--invert-bg, #101014);
    color: var(--invert-fg, #ffffff);
  }

  .filter-bar {
    display: flex;
    flex-wrap: wrap;
    gap: 1rem;
    padding: 1rem;
    border-bottom: var(--hairline, 1px) solid var(--line, rgba(16, 16, 20, 0.16));
    background: var(--bg, #fbfbfd);
  }

  .cat-select,
  .search-input {
    padding: 0.625rem 1rem;
    font-size: 0.8125rem;
    border: var(--hairline, 1px) solid var(--line, rgba(16, 16, 20, 0.16));
    background: var(--bg-raised, #ffffff);
    color: var(--ink, #101014);
    border-radius: 0;
    outline: none;
  }

  .search-input {
    flex: 1;
    min-width: 240px;
  }

  .table-scroll {
    overflow-x: auto;
  }

  .data-table {
    width: 100%;
    border-collapse: collapse;
    text-align: left;
    font-size: 0.8125rem;
  }

  .data-table th {
    padding: 0.75rem 1rem;
    font-size: 0.6875rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--muted, #70707c);
    border-bottom: var(--hairline, 1px) solid var(--line, rgba(16, 16, 20, 0.16));
    background: var(--bg, #fbfbfd);
  }

  .data-table td {
    padding: 0.75rem 1rem;
    border-bottom: var(--hairline, 1px) solid var(--line, rgba(16, 16, 20, 0.16));
  }

  .font-mono {
    font-family: var(--font-mono, monospace);
    font-variant-numeric: tabular-nums;
  }

  .col-rank {
    width: 60px;
    font-weight: 800;
  }

  .col-delta {
    width: 70px;
    text-align: center;
  }

  .col-num {
    text-align: right;
  }

  .delta-up {
    color: #10b981;
    font-weight: 700;
  }

  .delta-down {
    color: #ef4444;
    font-weight: 700;
  }

  .delta-eq {
    color: var(--muted, #70707c);
  }

  .rider-link,
  .team-link {
    color: var(--ink, #101014);
    text-decoration: none;
    font-weight: 600;
  }

  .rider-link:hover,
  .team-link:hover {
    color: var(--accent, #ff5500);
  }

  .badge-cat {
    display: inline-block;
    padding: 0.2rem 0.5rem;
    font-size: 0.6875rem;
    background: var(--bg, #fbfbfd);
    border: var(--hairline, 1px) solid var(--line, rgba(16, 16, 20, 0.16));
    letter-spacing: 0.05em;
  }

  .points-highlight {
    font-weight: 800;
    color: var(--ink, #101014);
  }

  .empty-cell {
    text-align: center;
    padding: 3rem;
    color: var(--muted, #70707c);
  }

  .sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    border: 0;
  }
</style>
