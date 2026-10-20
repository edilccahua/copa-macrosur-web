# Spec 02: Cronometraje en Vivo, Endpoints de Sincronización Offline y SSE Streaming

> **Estado:** COMPLETADO ✅  
> **Fecha de Verificación:** 19 de Octubre de 2026  
> **Evidencia:** `test_timing_sse.py` pasando con 0 sesiones DB retenidas en streaming, 409 Conflict en re-tap de meta, UUID idempotente para marcaciones offline-first, PWA Juez (`JudgeDashboard.svelte` con `idb`, WakeLock, Modo Ráfaga) y LiveLeaderboard SSE en Svelte 5 Runes puro.

## 1. Gestión de Largadas y Mangas (Start Waves)

### 1.1 Largada por Manga de Categorías: `POST /api/v1/stages/{stage_id}/waves/{wave_id}/start`
Permite dar la partida a un grupo de categorías simultáneamente (ej. Manga 1: *Élite + Master A*; Manga 2: *Turismo + Damas*).
- **Acción del Backend:**
  1. Registra `StartWave.started_at_ms = current_epoch_ms` (o timestamp enviado por el juez principal).
  2. Actualiza masivamente todos los `StageEntry` pertenecientes a las categorías de esa manga:
     - `start_time_ms = StartWave.started_at_ms`
     - `race_status = STARTED`
  3. Emite un evento SSE `wave-started` con el listado de categorías largadas y la hora oficial.

### 1.2 Largada Individual (Contrarreloj / Excepciones): `POST /api/v1/stages/{stage_id}/entries/{stage_entry_id}/start`
- Asigna `start_time_ms` y `race_status = STARTED` a un corredor individual en la hora exacta de su salida.

---

## 2. Endpoints de FastAPI para Cronometraje y Sincronización

### 2.1 Calibración de Reloj: `GET /api/v1/timing/time-sync`
- Devuelve `{ "server_time_ms": 1776510845120 }`.
- Al abrir el panel o reconectar red, el cliente móvil calcula el offset:
  `clock_offset = server_time_ms - Date.now()`.
- Cualquier marcación registrada en el móvil se guarda con:
  `recorded_at_ms = Date.now() + clock_offset`.

### 2.2 Snapshot Inicial de Carrera: `GET /api/v1/stages/{stage_id}/live-summary`
- Devuelve el estado actual completo de la carrera: lista de mangas largadas, últimos corredores en cruzar meta, tabla provisional de puestos por categoría y podio provisional de equipos.
- Consumido obligatoriamente por clientes web al cargar la pantalla `/en-vivo` o tras recuperar la conexión SSE tras una desconexión.

### 2.3 Recepción Individual o en Lote: `POST /api/v1/timing/events` y `/batch-sync`
- **Payload de entrada:**
```json
{
  "id": "c0733564-9721-4889-8d1b-05b19d458632",
  "stage_entry_id": 142,
  "checkpoint_id": 3,
  "recorded_at_ms": 1776510845000,
  "recorded_by_admin": "juez_01",
  "force_update": false
}
```

- **Validaciones y Lógica del Backend:**
  1. **Validación Cruzada de Fecha:** Verifica que `Checkpoint.stage_id == StageEntry.stage_id`. Si no coinciden, rechaza con HTTP `400 Bad Request`.
  2. **Validación de Largada (Sanity Check):** Verifica que `recorded_at_ms >= StageEntry.start_time_ms`. Si el tiempo es menor que la largada, rechaza con HTTP `422 Unprocessable Entity` ("Marcación anterior a la hora de partida").
  3. **Idempotencia Offline-First:** Realiza `UPSERT` sobre `TimingEvent` con clave `id` (UUID). Si el mismo UUID llega repetido por reintentos de red, se ignora silenciosamente.
  4. **Protección de Meta y Carrera de Re-tap (`is_finish_line == true`):**
     - Si el corredor ya tiene registrado un `finish_elapsed_ms` y `force_update == false`: Devuelve HTTP `409 Conflict` con los datos del tiempo anterior para disparar en el celular del juez la alerta interactiva:
       `"El dorsal #45 ya cruzó meta a las 09:32:15. ¿Deseas reemplazar el tiempo o cancelar?"`.
     - Si `force_update == true`: Actualiza `finish_elapsed_ms` con el nuevo tiempo y registra el evento en auditoría.
  5. **Cálculo de Tiempo Neto y Rankings:**
     - `finish_elapsed_ms = recorded_at_ms - StageEntry.start_time_ms`.
     - Actualiza `race_status = FINISHED`.
     - Dispara el recálculo asíncrono de puestos de categoría y de la clasificación por equipos de la fecha.
  6. **Disparo Inmediato de SSE:** Emite el evento `timing-update` hacia la cola en memoria del canal de streaming.

