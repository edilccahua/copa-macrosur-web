---
name: offline-timing-sync
description: Reglas de arquitectura para construir el panel del Juez Offline-First usando IndexedDB (via idb) y la recepción de datos en tiempo real con Server-Sent Events (SSE).
---

# Skill: Panel Offline-First y Tiempo Real SSE

## 1. El Almacenamiento Local del Juez (IndexedDB)

- Para evitar la complejidad de APIs crudas de IndexedDB, utiliza la librería ligera `idb` (de Jake Archibald) que devuelve Promesas nativas (`async/await`).
- **Esquema de la Base de Datos Local (`mtb_judge_db`):**
  - Store `pending_events`: Guarda los eventos de marcación offline. Estructura: `{ id: UUID, stage_entry_id: int, checkpoint_id: int, recorded_at_ms: int, synced: boolean }`.
- **Lógica de Conectividad:**
  - Implementa un `window.addEventListener('online', syncQueueWithBackend)`.
  - Cada vez que el navegador detecta red, recorre los registros con `synced: false` en `pending_events`, los empuja en un bloque `POST /api/v1/timing/batch-sync` a FastAPI, y actualiza su estado local a `synced: true` solo al recibir HTTP 200.

## 2. Consumo de SSE en Svelte 5 (EventSource)

- En el componente Svelte 5 que pinta el ranking en vivo (`/en-vivo`), inicializa el `EventSource` dentro de un `$effect` para asegurar limpieza al desmontar:

```ts
$effect(() => {
  const eventSource = new EventSource(`/api/v1/stages/${stageId}/stream`);

  eventSource.addEventListener('timing-update', (e) => {
    const payload = JSON.parse(e.data);
    updateLocalLeaderboard(payload);
  });

  eventSource.onerror = () => {
    // El navegador se encarga de la reconexión automática nativa
  };

  return () => {
    eventSource.close();
  };
});
```
