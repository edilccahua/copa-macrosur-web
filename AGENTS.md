# AGENTS.md — Constitución del Proyecto (Plataforma de competicion de ciclismo mtb)

## 1. Visión y Contexto
Plataforma web Mobile-First para la gestión, cronometraje en vivo (con soporte offline para jueces) y ranking acumulado de un campeonato de ciclismo MTB de 4 fechas.

## 2. Stack Tecnológico Innegociable
- **Frontend Core:** Astro 5 (SSG para contenido informativo, SSR selectivo).
- **Islas Interactivas:** Svelte 5 usando ESTRICTAMENTE **Runes** (`$state`, `$derived`, `$effect`, `$props`). PROHIBIDO usar sintaxis legacy de Svelte 4 (`export let`, `$:`, stores clásicos).
- **Lenguaje Frontend:** TypeScript estricto (`strict: true`).
- **Estilos y Diseño:** CSS Moderno Nativo (`<style>` scoped en componentes Astro/Svelte) consumiendo variables globales desde `src/styles/tokens.css` (basado en extracción `open-design` de getartcraft.com). **PROHIBIDO instalar o usar Tailwind CSS o Bootstrap.**
- **Animaciones:** GSAP permitido ÚNICAMENTE en páginas de escaparate (Home, Presentación de Fechas). **PROHIBIDO cargar librerías de animación en `/en-vivo` y `/admin/juez`.**
- **Tiempo Real:** Server-Sent Events (SSE) vía `StreamingResponse` en FastAPI y `EventSource` nativo en el cliente. **PROHIBIDO usar WebSockets.**
- **Backend:** Python 3.12+ con FastAPI, SQLModel (SQLAlchemy 2.0 + Pydantic v2) y Alembic para migraciones.
- **Procesamiento de Archivos:** `openpyxl` para ingesta/exportación de Excels; `gpxpy` para parseo de rutas `.gpx`.
- **Base de Datos y Storage:** PostgreSQL (alojado en Neon.tech en producción, Docker local en desarrollo) + Cloudflare R2 (vía `boto3` S3-compatible) para imágenes y archivos GPX.

## 3. Protocolo de Trabajo Agéntico (Lean SDD)
Tienes PROHIBIDO generar o modificar código de aplicación sin seguir esta secuencia:
1. **Lectura de Contrato:** Antes de tocar código, lee el archivo correspondiente dentro de `specs/`.
2. **Carga de Skill:** Si existe una skill relevante en `.agents/skills/`, léela antes de proponer soluciones.
3. **Gate de Planificación:** Presenta primero la lista exacta de archivos a crear/modificar y un resumen de 5 líneas de la lógica. Espera confirmación humana.
4. **Verificación (Test Gate):** Todo cálculo de tiempos, puntos acumulados, deltas de posición o parseo de Excel debe incluir su test unitario en `pytest` y pasar en verde antes de dar la tarea por terminada.
5. **Sincronización:** Si durante la implementación se acuerda un cambio de estructura, actualiza el archivo `specs/XX-*.md` afectado antes de cerrar la tarea.
