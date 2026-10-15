---
name: svelte5-runes
description: Reglas obligatorias para programar componentes en Svelte 5 (Runes) e integrarlos como Islas óptimas dentro de Astro 5.
---

# Skill: Svelte 5 (Runes Mode) + Astro Islands

## 1. Sintaxis Prohibida vs. Sintaxis Obligatoria (Svelte 5)
Tienes ESTRICTAMENTE PROHIBIDO usar sintaxis de Svelte 3/4. Aplica siempre esta tabla de traducción:

- **Props de entrada:**
  - ❌ Prohibido: `export let initialData;`
  - ✅ Obligatorio: `let { initialData, stageId }: Props = $props();`
- **Estado Reactivo:**
  - ❌ Prohibido: `let count = 0;` (asumiendo reactividad implícita) o `writable(0)` de `svelte/store`.
  - ✅ Obligatorio: `let count = $state(0);`
- **Valores Calculados / Filtros:**
  - ❌ Prohibido: `$: filtered = items.filter(...)`
  - ✅ Obligatorio: `let filtered = $derived(items.filter(...));` (o `$derived.by(() => { ... })` para bloques complejos).
- **Efectos Secundarios y Ciclo de Vida:**
  - ❌ Prohibido: `$: { console.log(count); }` para efectos.
  - ✅ Obligatorio: `$effect(() => { ... return () => cleanup(); });`
- **Eventos en el DOM:**
  - ❌ Prohibido: `on:click={handler}`
  - ✅ Obligatorio: `onclick={handler}` (atributos estándar de HTML5).
- **Slots / Contenido Hijo:**
  - ❌ Prohibido: `<slot />`
  - ✅ Obligatorio: `{#snippet ...}` y `{@render children?.()}`.

## 2. Reglas de Hidratación en Astro (`client:*`)
En páginas `.astro`, nunca pongas directivas `client:*` a componentes que solo pintan HTML estático (Carteles, Tarjetas de Premios, Podios fijos). Usa componentes `.astro` para todo lo estático y reserva `.svelte` únicamente para:
1. `client:load` -> Cronómetro activo y Tabla de Ranking en `/en-vivo`.
2. `client:visible` -> Mapa interactivo GPX (`MapLibre` / `Leaflet`), perfil de altimetría interactivo y tablas históricas con buscador/filtros en páginas de fechas.
3. `client:only="svelte"` -> Panel de control del Juez (`/admin/juez`) que depende de `IndexedDB` del navegador.