---

## 3. Canal de Streaming en Tiempo Real: `GET /api/v1/stages/{stage_id}/stream`

- **Arquitectura de Desacoplamiento Estricto:**
  - El generador SSE `async def event_generator()` **NO interactúa con la base de datos PostgreSQL** ni retiene sesiones de conexión (`AsyncSession`). Escucha únicamente un canal `asyncio.Queue` en memoria por cada `stage_id`.
  - Soporta 2,000+ conexiones concurrentes en un único proceso FastAPI sin saturar el pool de base de datos de Neon.
- **Mantenimiento de Conexión (Keep-Alive Heartbeat):**
  - Cada 20 segundos de inactividad de eventos, el generador emite:
    ```text
    : ping\n\n
    ```
    Esto previene que proxies intermedios (Cloudflare, Nginx, operadores móviles) corten la conexión HTTP por inactividad.
- **Estructura del Mensaje SSE (`timing-update`):**
```json
{
  "event_type": "finish",
  "stage_id": 1,
  "bib_number": 15,
  "rider_name": "ALEXIS ARNOLD QUISPE TANTANI",
  "team_name": "TEAM ALPHA",
  "category_name": "ELITE",
  "elapsed_ms": 4116000,
  "formatted_time": "01:08:36.000",
  "provisional_category_rank": 1,
  "checkpoint_name": "Meta"
}
```

---

## 4. Panel del Juez (PWA Mobile en `/admin/juez`)

### 4.1 Experiencia de Usuario (Marcación Rápida sin Grilla Masiva de Botones)
Dada la cantidad de participantes (cientos de ciclistas), la interfaz móvil ofrece dos modos de captura:

1. **Modo Individual (Teclado Numérico Directo):**
   - Teclado numérico táctil grande en pantalla (tipo calculadora/POS).
   - En cuanto el juez escribe el número de dorsal o pulsa `[ REGISTRAR ]`, el tiempo se congela al primer toque. Muestra la tarjeta del ciclista para confirmación instantánea.
2. **Modo Ráfaga / Llegada Grupal (`[ MARCAR PASO ]`):**
   - Para llegadas masivas de sprint con múltiples ciclistas cruzando en segundos:
   - Botón de ancho completo `[ MARCAR PASO ]`. Cada pulsación congela y apila un timestamp ($T_1, T_2, T_3...$) en una cola visual en pantalla.
   - En los segundos siguientes, el juez selecciona cada tarjeta de tiempo y le digita el dorsal correspondiente.

### 4.2 Resiliencia de Hardware y Almacenamiento
1. **Pantalla Siempre Activa (Screen Wake Lock):**
   - Al cargar el panel, solicita `navigator.wakeLock.request('screen')` para evitar que el teléfono se bloquee bajo el sol mientras el juez espera corredores.
2. **Protección contra Purgas del SO Móvil:**
   - Solicita almacenamiento persistente explícito: `await navigator.storage.persist()`.
   - Store `pending_events` en IndexedDB (vía `idb`).
   - Backup redundante en `localStorage` con las últimas 100 marcaciones como salvaguarda ante cualquier corrupción accidental.
3. **Sincronización Automática:**
   - Listener `window.addEventListener('online', syncBatch)`. Al recuperar señal 4G, envía el lote a `POST /api/v1/timing/batch-sync` y marca `synced: true` únicamente tras confirmación HTTP 200.
4. **Alerta Interactiva de Doble Toque:**
   - Si el backend responde HTTP 409, muestra modal de advertencia para confirmar si se desea reemplazar el tiempo anterior o descartar el segundo toque.
5. **Rendimiento:**
   - **PROHIBIDO** cargar GSAP u otras librerías de animación en `/admin/juez` ni en `/en-vivo` (conforme a `AGENTS.md`).

---

## 5. Portal de Espectadores en Vivo (`/en-vivo`)
- Página Astro ultra-ligera con Isla Svelte 5 (`<LiveLeaderboard stageId={currentStageId} />`).
- Al montar, solicita primero el snapshot `/api/v1/stages/{stage_id}/live-summary` para pintar la tabla al instante.
- Abre la conexión con `EventSource` nativo consumiendo `/api/v1/stages/{stage_id}/stream` para aplicar deltas en vivo.
- Si la conexión se pierde y se restablece, vuelve a solicitar `/live-summary` para subsanar cualquier evento no recibido.
