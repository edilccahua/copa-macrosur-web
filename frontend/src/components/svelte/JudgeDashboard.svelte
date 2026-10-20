<script lang="ts">
  import { onMount } from 'svelte';
  import { API_V1, BASE_URL } from '../../lib/api';
  import {
    savePendingEvent,
    getUnsyncedEvents,
    markEventSynced,
    getAllEvents,
    type PendingTimingEvent
  } from '../../lib/judge-db';

  /**
   * El PIN NUNCA viene en el código de la página: se pide en la puerta y se
   * guarda en el dispositivo. Antes venía hardcodeado en `initialJudgePin`
   * y cualquiera podía leerlo en el código fuente y mandar marcaciones.
   */
  const PIN_STORAGE_KEY = 'kuspide_judge_pin';

  type GateState = 'loading' | 'locked' | 'ready' | 'error';

  interface JudgeStage {
    id: number;
    stage_number: number;
    name: string;
    slug: string;
  }

  // Estados reactivos ($state)
  let gateState = $state<GateState>('loading');
  let pinInput = $state<string>('');
  let pinError = $state<string>('');
  let stage = $state<JudgeStage | null>(null);
  let stageError = $state<string>('');
  /** El PIN en memoria: se usa como cabecera `X-Judge-Pin` en cada llamada. */
  let judgePin = $state<string>('');
  let isAuthorized = $state(true);
  let bibInput = $state<string>('');
  let clockOffsetMs = $state<number>(0);
  let isOnline = $state<boolean>(true);
  let wakeLockActive = $state<boolean>(false);
  let unsyncedCount = $state<number>(0);
  let recentEvents = $state<PendingTimingEvent[]>([]);

  // ── Puerta de acceso ──────────────────────────────────────────────────────

  /**
   * La fecha se resuelve sola: la que está EN VIVO, si no la siguiente con
   * inscripciones abiertas, si no la última disputada. El juez no elige:
   * elige el PIN.
   */
  function resolveStage(stages: any[]): JudgeStage | null {
    if (!Array.isArray(stages) || stages.length === 0) return null;
    const live = stages.find((s: any) => s.status === 'LIVE');
    if (live) return live;
    const open = stages.find((s: any) => s.status === 'REGISTRATION_OPEN');
    if (open) return open;
    const finished = stages.filter((s: any) => s.status === 'FINISHED');
    return finished[finished.length - 1] ?? stages[stages.length - 1];
  }

  async function loadStage(): Promise<JudgeStage | null> {
    try {
      const res = await fetch(`${API_V1}/stages`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const resolved = resolveStage(await res.json());
      stage = resolved;
      return resolved;
    } catch (e) {
      stageError = 'No se pudo contactar al servidor de cronometraje.';
      return null;
    }
  }

  /** Comprueba el PIN contra el backend (sin registrar ninguna marcación). */
  async function validatePin(pin: string, target: JudgeStage): Promise<boolean> {
    try {
      const res = await fetch(`${API_V1}/stages/${target.id}/judge-auth`, {
        headers: { 'X-Judge-Pin': pin }
      });
      return res.ok;
    } catch (e) {
      return false;
    }
  }

  function storePin(pin: string): void {
    try {
      localStorage.setItem(PIN_STORAGE_KEY, pin);
    } catch (e) {
      /* sin almacenamiento: el PIN vive sólo en memoria */
    }
  }

  function readStoredPin(): string {
    try {
      return localStorage.getItem(PIN_STORAGE_KEY) ?? '';
    } catch (e) {
      return '';
    }
  }

  function forgetPin(): void {
    try {
      localStorage.removeItem(PIN_STORAGE_KEY);
    } catch (e) {
      /* nada que limpiar */
    }
    judgePin = '';
    pinInput = '';
    gateState = 'locked';
  }

  async function unlock(): Promise<void> {
    const pin = pinInput.trim();
    if (!pin) {
      pinError = 'Escribe el PIN de la fecha.';
      return;
    }
    if (!stage) {
      pinError = stageError || 'La fecha no está disponible.';
      return;
    }
    const ok = await validatePin(pin, stage);
    if (!ok) {
      pinError = 'PIN inválido para esta fecha.';
      return;
    }
    pinError = '';
    judgePin = pin;
    storePin(pin);
    gateState = 'ready';
    startSession();
  }

  // Cola de timestamps para Modo Ráfaga
  interface BurstStamp {
    id: string;
    timestampMs: number;
    formattedTime: string;
    bibNumber?: number;
  }
  let burstQueue = $state<BurstStamp[]>([]);

  // Modal 409 Conflicto
  let conflictModal = $state<{
    visible: boolean;
    pendingEvent?: PendingTimingEvent;
    message: string;
    existingTime: string;
  }>({
    visible: false,
    message: '',
    existingTime: ''
  });

  function getCalibratedTimeMs(): number {
    return Date.now() + clockOffsetMs;
  }

  function formatTime(ms: number): string {
    const d = new Date(ms);
    const h = String(d.getHours()).padStart(2, '0');
    const m = String(d.getMinutes()).padStart(2, '0');
    const s = String(d.getSeconds()).padStart(2, '0');
    const millis = String(d.getMilliseconds()).padStart(3, '0');
    return `${h}:${m}:${s}.${millis}`;
  }

  // Teclado numérico
  function pressKey(k: string) {
    if (k === 'C') {
      bibInput = '';
    } else if (k === 'DEL') {
      bibInput = bibInput.slice(0, -1);
    } else {
      if (bibInput.length < 4) bibInput += k;
    }
  }

  // Marcación individual
  async function submitSingleTap() {
    if (!bibInput || !Number(bibInput)) return;
    const bib = Number(bibInput);
    const recordedAt = getCalibratedTimeMs();
    bibInput = '';

    const newEvent: PendingTimingEvent = {
      id: crypto.randomUUID(),
      stage_entry_id: bib, // el backend resuelve dorsal si se pasa stage_id
      checkpoint_id: 3, // Meta final por defecto
      recorded_at_ms: recordedAt,
      recorded_by_admin: 'juez_pwa',
      force_update: false,
      synced: false,
      created_at: Date.now(),
      bib_number: bib
    };

    await savePendingEvent(newEvent);
    await refreshCounts();
    await trySync();
  }

  // Modo ráfaga: congela timestamp
  function triggerBurstTap() {
    const ts = getCalibratedTimeMs();
    const item: BurstStamp = {
      id: crypto.randomUUID(),
      timestampMs: ts,
      formattedTime: formatTime(ts)
    };
    burstQueue.unshift(item);
  }

  // Asignar dorsal a timestamp de ráfaga
  async function assignBibToBurst(item: BurstStamp, bibVal: number) {
    const newEvent: PendingTimingEvent = {
      id: item.id,
      stage_entry_id: bibVal,
      checkpoint_id: 3,
      recorded_at_ms: item.timestampMs,
      recorded_by_admin: 'juez_pwa_burst',
      force_update: false,
      synced: false,
      created_at: Date.now(),
      bib_number: bibVal
    };

    burstQueue = burstQueue.filter((b) => b.id !== item.id);
    await savePendingEvent(newEvent);
    await refreshCounts();
    await trySync();
  }

  // Sincronización hacia backend
  async function trySync() {
    if (!navigator.onLine) {
      isOnline = false;
      return;
    }
    isOnline = true;

    const unsynced = await getUnsyncedEvents();
    if (unsynced.length === 0) return;

    try {
      const payload = {
        events: unsynced.map((e) => ({
          id: e.id,
          stage_entry_id: e.stage_entry_id,
          checkpoint_id: e.checkpoint_id,
          recorded_at_ms: e.recorded_at_ms,
          recorded_by_admin: e.recorded_by_admin,
          force_update: e.force_update
        }))
      };

      const res = await fetch(`${BASE_URL}/api/v1/timing/batch-sync`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Judge-Pin': judgePin
        },
        body: JSON.stringify(payload)
      });

      if (res.ok) {
        const data = await res.json();
        // Marcar sincronizados
        for (const ev of unsynced) {
          const isConflict = (data.conflicts || []).find((c: any) => c.id === ev.id);
          if (!isConflict) {
            await markEventSynced(ev.id);
          } else {
            // Mostrar modal de conflicto 409
            conflictModal = {
              visible: true,
              pendingEvent: ev,
              message: isConflict.detail?.message || 'Conflicto de tiempo en meta',
              existingTime: isConflict.detail?.existing_time_str || ''
            };
          }
        }
      }
    } catch (err) {
      console.warn('Error en sincronización batch', err);
    }

    await refreshCounts();
  }

  async function resolveConflict(replace: boolean) {
    if (!conflictModal.pendingEvent) return;
    const ev = conflictModal.pendingEvent;
    conflictModal.visible = false;

    if (replace) {
      ev.force_update = true;
      await savePendingEvent(ev);
      await trySync();
    } else {
      await markEventSynced(ev.id);
      await refreshCounts();
    }
  }

  async function refreshCounts() {
    const unsynced = await getUnsyncedEvents();
    unsyncedCount = unsynced.length;
    const all = await getAllEvents();
    all.sort((a, b) => b.created_at - a.created_at);
    recentEvents = all.slice(0, 10);
  }

  /**
   * Lo que sólo tiene sentido con la sesión abierta: calibrar el reloj,
   * mantener la pantalla encendida, pedir almacenamiento persistente y
   * escuchar la red.
   */
  let sessionStarted = false;
  function startSession(): void {
    if (sessionStarted) return;
    sessionStarted = true;

    // 1. Calibrar reloj con el servidor
    fetch(`${API_V1}/timing/time-sync`)
      .then((r) => r.json())
      .then((d) => {
        if (d.server_time_ms) {
          clockOffsetMs = d.server_time_ms - Date.now();
        }
      })
      .catch(() => {});

    // 2. Wake Lock
    if ('wakeLock' in navigator) {
      (navigator as any).wakeLock
        .request('screen')
        .then(() => (wakeLockActive = true))
        .catch(() => {});
    }

    // 3. Storage persist
    if (navigator.storage && navigator.storage.persist) {
      navigator.storage.persist();
    }

    // 4. Listeners online/offline
    window.addEventListener('online', trySync);
    window.addEventListener('offline', () => (isOnline = false));

    refreshCounts();
  }

  onMount(() => {
    // La puerta: se resuelve la fecha y se prueba el PIN que ya guarda el
    // dispositivo. Si el PIN guardado ya no vale, se borra y se pide otro.
    (async () => {
      const target = await loadStage();
      if (!target) {
        gateState = 'error';
        return;
      }
      const stored = readStoredPin();
      if (stored) {
        if (await validatePin(stored, target)) {
          judgePin = stored;
          gateState = 'ready';
          startSession();
          return;
        }
        forgetPin();
      }
      gateState = 'locked';
    })();

    return () => {
      window.removeEventListener('online', trySync);
    };
  });
