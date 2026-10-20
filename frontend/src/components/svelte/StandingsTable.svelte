<!--
  StandingsTable.svelte — Clasificación oficial del campeonato.

  Patrón de navegación tomado de letour.fr/es/clasificaciones:
    · Selector de FECHA (casi escondido): la clasificación es el ACUMULADO
      "a la fecha" elegida.
    · Pestañas de grupo de categorías: PRO · NORMAL · E-BIKE, separadas por una
      regla de la Copa de EQUIPOS. Control segmentado: grupo con borde de 1px,
      celdas separadas por hairline y la celda activa invertida.
    · Selector de CATEGORÍA (casi escondido) dentro de la pestaña: "COMBINADO"
      agrupa las categorías de esa pestaña; una categoría concreta aísla su
      clasificación.
    · Tabla con Puesto, Δ contra la fecha anterior, Ciclista, Categoría, puesto
      en su categoría, Equipo, Tiempo acumulado, Diferencia al líder y Puntos.

  Color: UNO por vista (el del grupo activo) para el marco; el Δ usa colores
  SEMÁNTICOS (verde/rojo) porque informa de ranking, no de estilo; el podio se
  distingue con oro/plata/bronce.
-->
<script lang="ts">
  import { flip } from 'svelte/animate';
  import { fade } from 'svelte/transition';
  import { cubicOut } from 'svelte/easing';
  import ScopeControl from './ScopeControl.svelte';
  import {
    getStandings,
    unpackStandingsRows,
    unpackTeamStandingsRows,
    type StandingsContext,
    type StandingsRow,
    type TeamStandingRow,
  } from '../../lib/api';

  /**
   * Modo de la clasificación (patrón Tour de Francia):
   * - "acumulado": la suma de todo lo disputado hasta la fecha de corte.
   * - "fecha": solo la carrera elegida (sin acumulado y sin DELTA).
   */
  type Mode = 'acumulado' | 'fecha';
  type Kind = 'individual' | 'teams';

  interface Props {
    context: StandingsContext;
    /**
     * Las filas viajan COLUMNADAS: un JSON compacto (la primera fila son los
     * nombres de los campos y cada fila, sus valores). El HTML de la página
     * lleva así ~25 KB de props en vez de ~90 KB; `unpackStandingsRows` las
     * devuelve como objetos y la tabla no se entera.
     */
    initialRows: string;
    initialTeams: string;
    initialStageId: number | null;
    initialScope: string;
    initialCategoryId: number | null;
    /** Modo inicial; por defecto "acumulado". */
    initialMode?: Mode;
    /** Tabla inicial: "individual" o "teams" (Copa de Equipos). */
    initialKind?: Kind;
  }

  let {
    context,
    initialRows,
    initialTeams,
    initialStageId,
    initialScope,
    initialCategoryId,
    initialMode = 'acumulado',
    initialKind = 'individual',
  }: Props = $props();

  type ScopeKey = 'PRO' | 'NORMAL' | 'E-BIKE';

  /**
   * `mode` es el modo PEDIDO (el de la pestaña activa) y `tableMode` el que la
   * tabla DIBUJA. Se separan a propósito: la estructura de la tabla (la columna
   * Δ, el navegador de fechas) solo puede cambiar en el MISMO update que traen
   * los datos. Si cambiara antes, la animación `flip` de las filas se
   * interrumpiría al llegar los datos y dejaría filas pegadas en posición
   * absoluta, amontonadas sobre las nuevas.
   */
  let mode = $state<Mode>(initialMode);
  let tableMode = $state<Mode>(initialMode);
  let stageId = $state<number | null>(initialStageId);
  let scope = $state<ScopeKey>(normalizeScopeKey(initialScope));
  let categoryId = $state<number | null>(initialCategoryId);
  let kind = $state<Kind>(initialKind);
  let search = $state('');

  let rows = $state<StandingsRow[]>(unpackStandingsRows(initialRows));
  let teamRows = $state<TeamStandingRow[]>(unpackTeamStandingsRows(initialTeams));
  let meta = $state<StandingsContext>(context);
  let loading = $state(false);
  let error = $state<string | null>(null);

  /**
   * Las fechas disponibles salen del CONTEXTO (que es lo que la API devuelve
   * con cada respuesta): la página ya no las pasa como una prop aparte, que
   * era el mismo array duplicado dentro del HTML.
   */
  let stages = $derived(meta.stages);

  /**
   * Clave de la vista. La construye UNA sola función para que el valor
   * inicial y el del efecto tengan EXACTAMENTE el mismo formato: antes el
   * inicial tenía 4 segmentos y el del efecto 5, así que nunca coincidían y
   * la tabla volvía a pedir los datos que el servidor ya había entregado
   * (doble fetch y barra de progreso sobre contenido ya pintado).
   */
  function buildKey(
    m: Mode,
    s: number | null,
    sc: string,
    cat: number | null,
    k: Kind
  ): string {
    return `${m}|${s ?? ''}|${sc}|${cat ?? ''}|${k}`;
  }

  let lastKey = $state(
    buildKey(initialMode, initialStageId, initialScope, initialCategoryId, initialKind)
  );

  // Ancla para el <tbody> (evita variable implícita en `bind:this`).
  let tbodyEl = $state<HTMLElement | null>(null);

  // --- Indicador deslizante de las pestañas --------------------------------
  // Una "pastilla" invertida dentro de cada grupo que se desplaza hasta la
  // celda activa: la selección se ve moverse en vez de saltar de golpe.
  // La posición la calcula CSS puro a partir de `data-active` y de los anchos
  // fijos de cada pestaña: medirla con JavaScript obligaba a esperar al ciclo
  // de render y la pastilla aparecía tarde (o no aparecía) en pestañas de
  // segundo plano.

  /**
   * El tiempo medio mezcla categorías (un ELITE a 1:08 y un MASTER D a 1:50):
   * es un dato de contexto, no un récord. Se explica en el tooltip.
   */
  const AVG_TIME_HINT =
    'Media de los tiempos de los que cerraron. Mezcla categorías (un ELITE a 1:08 y un MASTER D a 1:50): ' +
    'es un dato de contexto, no un récord. El tiempo del ganador está en la tabla, arriba.';

  let stats = $derived(
    meta.stats ?? { participants: 0, finishers: 0, non_finishers: 0, avg_time_ms: null }
  );

  let avgTime = $derived(
    stats.avg_time_ms != null ? formatMs(stats.avg_time_ms) : '—'
  );

  function formatMs(ms: number): string {
    const total = Math.round(ms / 1000);
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = total % 60;
    const pad = (n: number) => String(n).padStart(2, '0');
    return h > 0 ? `${pad(h)}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
  }

  const GAP_HINT =
    'Diferencia de tiempo acumulado respecto al líder de la vista actual (ordenada por puntos). ' +
    'En COMBINADO puede ser negativa si acumulaste menos tiempo con menos puntos. ' +
    'Para comparar contra el líder de tu propia categoría, filtra por esa categoría.';

  // --- Datos -----------------------------------------------------------------

  $effect(() => {
    const key = buildKey(mode, stageId, scope, categoryId, kind);
    if (key === lastKey) return;
    lastKey = key;
    void load(key);
  });

  async function load(key: string) {
    loading = true;
    error = null;
    const [md, s, sc, cat, kd] = key.split('|');
    try {
      const res = await getStandings({
        mode: md as Mode,
        stage: s ? Number(s) : null,
        scope: sc as string,
        categoryId: cat ? Number(cat) : null,
        kind: kd as Kind,
      });
      // Si el usuario cambió algo mientras cargaba, esta respuesta es vieja.
      if (key !== lastKey) return;
      if (kd === 'teams') {
        teamRows = res.rows as TeamStandingRow[];
      } else {
        rows = res.rows as StandingsRow[];
      }
      meta = res.context;
      // El modo se aplica AQUÍ, con los datos: un solo update, una sola
      // animación, sin filas pegadas.
      tableMode = md as Mode;
    } catch (e) {
      if (key !== lastKey) return;
      error = 'No se pudo cargar la clasificación. Reintenta en unos segundos.';
      tableMode = md as Mode;
    } finally {
      if (key === lastKey) loading = false;
    }
  }

  // --- Identidad -------------------------------------------------------------

  /**
   * Las pestañas de ámbito. La etiqueta es CORTA (el ancho es escaso): el
   * E-BIKE va como "E-BIKE" y su forma larga, "E-BIKE OPEN", se reserva para
   * los rótulos con sitio (la cinta de la tabla).
   */
  const SCOPES: { key: ScopeKey; label: string }[] = [
    { key: 'PRO', label: 'PRO' },
    { key: 'NORMAL', label: 'NORMAL' },
    { key: 'E-BIKE', label: 'E-BIKE' },
  ];

  const SCOPE_CLASS: Record<string, string> = {
    PRO: 'scope-pro',
    NORMAL: 'scope-normal',
    'E-BIKE': 'scope-ebike',
  };

  // --- Opciones de los selectores --------------------------------------------

  /** El selector ofrece "COMBINADO" (las categorías de la pestaña) y cada una. */
  let categoryOptions = $derived([
    { value: 'TODOS', label: 'TODOS', meta: '' },
    ...(meta.groups[scope] ?? []).map((code) => {
      const cat = meta.categories.find((c) => c.short_code === code);
      return { value: code, label: cat?.name ?? code, meta: '' };
    }),
  ]);

  let activeStage = $derived(stages.find((s) => s.id === stageId));
  let stageIndex = $derived(stages.findIndex((s) => s.id === stageId));
  let prevStage = $derived(stageIndex > 0 ? stages[stageIndex - 1] : null);
  let nextStage = $derived(
    stageIndex >= 0 && stageIndex < stages.length - 1 ? stages[stageIndex + 1] : null
  );

  // --- Acciones --------------------------------------------------------------

  /**
   * Normaliza el ámbito que llega del servidor o de la URL. El E-BIKE se
   * llamaba antes "E-MTB": los enlaces viejos siguen funcionando.
   */
  function normalizeScopeKey(value: string | null | undefined): ScopeKey {
    const key = (value ?? '').toUpperCase();
    if (key === 'E-MTB') return 'E-BIKE';
    if (key === 'NORMAL') return 'NORMAL';
    if (key === 'E-BIKE') return 'E-BIKE';
    return 'PRO';
  }

  /**
   * Si la URL trae el nombre viejo del ámbito, se reescribe con el vigente
   * para que el enlace que se copia y comparte ya no lleve el nombre former.
   */
  $effect(() => {
    const current = new URLSearchParams(location.search).get('tabla');
    if (!current || current.toUpperCase() !== 'E-MTB') return;
    const params = new URLSearchParams(location.search);
    params.set('tabla', 'E-BIKE');
    history.replaceState(null, '', `${location.pathname}?${params.toString()}`);
  });

  function setScope(next: ScopeKey) {
    scope = next;
    categoryId = null;
    urlTouched = true;
  }

  function setMode(next: Mode) {
    if (next === mode) return;
    mode = next;
    urlTouched = true;
  }

  /** Cambia de fecha (modo "fecha"): el navegador de fechas del Tour. */
  function stepStage(delta: number) {
    const target = delta < 0 ? prevStage : nextStage;
    if (!target) return;
    stageId = target.id;
    urlTouched = true;
  }

  /**
   * La vista se escribe en la URL para que sea compartible: al abrirla de
   * nuevo (o al enlazarla) vuelve al mismo modo, pestaña, categoría y fecha.
   * Solo se escribe después de una interacción del usuario.
   */
  let urlTouched = $state(false);

  $effect(() => {
    void mode;
    void scope;
    void categoryId;
    void stageId;
    void kind;
    if (!urlTouched) return;
    const params = new URLSearchParams();
    params.set('modo', mode);
    params.set('tabla', kind === 'teams' ? 'EQUIPO' : scope);
    const cat = meta.categories.find((c) => c.id === categoryId);
    if (cat) params.set('categoria', cat.short_code);
    const st = stages.find((x) => x.id === stageId);
    if (st) params.set('fecha', String(st.stage_number));
    history.replaceState(null, '', `${location.pathname}?${params.toString()}`);
  });

  /** El titulo sigue al modo: "Ranking general acumulado" <-> "Clasificacion de la fecha". */
  let titleMain = $derived(tableMode === 'acumulado' ? 'Ranking general' : 'Clasificación');
  let titleWord = $derived(tableMode === 'acumulado' ? 'acumulado' : 'de la fecha');

  function setCategory(code: string) {
    urlTouched = true;
    if (code === 'TODOS') {
      categoryId = null;
      return;
    }
    const cat = meta.categories.find((c) => c.short_code === code);
    categoryId = cat ? cat.id : null;
  }

  let activeCategoryLabel = $derived(
    categoryId != null
      ? (meta.categories.find((c) => c.id === categoryId)?.name ?? '')
      : ''
  );

  /**
   * Rótulo de la cinta: qué categorías muestra la tabla. Aquí sí hay sitio,
   * así que el ámbito va con su nombre LARGO (el E-BIKE se llama "E-BIKE
   * OPEN", igual que su categoría).
   */
  let scopeLabel = $derived(
    kind === 'teams'
      ? 'COPA DE EQUIPOS'
      : (categoryId != null
          ? activeCategoryLabel
          : (meta.scope_labels_long[scope] ?? scope))
  );

  // --- Filtrado por búsqueda -------------------------------------------------

  let filteredRows = $derived(
    rows.filter((r) => {
      const q = search.trim().toLowerCase();
      if (!q) return true;
      return (
        r.rider_name.toLowerCase().includes(q) ||
        r.team_name.toLowerCase().includes(q) ||
        r.category_name.toLowerCase().includes(q)
      );
    })
  );

  let filteredTeams = $derived(
    teamRows.filter((t) => {
      const q = search.trim().toLowerCase();
      return !q || t.team_name.toLowerCase().includes(q);
    })
  );

  function stageDate(iso: string): string {
    return new Date(iso + 'T00:00:00')
      .toLocaleDateString('es-PE', { day: '2-digit', month: 'short', year: 'numeric' })
      .toUpperCase();
  }
</script>

<div class="standings {kind === 'teams' ? 'scope-team' : SCOPE_CLASS[scope]}">
  <!--
    Cabecera de la vista: el rótulo del campeonato, el titulo (que cambia con
    el modo) y las cifras de lo que se esta viendo, TODO en la misma linea.
    La cabecera la lleva el componente porque las cifras dependen de la vista
    activa (ambito y categoria) y del modo.
  -->
  <header class="standhead">
    <div class="standhead__title">
      <div class="standhead__crumb font-mono">COPA MACROSUR MTB 2026 / CLASIFICACIÓN OFICIAL</div>
      <h1 class="standhead__h1">
        {titleMain} <em>{titleWord}</em>
      </h1>
    </div>

    <!-- Cifras de lo que se esta viendo (la carrera o la ventana acumulada). -->
    <div class="figures">
      <span class="figure">
        <span class="figure__label font-mono">Participantes</span>
        <span class="figure__num font-mono">{stats.participants}</span>
      </span>
      <span class="figure">
        <span class="figure__label font-mono">Finalizaron</span>
        <span class="figure__num font-mono">{stats.finishers}</span>
      </span>
      <span class="figure">
        <span class="figure__label font-mono">No finalizaron</span>
        <span class="figure__num font-mono">{stats.non_finishers}</span>
      </span>
      <span class="figure" title={AVG_TIME_HINT}>
        <span class="figure__label font-mono">Tiempo medio</span>
        <span class="figure__num font-mono">{avgTime}</span>
      </span>
    </div>
  </header>

  <!--
    Cabecera FUERA de la caja, patrón Tour de Francia: primero la etapa (con
    flechas para recorrer las fechas) y debajo las pestañas de modo. El
    navegador de fechas es el ÚNICO selector de fecha y funciona en los dos
    modos: en "acumulado" marca el corte (HASTA FECHA N) y en "fecha" la
    carrera que se está viendo.
  -->
  {#if activeStage}
    <div class="stagehead">
      <button
        type="button"
        class="stagehead__nav"
        onclick={() => stepStage(-1)}
        disabled={!prevStage}
        aria-label="FECHA ANTERIOR"
      >
        <svg width="14" height="14" viewBox="0 0 10 10" aria-hidden="true">
          <path d="M6.5 1 L3 5 L6.5 9" fill="none" stroke="currentColor" stroke-width="1.6" />
        </svg>
      </button>
      <div class="stagehead__id">
        <span class="stagehead__num font-mono">
          {tableMode === 'acumulado' ? 'HASTA FECHA' : 'FECHA'} {activeStage?.stage_number ?? ''}
        </span>
        {#if activeStage}
          <span class="stagehead__meta font-mono">{stageDate(activeStage.date)}</span>
        {/if}
        <span class="stagehead__name font-mono">
          {activeStage?.name.replace(/^Fecha\s+\d+\s*:\s*/i, '').toUpperCase() ?? ''}
        </span>
      </div>
      <button
        type="button"
        class="stagehead__nav"
        onclick={() => stepStage(1)}
        disabled={!nextStage}
        aria-label="FECHA SIGUIENTE"
      >
        <svg width="14" height="14" viewBox="0 0 10 10" aria-hidden="true">
          <path d="M3.5 1 L7 5 L3.5 9" fill="none" stroke="currentColor" stroke-width="1.6" />
        </svg>
      </button>
    </div>
  {/if}

  <!-- Pestañas de modo: FECHA (una carrera) | ACUMULADO (hasta el corte) -->
  <nav class="modes" role="tablist" aria-label="Modo de clasificación">
    <button
      type="button"
      role="tab"
      class="mode font-mono"
      class:is-active={mode === 'fecha'}
      aria-selected={mode === 'fecha'}
      onclick={() => setMode('fecha')}
    >
      FECHA
    </button>
    <button
      type="button"
      role="tab"
      class="mode font-mono"
      class:is-active={mode === 'acumulado'}
      aria-selected={mode === 'acumulado'}
      onclick={() => setMode('acumulado')}
    >
      ACUMULADO
    </button>
  </nav>

  <div class="rank">
  <!-- Cinta: qué muestra la tabla y hasta cuándo -->
  <div class="ribbon">
    <div class="ribbon__id">
      <span class="ribbon__label font-mono">CATEGORÍAS</span>
      <span class="ribbon__name font-mono">{scopeLabel}</span>
    </div>
    <div class="ribbon__meta font-mono">
      {#if tableMode === 'fecha'}
        FECHA {activeStage?.stage_number ?? ''} · {meta.total_distance_km.toFixed(2)} KM
        {#if activeStage}· {stageDate(activeStage.date)}{/if}
      {:else}
        {meta.stages_counted} {meta.stages_counted === 1 ? 'FECHA' : 'FECHAS'}
        DISPUTADAS · {meta.total_distance_km.toFixed(2)} KM
        {#if activeStage}· CORTE {stageDate(activeStage.date)}{/if}
      {/if}
    </div>

  </div>

  <!-- Barra de pestañas y filtros -->
  <div class="rank__controls">
    <div class="tabs" role="tablist" aria-label="Grupo de categorías">
      <div class="tabs__group" data-active={kind === 'individual' ? scope : 'none'}>
        <span class="tabs__pill" aria-hidden="true"></span>
        {#each SCOPES as s (s.key)}
          <button
            type="button"
            role="tab"
            class="tab font-mono"
            data-tab={s.key}
            class:is-active={kind === 'individual' && scope === s.key}
            aria-selected={kind === 'individual' && scope === s.key}
            onclick={() => {
              kind = 'individual';
              setScope(s.key);
            }}
          >
            {s.label}
          </button>
        {/each}
      </div>

      <div class="tabs__group" data-active={kind === 'teams' ? 'teams' : 'none'}>
        <span class="tabs__pill" aria-hidden="true"></span>
        <button
          type="button"
          role="tab"
          class="tab font-mono"
          data-tab="teams"
          class:is-active={kind === 'teams'}
          aria-selected={kind === 'teams'}
          onclick={() => (kind = 'teams')}
        >
          EQUIPO
        </button>
      </div>
    </div>

    <div class="rank__filters">
      {#if kind === 'individual'}
        <div class="ctl ctl--cat">
          <ScopeControl
            options={categoryOptions}
            value={categoryId != null
              ? (meta.categories.find((c) => c.id === categoryId)?.short_code ?? 'TODOS')
              : 'TODOS'}
            label="CATEGORÍA"
            onchange={setCategory}
          />
        </div>
      {/if}

      <div class="search">
        <input
          type="search"
          class="search__input font-mono"
          placeholder={kind === 'teams' ? 'Buscar equipo...' : 'Buscar ciclista o club...'}
          bind:value={search}
          aria-label="Buscar en la clasificación"
        />
      </div>
    </div>
  </div>

  {#if error}
    <p class="rank__error font-mono">{error}</p>
  {/if}

  <!-- Cuerpo de las tablas: la línea de progreso no ocupa sitio (cero layout shift) -->
  <div class="rank__body">
    {#if loading}<span class="rank__progress" aria-hidden="true"></span>{/if}

  <!-- Tabla individual -->
  {#if kind === 'individual'}
    <div class="table-scroll">
      <table class="dt">
        <thead>
          <tr>
            <th class="col-rank">Puesto</th>
            {#if tableMode === 'acumulado'}<th class="col-delta">Δ</th>{/if}
            <th>Ciclista</th>
            <th class="col-cat">Categoría</th>
            <th class="col-catrank">En cat.</th>
            <th class="col-team">Equipo / Club</th>
            <th class="col-time">{tableMode === 'acumulado' ? 'Tiempo Acum.' : 'Tiempo'}</th>
            <th class="col-gap" title={GAP_HINT}>Diferencia</th>
            <th class="col-pts">Puntos</th>
          </tr>
        </thead>
        <tbody bind:this={tbodyEl}>
          {#if filteredRows.length === 0}
            <tr>
              <td colspan={tableMode === 'acumulado' ? 9 : 8} class="empty font-mono">
                No se encontraron corredores con los criterios seleccionados.
              </td>
            </tr>
          {:else}
            {#each filteredRows as r (r.rider_id)}
              <tr
                animate:flip={{ duration: 320, easing: cubicOut }}
                transition:fade={{ duration: 150 }}
                class:row-p1={r.current_rank === 1}
                class:row-p2={r.current_rank === 2}
                class:row-p3={r.current_rank === 3}
              >
                <td class="col-rank font-mono">
                  <span class="rankbox rankbox--{r.current_rank <= 3 ? `p${r.current_rank}` : 'plain'}">
                    {r.current_rank}º
                  </span>
                </td>
                {#if tableMode === 'acumulado'}
                  <td class="col-delta">
                    {#if r.is_debut}
                      <span class="delta-new font-mono">NUEVO</span>
                    {:else if r.rank_delta > 0}
                      <span class="delta-up font-mono">▲ {r.rank_delta}</span>
                    {:else if r.rank_delta < 0}
                      <span class="delta-down font-mono">▼ {Math.abs(r.rank_delta)}</span>
                    {:else if r.previous_rank == null}
                      <span class="delta-eq font-mono">—</span>
                    {:else}
                      <span class="delta-eq font-mono">=</span>
                    {/if}
                  </td>
                {/if}
                <td class="col-name">
                  <span class="name-wrap">
                    <a href={`/corredor/${r.rider_slug}`} class="rider-link">{r.rider_name}</a>
                    <span class="cell-sub font-mono">
                      <span class="cell-cat">{r.category_name}</span>
                      <span class="cell-team">
                        {#if r.team_slug}
                          <a href={`/equipos/${r.team_slug}`}>{r.team_name}</a>
                        {:else}
                          {r.team_name}
                        {/if}
                      </span>
                    </span>
                  </span>
                </td>
                <td class="col-cat">
                  <span class="badge-cat font-mono">{r.category_name}</span>
                </td>
                <td class="col-catrank font-mono catrank">{r.category_rank}º</td>
                <td class="col-team">
                  {#if r.team_slug}
                    <a href={`/equipos/${r.team_slug}`} class="team-link">{r.team_name}</a>
                  {:else}
                    <span class="team-free">{r.team_name}</span>
                  {/if}
                </td>
                <td class="col-time font-mono time">{r.formatted_total_time}</td>
                <td
                  class="col-gap font-mono gap"
                  class:is-negative={r.gap_to_leader_ms < 0}
                  title={r.gap_to_leader_ms < 0 ? GAP_HINT : undefined}
                >
                  {r.formatted_gap}
                </td>
                <td class="col-pts font-mono">
                  <span class="pts-num">{r.total_points}</span><span class="pts-unit">pts</span>
                </td>
              </tr>
            {/each}
          {/if}
        </tbody>
      </table>
    </div>
  {:else}
    <!-- Tabla de equipos -->
    <div class="table-scroll">
      <table class="dt">
        <thead>
          <tr>
            <th class="col-rank">Puesto</th>
            <th>Equipo / Club</th>
            <th class="col-pts">Puntos</th>
            <th class="col-num">Oros</th>
            <th class="col-num">Platas</th>
            <th class="col-num">Bronces</th>
            <th class="col-num">Corredores</th>
            <th class="col-time">{tableMode === 'acumulado' ? 'Tiempo Acum.' : 'Tiempo'}</th>
            <th class="col-gap" title={GAP_HINT}>Diferencia</th>
          </tr>
        </thead>
        <tbody bind:this={tbodyEl}>
          {#if filteredTeams.length === 0}
            <tr>
              <td colspan="9" class="empty font-mono">
                No se encontraron equipos registrados.
              </td>
            </tr>
          {:else}
            {#each filteredTeams as t (t.team_id)}
              <tr
                animate:flip={{ duration: 320, easing: cubicOut }}
                transition:fade={{ duration: 150 }}
                class:row-p1={t.current_rank === 1}
                class:row-p2={t.current_rank === 2}
                class:row-p3={t.current_rank === 3}
              >
                <td class="col-rank font-mono">
                  <span class="rankbox rankbox--{t.current_rank <= 3 ? `p${t.current_rank}` : 'plain'}">
                    {t.current_rank}º
                  </span>
                </td>
                <td class="col-name">
                  <span class="name-wrap">
                    <a href={`/equipos/${t.team_slug}`} class="rider-link">{t.team_name}</a>
                    <span class="cell-sub font-mono">
                      <span class="cell-stat">{t.first_places} OROS</span>
                      <span class="cell-stat">{t.second_places} PLATAS</span>
                      <span class="cell-stat">{t.third_places} BRONCES</span>
                      <span class="cell-stat cell-stat--riders">{t.total_riders} CORREDORES</span>
                    </span>
                  </span>
                </td>
                <td class="col-pts font-mono">
                  <span class="pts-num">{t.total_points}</span><span class="pts-unit">pts</span>
                </td>
                <td class="col-num font-mono">{t.first_places}</td>
                <td class="col-num font-mono">{t.second_places}</td>
                <td class="col-num font-mono">{t.third_places}</td>
                <td class="col-num font-mono">{t.total_riders}</td>
                <td class="col-time font-mono time">{t.formatted_total_time}</td>
                <td
                  class="col-gap font-mono gap"
                  class:is-negative={t.gap_to_leader_ms < 0}
                  title={t.gap_to_leader_ms < 0 ? GAP_HINT : undefined}
                >
                  {t.formatted_gap}
                </td>
              </tr>
            {/each}
          {/if}
        </tbody>
      </table>
    </div>
  {/if}
  </div>
  </div>
</div>

<style>
  .standings {
    --edge: var(--scope);
    --accent-color: var(--scope-ink, var(--accent));
    box-sizing: border-box;
    min-width: 0;
    margin-block: 1.5rem 4rem;
  }

  .rank {
    box-sizing: border-box;
    min-width: 0;
    border: var(--hairline) solid var(--line);
    background: var(--bg-raised);
  }

  /* --- Cabecera de modo (patrón Tour de Francia) ---------------------------
     Vive FUERA de la caja y es un control de VISTA, no un filtro: por eso no
     se parece al segmentado de abajo (pastilla invertida). Se lee como una
     barra de pestañas: rótulo grande y negrita, el activo con una raya de
     color del grupo que empata con el borde superior de la caja. */
  .modes {
    display: flex;
    align-items: flex-end;
    gap: 2rem;
  }

  .mode {
    position: relative;
    padding: 0.25rem 0 0.45rem;
    background: transparent;
    border: none;
    color: var(--faint);
    font-size: 0.875rem;
    font-weight: 800;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    cursor: pointer;
    transition: color var(--default-transition-duration) var(--default-transition-timing-function);
  }

  .mode:hover {
    color: var(--ink);
  }

  /* El ACTIVO se distingue por estilo, no por tamaño: toma el color del
     grupo (la señal más fuerte que hay) y lleva una raya gruesa pegada al
     texto. El inactivo se retira a --faint. */
  .mode.is-active {
    color: var(--scope-ink, var(--scope));
  }

  /* La raya del activo se posa sobre el borde de la caja: la pestaña queda
     unida a su panel (el gesto clásico de "GENERAL / CLASIFICACIÓN DE PASO"
     del Tour). */
  .mode.is-active::after {
    content: '';
    position: absolute;
    left: 0;
    right: 0;
    bottom: -1px;
    height: 4px;
    background: var(--scope-ink, var(--scope));
  }

  /* Navegador de fechas: "FECHA 2 · 23 AGO. 2026 · KÚSPIDE Z XXTREME III" */
  .stagehead {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    /* Aire con la sección de arriba: las burbujas no deben pintar contra la
       línea del título. */
    padding-top: 1.1rem;
    padding-bottom: 0.9rem;
  }

  .stagehead__nav {
    display: grid;
    place-items: center;
    width: 2.25rem;
    height: 2.25rem;
    flex: 0 0 auto;
    padding: 0;
    background: transparent;
    border: var(--hairline) solid var(--line-strong);
    border-radius: 50%;
    color: var(--ink);
    cursor: pointer;
    transition: border-color var(--default-transition-duration)
        var(--default-transition-timing-function),
      background var(--default-transition-duration) var(--default-transition-timing-function),
      color var(--default-transition-duration) var(--default-transition-timing-function);
  }

  /* Al pasar el ratón la burbuja se llena con el color del grupo y la flecha
     se invierte: el control se lee al instante. */
  .stagehead__nav:hover:not(:disabled) {
    background: var(--scope-ink, var(--scope));
    border-color: var(--scope-ink, var(--scope));
    color: var(--invert-fg);
  }

  .stagehead__nav:disabled {
    opacity: 0.28;
    cursor: default;
  }

  .stagehead__id {
    display: flex;
    align-items: baseline;
    flex-wrap: wrap;
    gap: 0.15rem 0.6rem;
    min-width: 0;
  }

  .stagehead__num {
    font-size: 1.125rem;
    font-weight: 800;
    letter-spacing: 0.04em;
    color: var(--ink-strong);
  }

  .stagehead__meta {
    font-size: 0.75rem;
    letter-spacing: 0.08em;
    color: var(--muted);
  }

  .stagehead__name {
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    color: var(--scope-ink, var(--muted));
  }

  .rank *,
  .rank *::before,
  .rank *::after {
    box-sizing: border-box;
  }

  /* --- Cinta --- */
  .ribbon {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 1.5rem;
    flex-wrap: wrap;
    padding: 0.7rem 1.25rem;
    border-bottom: var(--hairline) solid var(--line);
  }

  .ribbon__id {
    display: flex;
    align-items: baseline;
    gap: 0.6rem;
  }

  .ribbon__label {
    font-size: 0.625rem;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--faint);
  }

  .ribbon__name {
    font-size: 0.8125rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--scope-ink);
  }

  .ribbon__meta {
    font-size: 0.6875rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--muted);
  }

  /* Cabecera de la vista: rótulo del campeonato + título + cifras, en la
     MISMA línea (el título a la izquierda, las cifras a la derecha). */
  .standhead {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 0.75rem 3rem;
    padding-bottom: 1.25rem;
    border-bottom: var(--hairline) solid var(--line);
  }

  .standhead__crumb {
    font-size: 0.6875rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 0.75rem;
  }

  .standhead__h1 {
    font-family: var(--font-display, var(--font-sans));
    font-size: clamp(2rem, 4vw, 3rem);
    font-weight: 620;
    font-stretch: 118%;
    letter-spacing: -0.03em;
    line-height: 1.02;
    color: var(--ink-strong);
    text-wrap: balance;
    margin: 0;
  }

  .standhead__h1 em {
    font-family: var(--font-serif, Georgia, serif);
    font-style: italic;
    font-weight: 400;
    color: var(--accent);
  }

  /* Cifras de la carrera: la tipografía del rótulo del campeonato, no un
     titular: son datos de contexto, no otro título. */
  .figures {
    display: flex;
    flex-wrap: wrap;
    gap: 0.3rem 1.4rem;
    padding-bottom: 0.35rem;
  }

  .figure {
    display: inline-flex;
    align-items: baseline;
    gap: 0.4rem;
  }

  .figure__label {
    font-size: 0.6875rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--muted);
  }

  .figure__num {
    font-size: 0.8125rem;
    font-weight: 700;
    color: var(--ink);
    font-variant-numeric: tabular-nums;
  }

  /* --- Controles --- */
  .rank__controls {
    display: flex;
    align-items: stretch;
    justify-content: space-between;
    gap: 1.5rem;
    flex-wrap: wrap;
    border-bottom: var(--hairline) solid var(--line);
  }

  /* Control segmentado: dos grupos con borde, separados por un hueco
     deliberado. La Copa de Equipos es una clasificación distinta, no una
     categoría más. */
  .tabs {
    display: flex;
    align-items: stretch;
    gap: 0.75rem;
    min-width: 0;
    overflow-x: auto;
    scrollbar-width: none;
  }

  .tabs::-webkit-scrollbar {
    display: none;
  }

  .tabs__group {
    position: relative;
    display: flex;
    align-items: stretch;
    border: var(--hairline) solid var(--line);
    /* Anchos de las pestañas: la pastilla se posiciona con CSS puro a partir
       de estas variables (sin medición por JavaScript). En móvil se estrechan
       para que las CUATRO pestañas quepan, incluida EQUIPO. */
    --w-pro: 4.5rem;
    --w-normal: 7rem;
    --w-ebike: 6.5rem;
    --w-teams: 6.5rem;
  }

  .tab {
    /* Por DEBAJO de la pastilla: el rótulo se invierte solo donde la pastilla
       lo cubre, así que nunca queda ilegible ni al llegar ni al irse. */
    position: relative;
    z-index: 1;
    padding: 0.8rem 1.15rem;
    background: transparent;
    border: none;
    border-right: var(--hairline) solid var(--line);
    color: var(--muted);
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    cursor: pointer;
    transition: background var(--default-transition-duration) var(--default-transition-timing-function),
      color var(--default-transition-duration) var(--default-transition-timing-function),
      transform 90ms var(--default-transition-timing-function);
  }

  .tab:last-child {
    border-right: none;
  }

  .tab:hover {
    background: var(--bg-sunken);
    color: var(--ink);
  }

  .tab:active {
    transform: scale(0.98);
  }

  /* La celda activa no lleva fondo propio: lo pone la pastilla, que se
     desliza hasta ella. Su rótulo tampoco cambia de color de golpe (eso
     dejaba las pestañas ilegibles durante el desplazamiento): la inversión la
     aplica la pastilla, píxel a píxel, sobre lo que hay debajo. */
  .tab.is-active {
    background: transparent;
    color: var(--ink);
  }

  /* Anchos fijos: la pastilla se posiciona con CSS puro (sin medición JS). */
  .tab[data-tab='PRO'] { width: var(--w-pro); }
  .tab[data-tab='NORMAL'] { width: var(--w-normal); }
  .tab[data-tab='E-BIKE'] { width: var(--w-ebike); }
  .tab[data-tab='teams'] { width: var(--w-teams); }

  /* La pastilla invierte lo que hay debajo (`difference`): en tema oscuro el
     bloque queda blanco y el rótulo negro; en tema claro, al revés. Como la
     inversión depende de la POSICIÓN REAL de la pastilla, durante el
     desplazamiento los dos rótulos siguen siendo legibles: el que va saliendo
     vuelve a su color y el que va entrando se invierte poco a poco. */
  .tabs__pill {
    position: absolute;
    top: 0;
    bottom: 0;
    left: 0;
    z-index: 2;
    width: var(--w-pro);
    background: #fff;
    mix-blend-mode: difference;
    opacity: 0;
    pointer-events: none;
    transform: translateX(0);
    transition: transform 300ms var(--ease-out), width 300ms var(--ease-out),
      opacity 200ms linear;
  }

  .tabs__group[data-active='PRO'] .tabs__pill {
    width: var(--w-pro);
    transform: translateX(0);
    opacity: 1;
  }

  .tabs__group[data-active='NORMAL'] .tabs__pill {
    width: var(--w-normal);
    transform: translateX(var(--w-pro));
    opacity: 1;
  }

  .tabs__group[data-active='E-BIKE'] .tabs__pill {
    width: var(--w-ebike);
    transform: translateX(calc(var(--w-pro) + var(--w-normal)));
    opacity: 1;
  }

  .tabs__group[data-active='teams'] .tabs__pill {
    width: var(--w-teams);
    transform: translateX(0);
    opacity: 1;
  }

  .rank__filters {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 1.5rem;
    flex: 1 1 auto;
    padding: 0.7rem 1.25rem;
  }

  /* El buscador ocupa el espacio disponible: deja de ser una caja mínima. */
  .search {
    flex: 1 1 14rem;
    max-width: 24rem;
  }

  .search__input {
    width: 100%;
    padding: 0.5rem 0.75rem;
    font-size: 0.75rem;
    letter-spacing: 0.04em;
    color: var(--ink);
    background: var(--bg);
    border: var(--hairline) solid var(--line);
    border-radius: 0;
    outline: none;
  }

  .search__input:focus,
  .search__input:focus-visible {
    outline: none;
    border-color: var(--line-strong);
    box-shadow: 0 0 0 1px var(--line-strong);
  }

  .rank__body {
    position: relative;
  }

  /* Línea de progreso: absolutely positioned, no empuja el contenido. */
  .rank__progress {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 2px;
    z-index: 20;
    background: var(--scope);
    transform-origin: left center;
    animation: progress-sweep 1.1s var(--ease-in-out) infinite;
  }

  @keyframes progress-sweep {
    0% {
      transform: scaleX(0);
      opacity: 1;
    }
    70% {
      transform: scaleX(1);
      opacity: 1;
    }
    100% {
      transform: scaleX(1);
      opacity: 0;
    }
  }

  .rank__error {
    margin: 0;
    padding: 0.7rem 1.25rem;
    font-size: 0.6875rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--muted);
    border-bottom: var(--hairline) solid var(--line);
  }

  .rank__error {
    color: var(--danger);
  }

  /* --- Tabla --- */
  /* Entrada del contenido al cambiar de fecha o de ámbito: un leve alzado con
     desenfoque, al mismo ritmo que el revelado del sistema. El reordenamiento de
     las filas lo resuelve `animate:flip` (Svelte), no este keyframe. */
  @media (prefers-reduced-motion: no-preference) {
    /* La entrada NUNCA oculta la tabla: la opacidad se queda en 1 y solo se
       desplaza. Si la tabla se volviera invisible, el fondo del contenedor
       aparecería como un bloque negro al cambiar de pestaña. */
    .dt tbody {
      animation: rank-in 240ms var(--ease-out) both;
    }

    @keyframes rank-in {
      from {
        transform: translateY(0.4rem);
        filter: blur(0.2rem);
      }
      to {
        transform: none;
        filter: blur(0);
      }
    }
  }

  /* Sin `overflow` en escritorio: el contenedor se convertiría en scrollport y el
     `thead` sticky taparía la primera fila (el líder). */
  .table-scroll {
    overflow-x: visible;
  }

  .dt {
    width: 100%;
    border-collapse: collapse;
    text-align: left;
    font-size: 0.8125rem;
    /* Cifras tabulares en todas las columnas numéricas. */
    font-variant-numeric: tabular-nums;
  }

  .dt thead th {
    position: sticky;
    /* Bajo la cabecera COMPLETA (barra + hairline), no sólo la barra. */
    top: var(--header-offset, 3.0625rem);
    z-index: 10;
    padding: 0.7rem 0.9rem;
    font-size: 0.625rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: var(--muted);
    background: var(--bg);
    border-bottom: var(--hairline) solid var(--line-strong);
    white-space: nowrap;
  }

  .dt tbody td {
    padding: 0.55rem 0.9rem;
    border-bottom: var(--hairline) solid var(--line);
    vertical-align: middle;
  }

  .dt tbody tr {
    transition: background var(--default-transition-duration) var(--default-transition-timing-function);
  }

  /* Podio: borde izquierdo de 3px en 1°/2°/3°, velo de fila completa solo en 1°. */
  .dt tbody tr.row-p1 > td:first-child {
    box-shadow: inset 3px 0 0 0 var(--podium-1);
  }

  .dt tbody tr.row-p2 > td:first-child {
    box-shadow: inset 3px 0 0 0 var(--podium-2);
  }

  .dt tbody tr.row-p3 > td:first-child {
    box-shadow: inset 3px 0 0 0 var(--podium-3);
  }

  /* El ÚNICO realce de fila es el paso del ratón. Ninguna fila tiene estado
     persistente: el 1º no está "seleccionado", solo encabeza la tabla. */
  .dt tbody tr:hover {
    background: color-mix(in srgb, var(--edge) 5%, transparent);
  }

  .rankbox {
    display: inline-block;
    min-width: 2.1rem;
    padding: 0.1rem 0.3rem;
    font-weight: 700;
    font-size: 0.75rem;
    text-align: center;
    color: var(--muted);
    border: var(--hairline) solid var(--line-strong);
  }

  /* Podio: 1 oro, 2 plata, 3 bronce. Insignia SOLIDA: los tres primeros tienen
     que verse de un vistazo, también en móvil y con los colores apagados de
     una tabla con mucha información. */
  .rankbox--p1 {
    color: var(--podium-fg);
    background: var(--podium-1);
    border-color: var(--podium-1);
  }

  .rankbox--p2 {
    color: var(--podium-fg);
    background: var(--podium-2);
    border-color: var(--podium-2);
  }

  .rankbox--p3 {
    color: var(--podium-fg);
    background: var(--podium-3);
    border-color: var(--podium-3);
  }

  .col-rank {
    width: 4rem;
  }

  .col-delta {
    width: 3.75rem;
    text-align: center;
  }

  .col-name {
    width: 24%;
    min-width: 11rem;
  }

  .name-wrap {
    display: inline-block;
    vertical-align: middle;
  }

  .col-cat {
    width: 9.5rem;
  }

  .col-catrank {
    width: 4.5rem;
    color: var(--muted);
    font-size: 0.75rem;
  }

  /* El club es la columna que respira: ancho mínimo wide y sin recorte. */
  .col-team {
    width: 30%;
    min-width: 180px;
  }

  .col-time {
    width: 6.75rem;
    text-align: right;
    white-space: nowrap;
  }

  .col-gap {
    width: 6.75rem;
    text-align: right;
    color: var(--muted);
    white-space: nowrap;
  }

  .gap.is-negative {
    color: var(--faint);
  }

  .col-pts {
    width: 4.75rem;
    text-align: right;
    white-space: nowrap;
  }

  .pts-num {
    font-weight: 800;
  }

  .pts-unit {
    margin-left: 0.25rem;
    font-size: 0.6875rem;
    font-weight: 400;
    color: var(--muted);
  }

  .col-num {
    width: 4.5rem;
    text-align: right;
    color: var(--muted);
  }

  .rider-link,
  .team-link {
    color: var(--ink);
    text-decoration: none;
    font-weight: 600;
  }

  .rider-link:hover,
  .team-link:hover {
    color: var(--scope-ink);
    text-decoration: underline;
    text-underline-offset: 0.2rem;
  }

  .team-free {
    color: var(--muted);
  }

  .badge-cat {
    display: inline-block;
    padding: 0.1rem 0.35rem;
    font-size: 0.625rem;
    letter-spacing: 0.08em;
    color: var(--muted);
    border: var(--hairline) solid var(--line);
    white-space: nowrap;
  }

  /* Δ: colores SEMÁNTICOS (subir verde, bajar rojo) en cualquier tema. */
  .delta-up {
    color: var(--status-up);
    font-weight: 700;
  }

  .delta-down {
    color: var(--status-down);
    font-weight: 700;
  }

  .delta-eq {
    color: var(--status-flat);
  }

  .delta-new {
    color: var(--status-flat);
    font-size: 0.625rem;
    letter-spacing: 0.08em;
  }

  .empty {
    text-align: center;
    padding: 3rem 1rem;
    color: var(--muted);
    font-size: 0.75rem;
  }

  /* Subtítulo compacto: solo en la vista de tarjeta (móvil). */
  .cell-sub {
    display: none;
  }

  /* --- Móvil: celda apilada de 3 columnas --- */
  @media (max-width: 47.99em) {
    /* En móvil la descripcion de la carrera ocupa varias lineas (con los
       enlaces): las flechas se alinean con la primera. */
    .stagehead {
      align-items: flex-start;
    }

    .stagehead__nav {
      margin-top: -0.45rem;
    }

    .ribbon {
      padding: 0.6rem 0.9rem;
      gap: 0.35rem;
    }

    .ribbon__meta {
      font-size: 0.625rem;
    }

    .rank__controls {
      gap: 0;
    }

    .tabs {
      width: 100%;
      overflow-x: auto;
      scrollbar-width: none;
    }

    .tabs::-webkit-scrollbar {
      display: none;
    }

    /* En móvil las CUATRO pestañas tienen que caber (EQUIPO se salía de la
       pantalla): se estrechan los anchos y el interletraje del rótulo. */
    .tabs__group {
      --w-pro: 3.5rem;
      --w-normal: 5rem;
      --w-ebike: 4.75rem;
      --w-teams: 4.75rem;
    }

    .tab {
      padding: 0.7rem 0.4rem;
      font-size: 0.6875rem;
      letter-spacing: 0.08em;
      white-space: nowrap;
    }

    /* Selectores en dos columnas y el buscador debajo: menos alto, más filas. */
    .rank__filters {
      display: grid;
      grid-template-columns: 1fr 1fr;
      grid-template-areas:
        'stage stage'
        'search search';
      gap: 0.75rem;
      width: 100%;
      padding: 0.75rem 0.9rem;
      border-top: var(--hairline) solid var(--line);
    }

    .rank__filters:has(.ctl--cat) {
      grid-template-areas:
        'cat stage'
        'search search';
    }

    .ctl--cat {
      grid-area: cat;
    }

    .ctl--stage {
      grid-area: stage;
    }

    .search {
      grid-area: search;
      max-width: none;
    }

    .dt {
      font-size: 0.8125rem;
    }

    .dt thead {
      display: none;
    }

    .dt tbody tr {
      display: grid;
      grid-template-columns: 44px minmax(0, 1fr) auto;
      grid-template-areas:
        'rank name pts'
        'delta name time';
      align-items: center;
      gap: 10px;
      padding: 10px 12px;
      border-bottom: var(--hairline) solid var(--line);
    }

    .dt tbody td {
      display: block;
      padding: 0;
      border: none;
    }

    .col-rank {
      grid-area: rank;
      width: auto;
      text-align: left;
    }

    .col-delta {
      grid-area: delta;
      width: auto;
      text-align: left;
      font-size: 0.6875rem;
    }

    .col-name {
      grid-area: name;
      width: auto;
      min-width: 0;
    }

    .col-pts {
      grid-area: pts;
      width: auto;
      min-width: 76px;
      text-align: right;
    }

    .col-time {
      grid-area: time;
      width: auto;
      text-align: right;
      font-size: 0.6875rem;
      color: var(--muted);
    }

    /* Sus datos pasan al subtítulo: no se pierde información. */
    .dt tbody td.col-cat,
    .dt tbody td.col-team,
    .dt tbody td.col-catrank,
    .dt tbody td.col-gap {
      display: none;
    }

    .name-wrap {
      display: block;
      margin-left: 0;
      min-width: 0;
      max-width: 100%;
    }

    .name-wrap .rider-link {
      display: block;
      font-weight: 700;
      font-size: 0.8125rem;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .cell-sub {
      display: flex;
      align-items: baseline;
      gap: 0.4rem;
      margin-top: 0.15rem;
      font-size: 0.6875rem;
      color: var(--muted);
      min-width: 0;
      max-width: 100%;
      overflow: hidden;
    }

    .cell-cat {
      flex: 0 0 auto;
      padding: 0 0.3rem;
      font-size: 0.5625rem;
      letter-spacing: 0.06em;
      color: var(--muted);
      border: var(--hairline) solid var(--line);
      white-space: nowrap;
    }

    .cell-team {
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .cell-team a {
      color: inherit;
      text-decoration: none;
    }

    /* Fila de equipo: los conteos van con etiqueta en el sub-título; las
       columnas sueltas (OROS/PLATAS/BRONCES/CORREDORES) se ocultan. */
    .dt tbody td.col-num {
      display: none;
    }

    .cell-stat {
      white-space: nowrap;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    /* En móvil el conteo de corredores no cabe junto a las medallas: la tabla
       de escritorio lo muestra; aquí se omite para no truncar el subtítulo. */
    .cell-stat--riders {
      display: none;
    }

    .rankbox {
      min-width: 1.9rem;
      font-size: 0.6875rem;
    }

    .pts-num {
      font-size: 0.875rem;
    }

    .pts-unit {
      font-size: 0.6875rem;
    }
  }
</style>