</script>

<!-- ── Puerta de acceso ──────────────────────────────────────────────────────
     El PIN se pide aquí, se valida contra el servidor y se guarda en el
     dispositivo. El sitio público no enlaza a esta página: la URL la
     comparte el organizador con el juez. -->
{#if gateState === 'loading'}
  <div class="judge-gate">
    <div class="judge-gate-card">
      <div class="judge-gate-title font-mono">ABRIENDO EL PANEL DE CRONOMETRAJE</div>
      <div class="judge-gate-text">Resolviendo la fecha en curso…</div>
    </div>
  </div>
{:else if gateState === 'error'}
  <div class="judge-gate">
    <div class="judge-gate-card">
      <div class="judge-gate-title font-mono">SIN CONEXIÓN CON EL SERVIDOR</div>
      <div class="judge-gate-text">
        {stageError || 'No se pudo contactar al servidor de cronometraje.'}
      </div>
      <button class="judge-gate-submit font-mono" onclick={() => location.reload()}>
        REINTENTAR
      </button>
    </div>
  </div>
{:else if gateState === 'locked'}
  <div class="judge-gate">
    <div class="judge-gate-card">
      <div class="judge-gate-title font-mono">PANEL OFICIAL DEL JUEZ</div>
      <div class="judge-gate-stage font-mono">
        FECHA {stage?.stage_number ?? '—'} · {stage?.name ?? ''}
      </div>
      <div class="judge-gate-text">
        Introduce el PIN de esta fecha. El dispositivo lo recuerda para el resto
        del campeonato; puedes borrarlo cuando quieras.
      </div>
      <form
        class="judge-gate-form"
        onsubmit={(e) => {
          e.preventDefault();
          void unlock();
        }}
      >
        <input
          class="judge-gate-input font-mono"
          type="password"
          inputmode="text"
          autocomplete="off"
          autocapitalize="characters"
          spellcheck="false"
          placeholder="PIN"
          bind:value={pinInput}
        />
        <button class="judge-gate-submit font-mono" type="submit" disabled={!pinInput.trim()}>
          ENTRAR
        </button>
      </form>
      {#if pinError}
        <div class="judge-gate-error font-mono">{pinError}</div>
      {/if}
    </div>
  </div>
{:else}
<div class="judge-container">
  <!-- Cabecera de Estado del Juez -->
  <div class="judge-header">
    <div class="badge-status">
      <span class="status-indicator" class:online={isOnline}></span>
      <span>{isOnline ? 'ENLACE ONLINE ACTIVO' : 'MODO OFFLINE'}</span>
    </div>
    {#if wakeLockActive}
      <span class="wake-tag font-mono">[WAKE-LOCK ACTIVO]</span>
    {/if}
    <div class="queue-status font-mono">
      Pendientes: <strong>{unsyncedCount}</strong>
    </div>
    <button class="judge-lock font-mono" onclick={forgetPin} title="Borrar el PIN de este dispositivo">
      [ SALIR ]
    </button>
  </div>

  <!-- Teclado Numérico Directo -->
  <div class="pos-screen">
    <div class="screen-label font-mono">[ DORSAL A REGISTRAR EN META ]</div>
    <div class="screen-input font-mono">{bibInput || '---'}</div>
  </div>

  <div class="keypad-grid">
    {#each ['1', '2', '3', '4', '5', '6', '7', '8', '9', 'C', '0', 'DEL'] as key}
      <button class="key-btn font-mono" onclick={() => pressKey(key)}>
        {key}
      </button>
    {/each}
  </div>

  <button class="btn-register-primary font-mono" onclick={submitSingleTap} disabled={!bibInput}>
    REGISTRAR CRUCE DE META #{bibInput || '?'}
  </button>

  <!-- Modo Ráfaga para Sprint Masivo -->
  <div class="burst-section">
    <div class="burst-title font-mono">[ LLEGADA MASIVA // MODO SPRINT ]</div>
    <button class="btn-burst font-mono" onclick={triggerBurstTap}>
      [ CAPTURAR SPLIT // CONGELAR TIEMPO ]
    </button>

    {#if burstQueue.length > 0}
      <div class="burst-list">
        <div class="burst-list-label font-mono">Tiempos congelados por asignar dorsal:</div>
        {#each burstQueue as item (item.id)}
          <div class="burst-card">
            <span class="burst-time font-mono">{item.formattedTime}</span>
            <div class="burst-action">
              <input
                type="number"
                placeholder="Dorsal"
                class="burst-input font-mono"
                onkeydown={(e) => {
                  if (e.key === 'Enter') {
                    const target = e.target as HTMLInputElement;
                    if (target.value) assignBibToBurst(item, Number(target.value));
                  }
                }}
              />
            </div>
          </div>
        {/each}
      </div>
    {/if}
  </div>

  <!-- Historial de Últimas Marcaciones -->
  <div class="recent-events-box">
    <div class="recent-title font-mono">Últimas 10 marcaciones en este dispositivo</div>
    {#each recentEvents as ev (ev.id)}
      <div class="recent-row">
        <span class="font-mono bib">#{ev.bib_number}</span>
        <span class="font-mono time">{formatTime(ev.recorded_at_ms)}</span>
        <span class="tag-synced font-mono" class:synced={ev.synced}>
          {ev.synced ? '[Sincronizado]' : '[Pendiente]'}
        </span>
      </div>
    {/each}
  </div>
</div>

<!-- Modal Conflicto 409 -->
{#if conflictModal.visible}
  <div class="modal-backdrop">
    <div class="modal-card">
      <div class="modal-title font-mono">[ALERTA 409 // REGISTRO DUPLICADO EN META]</div>
      <p class="modal-text">
        El dorsal #{conflictModal.pendingEvent?.bib_number} ya tenía registrado un tiempo en meta:
        <strong>{conflictModal.existingTime}</strong>.
      </p>
      <p class="modal-text">¿Deseas reemplazar el tiempo oficial con esta nueva marcación?</p>
      <div class="modal-actions">
        <button class="btn-modal-cancel font-mono" onclick={() => resolveConflict(false)}>
          Conservar tiempo anterior
        </button>
        <button class="btn-modal-replace font-mono" onclick={() => resolveConflict(true)}>
          Reemplazar tiempo
        </button>
      </div>
    </div>
  </div>
{/if}
{/if}

<style>
  .judge-container {
    max-width: 30rem;
    margin: 0 auto;
    padding: 1rem;
    background: var(--bg, #fbfbfd);
    min-height: 100vh;
  }

  .judge-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.75rem 1rem;
    background: var(--bg-raised, #ffffff);
    border: var(--hairline, 1px) solid var(--line, rgba(16, 16, 20, 0.16));
    margin-bottom: 1rem;
  }

  .badge-status {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.6875rem;
    font-weight: 800;
  }

  .status-indicator {
    width: 0.5rem;
    height: 0.5rem;
    background: #ef4444;
  }

  .status-indicator.online {
    background: #10b981;
  }

  .wake-tag {
    font-size: 0.625rem;
    font-weight: 700;
    color: var(--accent, #ff5500);
  }

  .pos-screen {
    background: var(--invert-bg, #101014);
    color: var(--invert-fg, #ffffff);
    padding: 1.25rem;
    text-align: center;
    border: var(--hairline, 1px) solid var(--line, rgba(16, 16, 20, 0.16));
    margin-bottom: 1rem;
  }

  .screen-label {
    font-size: 0.625rem;
    letter-spacing: 0.14em;
    color: #a0a0b0;
    margin-bottom: 0.25rem;
  }

  .screen-input {
    font-size: 2.5rem;
    font-weight: 800;
    letter-spacing: 0.05em;
  }

  .keypad-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0.5rem;
    margin-bottom: 1rem;
  }

  .key-btn {
    height: 4rem;
    background: var(--bg-raised, #ffffff);
    border: var(--hairline, 1px) solid var(--line, rgba(16, 16, 20, 0.16));
    font-size: 1.5rem;
    font-weight: 700;
    color: var(--ink, #101014);
    cursor: pointer;
    border-radius: 0;
  }

  .key-btn:active {
    background: var(--line, rgba(16, 16, 20, 0.16));
  }

  .btn-register-primary {
    width: 100%;
    padding: 1.25rem;
    background: #10b981;
    color: #ffffff;
    border: none;
    font-family: inherit;
    font-size: 0.875rem;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    cursor: pointer;
    margin-bottom: 1.5rem;
  }

  .btn-register-primary:disabled {
    background: var(--muted);
    opacity: 0.35;
    cursor: not-allowed;
  }

  .burst-section {
    background: var(--bg-raised, #ffffff);
    border: var(--hairline, 1px) solid var(--line, rgba(16, 16, 20, 0.16));
    padding: 1rem;
    margin-bottom: 1.5rem;
  }

  .burst-title {
    font-size: 0.6875rem;
    font-weight: 800;
    letter-spacing: 0.12em;
    color: var(--muted, #70707c);
    margin-bottom: 0.75rem;
  }

  .btn-burst {
    width: 100%;
    padding: 1rem;
    background: var(--invert-bg, #101014);
    color: var(--invert-fg, #ffffff);
    border: none;
    font-size: 0.8125rem;
    font-weight: 800;
    letter-spacing: 0.1em;
    cursor: pointer;
  }

  .burst-list {
    margin-top: 1rem;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .burst-card {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.625rem;
    border: var(--hairline, 1px) solid var(--line, rgba(16, 16, 20, 0.16));
    background: var(--bg, #fbfbfd);
  }

  .burst-input {
    width: 5rem;
    padding: 0.35rem 0.5rem;
    border: var(--hairline, 1px) solid var(--line, rgba(16, 16, 20, 0.16));
    font-size: 0.875rem;
  }

  .recent-events-box {
    background: var(--bg-raised, #ffffff);
    border: var(--hairline, 1px) solid var(--line, rgba(16, 16, 20, 0.16));
    padding: 1rem;
  }

  .recent-title {
    font-size: 0.6875rem;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--muted, #70707c);
    margin-bottom: 0.75rem;
  }

  .recent-row {
    display: flex;
    justify-content: space-between;
    padding-block: 0.35rem;
    border-bottom: var(--hairline, 1px) solid var(--line, rgba(16, 16, 20, 0.16));
    font-size: 0.75rem;
  }

  .tag-synced {
    color: #f59e0b;
  }

  .tag-synced.synced {
    color: #10b981;
  }

  .modal-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.7);
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 1.5rem;
    z-index: 50;
  }

  .modal-card {
    background: var(--bg-raised, #ffffff);
    padding: 1.5rem;
    max-width: 25rem;
    width: 100%;
    border: 2px solid #ef4444;
  }

  .modal-title {
    font-size: 1rem;
    font-weight: 800;
    margin-bottom: 0.75rem;
    color: #ef4444;
  }

  .modal-text {
    font-size: 0.8125rem;
    color: var(--ink, #101014);
    line-height: 1.5;
    margin-bottom: 0.75rem;
  }

  .modal-actions {
    display: flex;
    gap: 0.75rem;
    margin-top: 1.25rem;
  }

  .btn-modal-cancel {
    flex: 1;
    padding: 0.75rem;
    background: var(--bg, #fbfbfd);
    border: var(--hairline, 1px) solid var(--line, rgba(16, 16, 20, 0.16));
    font-weight: 600;
    cursor: pointer;
  }

  .btn-modal-replace {
    flex: 1;
    padding: 0.75rem;
    background: #ef4444;
    color: #ffffff;
    border: none;
    font-weight: 700;
    cursor: pointer;
  }

  /* ── Puerta de acceso ─────────────────────────────────────────────────── */

  .judge-gate {
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 1.5rem;
    background: var(--bg, #fbfbfd);
  }

  .judge-gate-card {
    width: 100%;
    max-width: 24rem;
    padding: 1.5rem;
    background: var(--bg-raised, #fff);
    border: var(--hairline, 1px) solid var(--line, rgba(16, 16, 20, 0.16));
  }

  .judge-gate-title {
    font-size: 0.75rem;
    font-weight: 800;
    letter-spacing: 0.14em;
    color: var(--ink, #101014);
  }

  .judge-gate-stage {
    margin-top: 0.5rem;
    font-size: 0.6875rem;
    letter-spacing: 0.08em;
    color: #ff5500;
  }

  .judge-gate-text {
    margin-top: 0.875rem;
    font-size: 0.8125rem;
    line-height: 1.5;
    color: var(--muted, rgba(16, 16, 20, 0.62));
  }

  .judge-gate-form {
    display: flex;
    gap: 0.5rem;
    margin-top: 1.25rem;
  }

  .judge-gate-input {
    flex: 1 1 auto;
    min-width: 0;
    padding: 0.75rem;
    font-size: 1rem;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    color: var(--ink, #101014);
    background: var(--bg, #fbfbfd);
    border: var(--hairline, 1px) solid var(--line, rgba(16, 16, 20, 0.16));
  }

  .judge-gate-submit {
    flex: 0 0 auto;
    padding: 0.75rem 1rem;
    font-size: 0.6875rem;
    font-weight: 800;
    letter-spacing: 0.12em;
    color: #ffffff;
    background: #101014;
    border: none;
    cursor: pointer;
  }

  .judge-gate-submit:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  .judge-gate-error {
    margin-top: 0.75rem;
    font-size: 0.6875rem;
    letter-spacing: 0.08em;
    color: #ef4444;
  }

  .judge-lock {
    font-size: 0.625rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    color: var(--muted, rgba(16, 16, 20, 0.62));
    background: none;
    border: none;
    cursor: pointer;
  }

  .judge-lock:hover {
    color: #ef4444;
  }
</style>
