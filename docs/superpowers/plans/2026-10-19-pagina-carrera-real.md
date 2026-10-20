# Plan General — Rediseño Real de la Página de Carrera (`/fechas/[slug]`)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convertir `/fechas/[slug]` de una maqueta editorial con datos falsos en una ficha de carrera real: todo dato de la BD (podio por categoría, estadísticas de jornada, podio de equipos, top-10 Strava, checkpoints, ruta real, premios con ganador) servido por un endpoint único de presentación y renderizado con un mapa de verdad.

**Architecture:** Un endpoint SSR nuevo `GET /api/v1/stages/{slug}/summary` devuelve el agregado de presentación de una fecha (stage + stats + podios + strava + checkpoints + awards). La página Astro consume ese endpoint y renderiza la ficha. El mock `stagesDb` desaparece: la BD es la única fuente de verdad. `RouteMapGpx.svelte` pasa de polígono SVG inventado a mapa vectorial proyectado desde `route_geojson` real con markers de checkpoint.

**Tech Stack:** FastAPI + SQLModel (async) + Pydantic v2 · Astro 5 SSR (`@astrojs/node` standalone) · Svelte 5 Runes estricto · CSS nativo scoped con tokens de `copiaartcraft` · pytest + httpx AsyncClient.

**Spec:** `specs/03-public-portal-and-gpx.md` §1.2 (página de fecha), §0 (reglas SSR). `specs/00-domain-schema.md` (entidades). `specs/01-excel-and-scoring.md` §3.1 (escala de puntos). `INTEGRIDAD-DATOS.md` (cifras oficiales).

---

## Global Constraints

- **Cero mocks.** La página de fecha no puede contener objetos de datos literales. Si la API no responde, la página devuelve **503** (`specs/03` §0.2). Prohibido reintroducir `stagesDb`.
- **Cero Tailwind/Bootstrap** (`AGENTS.md` §2). CSS nativo scoped en `<style>` de cada `.astro`/`.svelte`.
- **Fuente de diseño:** estilos, tokens y ritmo de animación tomados de `/home/edilsonc/Documents/copiaartcraft/src/styles/` y `src/components/` (`AGENTS.md` §2, skill `artcraft-scoped-css`).
- **Svelte 5 Runes estrictos:** prohibido `export let`, `$:`, `on:click`, `svelte/store`. Props con `$props()`, estado con `$state()`, derivados con `$derived()`, eventos con `onclick=` (`skill svelte5-runes`).
- **Animación pesada solo en escaparate:** GSAP/Lenis únicamente en `Showcase.astro`. La ficha de fecha **sí** usa `Showcase` (es página de presentación de fecha, autorizada por `AGENTS.md` §2), pero `RouteMapGpx` no carga ninguna librería de animación.
- **Sin MapLibre.** No se instala `maplibre-gl` (no está en `package.json` y `specs/03` §1.2 lo menciona por error). El mapa es SVG vectorial nativo, proyectado desde `route_geojson`.
- **Cero disco local en runtime:** el GPX se sirve desde `frontend/public/gpx/` (ya versionado) o R2; nunca se escribe en disco.
- **Test Gate (`AGENTS.md` §3.5):** todo cálculo de estadísticas de jornada, podio y agregados debe tener test unitario en `pytest` y estar en verde antes de cerrar la tarea.
- **Sync (`AGENTS.md` §3.6):** si cambia el contrato de la API o la estructura de la página, actualizar `specs/03-public-portal-and-gpx.md` en la misma tarea.
- **SQLModel/Pydantic v2:** `.model_dump()`, `.model_validate()`, `ConfigDict(from_attributes=True)`. Prohibido `.dict()` / `.parse_obj()`.
- **Errores de negocio:** `422` con `{"detail": ..., "errors": [{"row","field","message"}]}`.

---

## Review Focus

Cinco modos de fallo que la spec implica pero que ningún test del repo cubre hoy. Cada línea tiene su test en la tarea dueña.

1. **Fecha sin resultados** (F3/F4: 0 inscripciones). La ficha debe renderizar como "próxima", no romperse ni mostrar métricas en cero como si fueran reales. → Task 1.1, `test_stage_summary.py::test_summary_undisputed_stage_has_null_stats`.
2. **Ciclo por vueltas** (F2: 11.83 km × 3 vueltas, +280 m por vuelta). `elevation_gain_m` y `distance_km` en BD son **por vuelta**; el total de carrera es `× laps`. La página y la API deben exponer ambos sin mezclarlos (el bug actual muestra +840 m en el hero y +280 m en el bloque GPX). → Task 1.1, `test_stage_summary.py::test_summary_lap_circuit_exposes_per_lap_and_total`.
3. **`farolito` sin `scratch`** (o al revés). La BD puede tener un extremo y no el otro. El render actual accede a `stage.farolito.name` sin guardia → TypeError → 500. → Tarea 1.5 (`test_summary_endpoint_extremes_may_be_independent`) + Tarea 2.2 Step 6 (guardia en el render) + Tarea 3.2 Step 7 (comprobación en navegador).
4. **Nombre del categoría con acento y club partido por salto de línea** (`CLUB ORIGINAL BIKES AREQUIPA-PERÚ`). La normalización de club partido ya existe en `excel_service.resolve_or_create_team`; el resumen debe devolverla sin duplicar equipos. → Task 1.3, `test_stage_summary.py::test_summary_team_podium_has_no_duplicated_clubs`.
5. **Cero segmentos Strava o cero premios** (F3/F4 no tienen). Los bloques deben omitirse enteros, no renderizar tarjetas vacías ni "Sin registros aún" duplicado. → Task 1.4, `test_stage_summary.py::test_summary_upcoming_stage_has_empty_collections`.

---

## Mapa de archivos

### Backend — crear
| Archivo | Responsabilidad |
| :--- | :--- |
| `backend/app/services/stage_summary_service.py` | Agrega los datos de presentación de una fecha: stats de jornada, podio por categoría, podio de equipos, segmentos Strava con top-10, checkpoints, awards con ganador. Sin acceso a red ni a disco. |
| `backend/app/models/schemas.py` (modificar) | Esquemas Pydantic v2 de la respuesta: `StageSummaryRead`, `StageStatsRead`, `CategoryPodiumRead`, `PodiumEntryRead`, `TeamPodiumRead`, `StravaSegmentSummaryRead`, `CheckpointRead`, `AwardSummaryRead`. |
| `backend/app/routers/stages.py` (modificar) | Añade `GET /api/v1/stages/{slug}/summary`. Mantiene los endpoints existentes sin cambios. |
| `backend/tests/test_stage_summary.py` | Tests del servicio y del endpoint contra cifras oficiales reales. |

### Frontend — crear
| Archivo | Responsabilidad |
| :--- | :--- |
| `frontend/src/components/svelte/RouteMapGpx.svelte` (reescribir) | Mapa vectorial de la ruta real desde `route_geojson` + markers de checkpoint + altimetría sincronizada. Sin geometría inventada. |
| `frontend/src/components/StagePodiumGrid.astro` | Podio por categoría: 11 bloques, top-3 con dorsal, tiempo, puntos, club. |
| `frontend/src/components/StageStatsRow.astro` | Fila de estadísticas de jornada: inscritos, finalizaron, no_SUBMIT, puntos, velocidad ganadora, desnivel total. |
| `frontend/src/components/StageTeamPodium.astro` | Podio de equipos de la jornada con puntos sumados y corredores. |

### Frontend — modificar
| Archivo | Cambio |
| :--- | :--- |
| `frontend/src/pages/fechas/[slug].astro` | Borrar `stagesDb`; consumir `/summary`; nuevos bloques; prev/next; countdown; guardia de `farolito`; desnivel por vuelta vs total. |
| `frontend/src/lib/api.ts` | Tipos `StageSummary` y su cliente `getStageSummary(slug)`. |
| `frontend/src/pages/fechas/[slug]/resultados.astro` | Añadir enlace de retorno a los podios de la ficha y a la exportación; no recalcular podios aquí. |
| `specs/03-public-portal-and-gpx.md` | §1.2 reescrito con lo que realmente existe; eliminar la mención a MapLibre y a la galería si no se implementa. |

---

## Fase 0 — Truth Ground (desbloquea todo)

Sin esto, todo lo demás se construye sobre una BD con la API sirviendo código viejo. El `uvicorn` llevaba 2 h sin recargar y no exponía `title`, `short_name`, `start_location`, `start_time`: la página leía `undefined` y caía al mock.

### Task 0.1: Congelar el estado real del API y la BD

**Files:**
- Create: `backend/tests/test_stage_summary.py` (solo el andamiaje y el test de verdad de la API)
- Test: `backend/tests/test_stage_summary.py`

**Interfaces:**
- Consumes: `backend/app.main.app`, fixture `client` de `backend/tests/conftest.py`.
- Produces: nothing (es la línea base que todos los tests siguientesassume).

- [ ] **Step 1: Escribir el test que falla**

```python
def test_stage_api_exposes_persisted_fields(client):
    """El summary de una fecha devuelve los campos que la BD persiste.

    Antes, el API servía una versión vieja del modelo (sin title/short_name/
    start_location/start_time) y la página caía al mock local.
    """
    # seed mínimo: una etapa con title, short_name, start_location, start_time
    ...
    res = await client.get("/api/v1/stages/la-joya-extreme/summary")
    assert res.status_code == 200
    body = res.json()
    assert body["stage"]["title"] == "La Joya Extreme"
    assert body["stage"]["short_name"] == "La Joya"
    assert body["stage"]["start_location"] == "Vía de Evitamiento, La Joya"
    assert body["stage"]["start_time"] == "08:00 AM"
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `PYTHONPATH=. python3 -m pytest backend/tests/test_stage_summary.py::test_stage_api_exposes_persisted_fields -v`
Expected: FAIL — `404` (el endpoint `/summary` todavía no existe).

- [ ] **Step 3: Fijar el procedimiento de arranque (documentación, no código)**

Añadir a `start.sh` un `curl` de salud al backend antes de levantar el frontend, y anotar en `specs/03` §0.2 que **el API debe reiniciarse tras cambiar modelos** (`uvicorn --reload` en dev). Verificar que `start.sh` levanta el backend con `--reload` cuando `MODE=dev`.

```bash
# en start.sh, modo dev:
PYTHONPATH=. python3 -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload &
# y antes de "Levantando frontend":
for i in $(seq 1 30); do
  curl -sf http://localhost:8000/api/v1/stages > /dev/null && break
  sleep 1
done
```

- [ ] **Step 4: Verificar el arranque**

Run: `PYTHONPATH=. python3 -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload &` y luego `curl -s http://localhost:8000/api/v1/stages/la-joya-extreme | python3 -c "import sys,json; print(sorted(json.load(sys.stdin)['stage'].keys()))"`
Expected: la lista incluye `title`, `short_name`, `start_location`, `start_time`, `laps`, `strava_route_url`.

- [ ] **Step 5: Commit**

```bash
git add start.sh backend/tests/test_stage_summary.py
git commit -m "test: fijar contrato del API de etapa y arranque con reload"
```

### Task 0.2: Helper de siembra para los tests del resumen

**Files:**
- Create: `backend/tests/test_stage_summary.py` (sección de helpers, arriba de los tests)
- Test: `backend/tests/test_stage_summary.py`

**Interfaces:**
- Produces: los helpers que usan las Tasks 1.1–1.5.
  ```python
  async def _seed_stage_with_results(
      session: AsyncSession,
      *,
      slug: str = "la-joya-extreme",
      stage_number: int = 1,
      name: str = "Fecha 1: La Joya Extreme",
      title: str = "La Joya Extreme",
      short_name: str = "La Joya",
      start_location: str = "Vía de Evitamiento, La Joya",
      start_time: str = "08:00 AM",
      date: str = "2026-05-17",
      distance_km: float = 40.85,
      elevation_gain_m: int = 384,
      laps: int = 1,
      entries: int = 0,
      finishers: int = 0,
      points: int = 0,
      categories: int = 0,
  ) -> Stage
  ```
  Crea la `Stage` y sus `StageEntry` (con `category_rank`, `finish_elapsed_ms`, `points_earned`), las `Category` necesarias y `commit`. Devuelve la `Stage` creada.

  ```python
  async def _seed_categories(session: AsyncSession, codes: list[str]) -> list[Category]
  ```
  Crea (o reutiliza) las categorías por `short_code` y devuelve la lista en orden.

- [ ] **Step 1: Escribir el helper y su test de humo**

```python
async def test_seed_helper_creates_entries(async_session):
    """El helper deja la BD en el estado que el resto de tests asume."""
    stage = await _seed_stage_with_results(async_session, entries=225, finishers=198, points=667, categories=11)
    assert stage.id is not None
    total = await async_session.exec(
        select(func.count()).select_from(StageEntry).where(StageEntry.stage_id == stage.id)
    )
    assert total.one() == 225
```

- [ ] **Step 2: Ejecutar y ver que pasa**

Run: `PYTHONPATH=. python3 -m pytest backend/tests/test_stage_summary.py::test_seed_helper_creates_entries -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_stage_summary.py
git commit -m "test: helper de siembra para el resumen de fecha"
```

---

## Fase 1 — El endpoint de presentación (backend)

### Task 1.1: Estadísticas de jornada

**Files:**
- Create: `backend/app/services/stage_summary_service.py`
- Modify: `backend/app/models/schemas.py`
- Test: `backend/tests/test_stage_summary.py`

**Interfaces:**
- Consumes: `AsyncSession`, `Stage`, `StageEntry`, `Category`, `Rider`, `Team`.
- Produces:
  ```python
  # backend/app/services/stage_summary_service.py
  async def compute_stage_stats(session: AsyncSession, stage_id: int) -> StageStatsRead
  ```
  con `StageStatsRead`:
  ```python
  class StageStatsRead(BaseModel):
      entries_total: int          # inscripciones (StageEntry de la fecha)
      finishers: int             # finish_elapsed_ms IS NOT NULL
      non_finishers: int         # inscritos sin tiempo
      points_total: int          # SUM(points_earned)
      distance_km_per_lap: float # Stage.distance_km
      distance_km_total: float   # Stage.distance_km * Stage.laps
      elevation_m_per_lap: int   # Stage.elevation_gain_m
      elevation_m_total: int     # Stage.elevation_gain_m * Stage.laps
      laps: int
      winner_time_ms: Optional[int]      # MIN(finish_elapsed_ms)
      winner_avg_speed_kmh: Optional[float]  # distance_km_total / winner_time_ms
      categories_count: int
  ```

- [ ] **Step 1: Escribir el test que falla**

```python
async def test_stage_stats_match_official_numbers(async_session):
    """Las estadísticas de la Fecha 1 coinciden con el PDF oficial.

    INTEGRIDAD-DATOS.md §4: 225 inscripciones, 198 con tiempo, 667 puntos.
    """
    stage = await _seed_stage_with_results(async_session, slug="la-joya-extreme",
                                           entries=225, finishers=198, points=667)
    stats = await compute_stage_stats(async_session, stage.id)
    assert stats.entries_total == 225
    assert stats.finishers == 198
    assert stats.non_finishers == 27
    assert stats.points_total == 667
    assert stats.categories_count == 11
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `PYTHONPATH=. python3 -m pytest backend/tests/test_stage_summary.py::test_stage_stats_match_official_numbers -v`
Expected: FAIL — `ImportError: cannot import name 'compute_stage_stats'`.

- [ ] **Step 3: Implementar `compute_stage_stats`**

En `backend/app/services/stage_summary_service.py`:

```python
async def compute_stage_stats(session: AsyncSession, stage_id: int) -> StageStatsRead:
    """Agrega las cifras de una jornada a partir de StageEntry.

    `distance_km` y `elevation_gain_m` de Stage son POR VUELTA (ver
    entities.Stage). Los totales de carrera se derivan multiplicando por `laps`.
    """
```
Consultas: `select(func.count(), func.sum(...))` sobre `StageEntry` filtrado por `stage_id`; `select(Stage).where(Stage.id == stage_id)` para distancia/elevación/laps; `MIN(finish_elapsed_ms)` para el ganador. La velocidad ganadora es `distance_km_total / (winner_time_ms / 3_600_000)`, redondeada a 2 decimales.

- [ ] **Step 4: Ejecutar y ver que pasa**

Run: `PYTHONPATH=. python3 -m pytest backend/tests/test_stage_summary.py::test_stage_stats_match_official_numbers -v`
Expected: PASS.

- [ ] **Step 5: Añadir los casos límite del Review Focus**

```python
async def test_summary_undisputed_stage_has_null_stats(async_session):
    """F3 no tiene inscripciones: las estadísticas son null, no ceros falsos."""
    # ...
    assert stats.entries_total == 0
    assert stats.winner_time_ms is None
    assert stats.winner_avg_speed_kmh is None

async def test_summary_lap_circuit_exposes_per_lap_and_total(async_session):
    """F2 es un circuito por vueltas: se exponen ambos, sin mezclarlos."""
    # laps=3, distance_km=11.83, elevation_gain_m=280
    assert stats.distance_km_per_lap == 11.83
    assert stats.distance_km_total == pytest.approx(35.49)
    assert stats.elevation_m_per_lap == 280
    assert stats.elevation_m_total == 840
```

- [ ] **Step 6: Ejecutar todos los tests de stats**

Run: `PYTHONPATH=. python3 -m pytest backend/tests/test_stage_summary.py -v`
Expected: PASS (3 tests).

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/stage_summary_service.py backend/app/models/schemas.py backend/tests/test_stage_summary.py
git commit -m "feat: estadísticas de jornada por fecha"
```

### Task 1.2: Podio por categoría

**Files:**
- Modify: `backend/app/services/stage_summary_service.py`
- Modify: `backend/app/models/schemas.py`
- Test: `backend/tests/test_stage_summary.py`

**Interfaces:**
- Consumes: `compute_stage_stats` (no requerido), `StageEntry`, `Category`, `Rider`, `Team`.
- Produces:
  ```python
  async def compute_category_podium(session: AsyncSession, stage_id: int) -> List[CategoryPodiumRead]

  class CategoryPodiumRead(BaseModel):
      category_id: int
      category_name: str
      short_code: str
      entries: List[PodiumEntryRead]   # top 3, ordenados por category_rank

  class PodiumEntryRead(BaseModel):
      rank: int
      bib_number: int
      rider_name: str
      rider_slug: str
      team_name: str
      team_slug: Optional[str]
      formatted_time: str
      points_earned: int
  ```

- [ ] **Step 1: Escribir el test que falla**

```python
async def test_category_podium_returns_top3_per_category(async_session):
    """Cada categoría devuelve su top-3 con tiempo, puntos y club."""
    # 11 categorías sembradas
    podium = await compute_category_podium(async_session, stage.id)
    assert len(podium) == 11
    for cat in podium:
        assert len(cat.entries) == 3
        assert [e.rank for e in cat.entries] == [1, 2, 3]
        assert all(e.formatted_time for e in cat.entries)
        assert all(e.points_earned > 0 for e in cat.entries)
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `PYTHONPATH=. python3 -m pytest backend/tests/test_stage_summary.py::test_category_podium_returns_top3_per_category -v`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Implementar `compute_category_podium`**

```python
async def compute_category_podium(session: AsyncSession, stage_id: int) -> List[CategoryPodiumRead]:
    """Top-3 por categoría de una fecha, ordenado por category_rank.

    Usa `StageEntry.category_rank` (ya calculado por el motor de scoring)
    y no recalcula puestos: el PDF oficial manda (specs/01 §1.5.2).
    """
```
`select(StageEntry, Category, Rider, Team).join(...)` filtrado por `stage_id` y `category_rank <= 3`, ordenado por `Category.id` y `StageEntry.category_rank`. El tiempo se formatea con `format_ms_to_time` de `backend/app/services/pdf_service.py`. Si `finish_elapsed_ms` es `None`, `formatted_time` es `"-"` y el puesto se omite (no entra al top-3).

- [ ] **Step 4: Ejecutar y ver que pasa**

Run: `PYTHONPATH=. python3 -m pytest backend/tests/test_stage_summary.py::test_category_podium_returns_top3_per_category -v`
Expected: PASS.

- [ ] **Step 5: Verificar contra la BD real**

```bash
curl -s http://localhost:8000/api/v1/stages/la-joya-extreme/summary | python3 -c "
import sys,json
d=json.load(sys.stdin)
p=d['podium']
print('categorías:', len(p))
print('total entradas:', sum(len(c['entries']) for c in p))
print('ejemplo:', p[0])
"
```
Expected: 11 categorías, 33 entradas, primera = ELITE con `ALEXIS  ARNOLD QUISPE TANTANI` (dorsal del PDF oficial, 10 pts).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/stage_summary_service.py backend/app/models/schemas.py backend/tests/test_stage_summary.py
git commit -m "feat: podio por categoria en el resumen de fecha"
```

### Task 1.3: Podio de equipos de la jornada

**Files:**
- Modify: `backend/app/services/stage_summary_service.py`
- Modify: `backend/app/models/schemas.py`
- Test: `backend/tests/test_stage_summary.py`

**Interfaces:**
- Produces:
  ```python
  async def compute_stage_team_podium(session: AsyncSession, stage_id: int) -> List[TeamPodiumRead]

  class TeamPodiumRead(BaseModel):
      team_id: int
      team_name: str
      team_slug: str
      points: int              # SUM(points_earned) en la fecha
      riders_counted: int      # corredores con puntos en la fecha
      best_rank: int           # mejor category_rank alcanzado
  ```

- [ ] **Step 1: Escribir el test que falla**

```python
async def test_team_podium_ranks_by_points_of_that_stage(async_session):
    """El podio de equipos suma solo los puntos de ESA fecha, no el acumulado."""
    # ...
    podium = await compute_stage_team_podium(async_session, stage.id)
    assert podium[0].team_name == "TEAM COLCA BIKE"
    assert podium[0].points == 107
    assert podium[0].riders_counted == 25
    assert [p.points for p in podium] == sorted([p.points for p in podium], reverse=True)
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `PYTHONPATH=. python3 -m pytest backend/tests/test_stage_summary.py::test_team_podium_ranks_by_points_of_that_stage -v`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Implementar `compute_stage_team_podium`**

```python
async def compute_stage_team_podium(session: AsyncSession, stage_id: int) -> List[TeamPodiumRead]:
    """Top-3 equipos por puntos sumados en ESTA fecha.

    Normaliza el nombre del club con la misma regla que `excel_service`
    (`collapse_team_hyphen`) para no partir 'AREQUIPA-' / 'PERÚ' en dos
    equipos (INTEGRIDAD-DATOS.md §2.2 caso 3).
    """
```
`select(Team, func.sum(StageEntry.points_earned), func.count()).join(StageEntry).where(StageEntry.stage_id == stage_id).group_by(Team.id).order_by(desc(sum), Team.name)`. Solo equipos con `points > 0`. Limitar a los 3 primeros.

- [ ] **Step 4: Ejecutar y ver que pasa**

Run: `PYTHONPATH=. python3 -m pytest backend/tests/test_stage_summary.py::test_team_podium_ranks_by_points_of_that_stage -v`
Expected: PASS.

- [ ] **Step 5: Añadir el caso de club partido del Review Focus**

```python
async def test_summary_team_podium_has_no_duplicated_clubs(async_session):
    """'CLUB ORIGINAL BIKES AREQUIPA-PERÚ' es UN equipo, no dos."""
    # ...
    names = [p.team_name for p in podium]
    assert len(names) == len(set(names))
    assert "CLUB ORIGINAL BIKES AREQUIPA-PERÚ" in names
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/stage_summary_service.py backend/app/models/schemas.py backend/tests/test_stage_summary.py
git commit -m "feat: podio de equipos por fecha"
```

### Task 1.4: Strava con top-10, checkpoints y premios

**Files:**
- Modify: `backend/app/services/stage_summary_service.py`
- Modify: `backend/app/models/schemas.py`
- Test: `backend/tests/test_stage_summary.py`

**Interfaces:**
- Produces:
  ```python
  async def compute_stage_strava(session: AsyncSession, stage_id: int) -> List[StravaSegmentSummaryRead]
  async def compute_stage_checkpoints(session: AsyncSession, stage_id: int) -> List[CheckpointRead]
  async def compute_stage_awards(session: AsyncSession, stage_id: int) -> List[AwardSummaryRead]

  class StravaSegmentSummaryRead(BaseModel):
      strava_segment_id: str
      name: str
      distance_m: float
      average_grade: float
      distance_km: float
      efforts: List[StravaEffortRead]   # top 10 por elapsed_time_sec
      kom: Optional[StravaEffortRead]  # el effort con is_kom_qom

  class StravaEffortRead(BaseModel):
      athlete_name: str
      elapsed_time_sec: int
      formatted_time: str
      is_kom_qom: bool

  class CheckpointRead(BaseModel):
      name: str
      order_index: int
      distance_from_start_km: float
      is_finish_line: bool

  class AwardSummaryRead(BaseModel):
      title: str
      sponsor_name: Optional[str]
      sponsor_logo_url: Optional[str]
      prize_description: Optional[str]
      metric_value: Optional[str]
      winner_name: Optional[str]
  ```

- [ ] **Step 1: Escribir el test que falla**

```python
async def test_strava_summary_exposes_top10_and_kom(async_session):
    """Cada segmento trae sus 10 mejores y el KOM marcado."""
    segs = await compute_stage_strava(async_session, stage.id)
    assert len(segs) == 2
    la_joya = next(s for s in segs if s.name == "La Joya Xtreme 26")
    assert len(la_joya.efforts) == 10
    assert la_joya.kom is not None
    assert la_joya.kom.is_kom_qom is True
    times = [e.elapsed_time_sec for e in la_joya.efforts]
    assert times == sorted(times)

async def test_checkpoints_are_ordered_with_finish_last(async_session):
    cps = await compute_stage_checkpoints(async_session, stage.id)
    assert [c.name for c in cps] == ["Partida", "Control Intermedio Cumbre", "Meta Final"]
    assert cps[-1].is_finish_line is True
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `PYTHONPATH=. python3 -m pytest backend/tests/test_stage_summary.py::test_strava_summary_exposes_top10_and_kom -v`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Implementar las tres funciones**

```python
async def compute_stage_strava(session: AsyncSession, stage_id: int) -> List[StravaSegmentSummaryRead]:
    """Segmentos Strava de la fecha con sus 10 mejores efforts y el KOM.

    El `is_kom_qom` de la BD es la autoridad del KOM (specs/02 §4).
    """

async def compute_stage_checkpoints(session: AsyncSession, stage_id: int) -> List[CheckpointRead]:
    """Checkpoints ordenados: Partida (order_index 0) ... Meta (is_finish_line)."""

async def compute_stage_awards(session: AsyncSession, stage_id: int) -> List[AwardSummaryRead]:
    """Premios de la fecha con su ganador resuelto desde `winner_rider_id`."""
```
`compute_stage_awards` resuelve `winner_rider_id` → `Rider.full_name` con un `select` de riders en lote. `metric_value` es texto libre ("Premio a la Resistencia y Espíritu Deportivo") y se muestra como descripción del premio.

- [ ] **Step 4: Ejecutar y ver que pasa**

Run: `PYTHONPATH=. python3 -m pytest backend/tests/test_stage_summary.py -v`
Expected: PASS (todos los del archivo).

- [ ] **Step 5: Añadir el caso de colecciones vacías del Review Focus**

```python
async def test_summary_upcoming_stage_has_empty_collections(async_session):
    """F3 no tiene segmentos Strava ni premios: las listas van vacías, no None."""
    # ...
    assert strava == []
    assert awards == []
    assert checkpoints != []   # F3 sí tiene checkpoints sembrados
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/stage_summary_service.py backend/app/models/schemas.py backend/tests/test_stage_summary.py
git commit -m "feat: strava top10, checkpoints y premios en el resumen de fecha"
```

### Task 1.5: El endpoint `/summary`

**Files:**
- Modify: `backend/app/routers/stages.py`
- Modify: `backend/app/models/schemas.py`
- Test: `backend/tests/test_stage_summary.py`

**Interfaces:**
- Consumes: las cinco funciones de `stage_summary_service.py`.
- Produces:
  ```
  GET /api/v1/stages/{slug}/summary
  200 -> {
    "stage": StageRead,
    "stats": StageStatsRead,
    "podium": [CategoryPodiumRead],
    "teams": [TeamPodiumRead],
    "strava": [StravaSegmentSummaryRead],
    "checkpoints": [CheckpointRead],
    "awards": [AwardSummaryRead],
    "extremes": {"scratch": PodiumEntryRead | null, "farolito": PodiumEntryRead | null},
    "navigation": {"prev_slug": str|null, "next_slug": str|null}
  }
  404 -> {"detail": "Etapa no encontrada."}
  ```
- `navigation` se calcula con los `stage_number` de la tabla `stages` (vecino anterior y siguiente, cualquiera que sea su `status`).

- [ ] **Step 1: Escribir el test que falla**

```python
async def test_summary_endpoint_shape_and_404(client):
    res = await client.get("/api/v1/stages/la-joya-extreme/summary")
    assert res.status_code == 200
    body = res.json()
    for key in ("stage","stats","podium","teams","strava","checkpoints","awards","extremes","navigation"):
        assert key in body
    missing = await client.get("/api/v1/stages/no-existe/summary")
    assert missing.status_code == 404
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `PYTHONPATH=. python3 -m pytest backend/tests/test_stage_summary.py::test_summary_endpoint_shape_and_404 -v`
Expected: FAIL — 404 en `/summary`.

- [ ] **Step 3: Implementar el endpoint**

En `backend/app/routers/stages.py`, después de `get_stage_by_slug`:

```python
@router.get("/{slug}/summary")
async def get_stage_summary(slug: str, session: AsyncSession = Depends(get_session)):
    """Aggregado de presentación de una fecha para la ficha `/fechas/[slug]`.

    Devuelve en UNA llamada todo lo que la página muestra: cifras de jornada,
    podio por categoría, podio de equipos, segmentos Strava, checkpoints,
    premios y los extremos de la jornada. La página no recalcula nada.
    """
```
Devolver `HTTPException(status_code=404, detail="Etapa no encontrada.")` si el slug no existe. Reutilizar `StageRead` como schema de `stage` (ya tiene `ConfigDict(from_attributes=True)`).

- [ ] **Step 4: Ejecutar y ver que pasa**

Run: `PYTHONPATH=. python3 -m pytest backend/tests/test_stage_summary.py -v`
Expected: PASS.

- [ ] **Step 5: Smoke test contra la BD real**

```bash
curl -s http://localhost:8000/api/v1/stages/la-joya-extreme/summary | python3 -c "
import sys,json
d=json.load(sys.stdin)
print('stats:', d['stats'])
print('podium cats:', len(d['podium']), 'entradas:', sum(len(c['entries']) for c in d['podium']))
print('teams:', [(t['team_name'], t['points']) for t in d['teams']])
print('strava:', [(s['name'], len(s['efforts'])) for s in d['strava']])
print('awards:', [(a['title'], a['sponsor_name']) for a in d['awards']])
print('navigation:', d['navigation'])
"
```
Expected: `entries_total=225, finishers=198, points_total=667`; 11 categorías / 33 entradas; `TEAM COLCA BIKE 107`; 2 segmentos; 2 premios; `navigation` con `next_slug='z-xtreme-2026'`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/stages.py backend/app/models/schemas.py backend/tests/test_stage_summary.py
git commit -m "feat: endpoint GET /stages/{slug}/summary"
```

---

## Fase 2 — La página: datos reales (frontend)

### Task 2.1: Cliente tipado del resumen

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Test: compilación (`npx astro check`)

**Interfaces:**
- Consumes: la forma JSON de `/api/v1/stages/{slug}/summary` de la Task 1.5.
- Produces:
  ```ts
  export interface StageStats {
    entries_total: number;
    finishers: number;
    non_finishers: number;
    points_total: number;
    distance_km_per_lap: number;
    distance_km_total: number;
    elevation_m_per_lap: number;
    elevation_m_total: number;
    laps: number;
    winner_time_ms: number | null;
    winner_avg_speed_kmh: number | null;
    categories_count: number;
  }

  export interface PodiumEntry {
    rank: number;
    bib_number: number;
    rider_name: string;
    rider_slug: string;
    team_name: string;
    team_slug: string | null;
    formatted_time: string;
    points_earned: number;
  }

  export interface CategoryPodium {
    category_id: number;
    category_name: string;
    short_code: string;
    entries: PodiumEntry[];
  }

  export interface TeamPodium {
    team_id: number;
    team_name: string;
    team_slug: string;
    points: number;
    riders_counted: number;
    best_rank: number;
  }

  export interface StravaEffort {
    athlete_name: string;
    elapsed_time_sec: number;
    formatted_time: string;
    is_kom_qom: boolean;
  }

  export interface StravaSegmentSummary {
    strava_segment_id: string;
    name: string;
    distance_m: number;
    average_grade: number;
    distance_km: number;
    efforts: StravaEffort[];
    kom: StravaEffort | null;
  }

  export interface Checkpoint {
    name: string;
    order_index: number;
    distance_from_start_km: number;
    is_finish_line: boolean;
  }

  export interface AwardSummary {
    title: string;
    sponsor_name: string | null;
    sponsor_logo_url: string | null;
    prize_description: string | null;
    metric_value: string | null;
    winner_name: string | null;
  }

  export interface StageSummary {
    stage: StageOption & {
      title: string | null;
      short_name: string | null;
      start_location: string | null;
      start_time: string | null;
      poster_url: string | null;
      gpx_file_url: string | null;
      route_geojson: RouteGeoJson | null;
      strava_route_url: string | null;
    };
    stats: StageStats;
    podium: CategoryPodium[];
    teams: TeamPodium[];
    strava: StravaSegmentSummary[];
    checkpoints: Checkpoint[];
    awards: AwardSummary[];
    extremes: { scratch: PodiumEntry | null; farolito: PodiumEntry | null };
    navigation: { prev_slug: string | null; next_slug: string | null };
  }
  export async function getStageSummary(slug: string): Promise<StageSummary>
  ```
  `RouteGeoJson`:
  ```ts
  export interface RouteGeoJson {
    type: 'FeatureCollection';
    features: { type: 'Feature'; geometry: { type: 'LineString'; coordinates: [number, number, number, number][] } }[];
  }
  ```

- [ ] **Step 1: Escribir los tipos y el cliente**

En `frontend/src/lib/api.ts`, añadir las interfaces de arriba y:

```ts
export async function getStageSummary(slug: string): Promise<StageSummary> {
  const res = await fetch(`${API_V1}/stages/${slug}/summary`);
  if (res.status === 404) throw new Error('stage-not-found');
  if (!res.ok) throw new Error(`summary HTTP ${res.status}`);
  return res.json();
}
```

- [ ] **Step 2: Verificar tipos**

Run: `cd frontend && npx astro check`
Expected: 0 errors, 0 warnings, 0 hints.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/api.ts
git commit -m "feat: cliente tipado del resumen de fecha"
```

### Task 2.2: Reescribir `[slug].astro` sin mocks

**Files:**
- Modify: `frontend/src/pages/fechas/[slug].astro` (reescritura del frontmatter y del `<main>`)
- Test: `npx astro check` + smoke HTTP

**Interfaces:**
- Consumes: `getStageSummary(slug)` de la Task 2.1.
- Produces: página con hero de datos reales + 4 bloques nuevos.

- [ ] **Step 1: Eliminar el mock y conectar el endpoint**

En el frontmatter de `frontend/src/pages/fechas/[slug].astro`:
- **Borrar** el objeto `stagesDb` completo (líneas ~15-92 en el estado actual).
- **Borrar** el bloque `try { fetch(...) } catch (e) {}` que parcheaba el mock.
- Reemplazar por:

```ts
const { slug } = Astro.params;

let summary: StageSummary | null = null;
let notFound = false;
try {
  summary = await getStageSummary(String(slug));
} catch (e) {
  if (e instanceof Error && e.message === 'stage-not-found') {
    notFound = true;
    Astro.response.status = 404;
  } else {
    Astro.response.status = 503;   // el backend no responde: nunca hay datos ficticios
  }
}
```

- [ ] **Step 2: Verificar que no queda ningún dato literal**

Run: `grep -n "stagesDb\|scratch: {\|farolito: {\|strava: \[" "frontend/src/pages/fechas/[slug].astro"`
Expected: sin coincidencias (código de salida 1).

- [ ] **Step 3: Renderizar el hero con datos reales**

El hero pasa a usar: `summary.stage.title` (con fallback a `summary.stage.name` sin el prefijo `Fecha N:`), `summary.stage.date`, `summary.stage.start_location`, `summary.stage.start_time`, `summary.stats.distance_km_per_lap` / `distance_km_total`, `summary.stats.elevation_m_per_lap` / `elevation_m_total`.

Regla de display:
```ts
const distLabel = summary.stats.laps > 1
  ? `${summary.stats.distance_km_per_lap} KM × ${summary.stats.laps} VUELTAS = ${summary.stats.distance_km_total} KM`
  : `${summary.stats.distance_km_per_lap} KM`;
const elevLabel = summary.stats.laps > 1
  ? `+${summary.stats.elevation_m_per_lap} M/VUELTA · +${summary.stats.elevation_m_total} M TOTAL`
  : `+${summary.stats.elevation_m_per_lap} M`;
```
Esto elimina la contradicción actual (+840 m en el hero vs +280 m en el bloque GPX).

- [ ] **Step 4: Añadir la navegación de campeonato**

Sobre el hero, una fila con:
- Botón `← {prev.stage.short_name}` si `navigation.prev_slug` no es null.
- Botón `{next.stage.short_name} →` si `navigation.next_slug` no es null.
- Badge `[ EN VIVO ]` si `summary.stage.status === 'LIVE'` con enlace a `/en-vivo`.
- Cuenta regresiva si `status === 'REGISTRATION_OPEN'`: reusar la isla `EventCountdown` (`frontend/src/components/svelte/EventCountdown.svelte`) con `client:load` y `targetDate={summary.stage.date}T{summary.stage.start_time}`.

- [ ] **Step 5: Montar los bloques nuevos**

```astro
<StageStatsRow stats={summary.stats} />
<StagePodiumGrid id="podio" podium={summary.podium} />
<StageTeamPodium teams={summary.teams} />
```
Cada bloque se renderiza solo si su colección no está vacía:
- `StageStatsRow` siempre (si `entries_total === 0` muestra el aviso de "cifras no disponibles").
- `StagePodiumGrid` solo si `summary.podium.length > 0`.
- `StageTeamPodium` solo si `summary.teams.length > 0`.

`StagePodiumGrid` acepta un prop `id` opcional para poder enlazarlo desde `resultados.astro` (Task 2.6).

- [ ] **Step 6: Corregir la guardia del farolito**

El bloque de extremos debeIterator sobre `summary.extremes`, no sobre un único objeto:

```astro
{#if summary.extremes.scratch}
  <div class="extreme-card scratch-card">...{summary.extremes.scratch.name}...</div>
{/if}
{#if summary.extremes.farolito}
  <div class="extreme-card farolito-card">...{summary.extremes.farolito.name}...</div>
{/if}
```
Con esto desaparece el TypeError cuando solo existe un extremo.

- [ ] **Step 7: Verificar compilación y render**

Run: `cd frontend && npx astro check` → 0 errores.
Run: `npm run build` → OK.
Run: `curl -s -o /dev/null -w "%{http_code}" http://localhost:4321/fechas/la-joya-extreme` → `200`.
Run: `curl -s -o /dev/null -w "%{http_code}" http://localhost:4321/fechas/no-existe` → `404`.

- [ ] **Step 8: Commit**

```bash
git add "frontend/src/pages/fechas/[slug].astro"
git commit -m "feat: ficha de fecha con datos reales de la BD"
```

### Task 2.3: Los tres componentes nuevos

**Files:**
- Create: `frontend/src/components/StageStatsRow.astro`
- Create: `frontend/src/components/StagePodiumGrid.astro`
- Create: `frontend/src/components/StageTeamPodium.astro`
- Test: `npx astro check` + smoke

**Interfaces:**
- Consumes: `StageStats`, `CategoryPodium[]`, `TeamPodium[]` de `frontend/src/lib/api.ts`.
- Produces: tres componentes estáticos sin JS.

- [ ] **Step 1: `StageStatsRow.astro`**

Props: `{ stats: StageStats }`. Renderiza 6 celdas en una grilla: `INSCRITOS`, `FINALIZARON`, `NO FINALIZARON`, `PUNTOS`, `VEL. GANADOR` (`{stats.winner_avg_speed_kmh} KM/H`), `CATEGORÍAS`. Estilo: `SectionLabel` + grid `repeat(auto-fit, minmax(9rem, 1fr))` con hairline de 1px, cifras en `var(--font-mono)` con `font-variant-numeric: tabular-nums`.

Si `stats.entries_total === 0` (fecha no disputada), renderizar un mensaje: `CIFRAS DE JORNADA — DISPONIBLES AL CERRAR LA FECHA` en vez de ceros.

- [ ] **Step 2: `StagePodiumGrid.astro`**

Props: `{ id?: string; podium: CategoryPodium[] }`. Un bloque por categoría: título con `short_code` + `category_name`, y 3 filas con puesto, dorsal (`#{bib}`), nombre (enlace a `/corredor/{rider_slug}`), club (enlace a `/equipos/{team_slug}` si existe), tiempo mono tabular y puntos. En móvil, cada categoría es una lista de 3 filas apiladas, sin tabla. El `id` opcional se aplica al contenedor raíz (lo usa Task 2.6 para el enlace `#podio`).

- [ ] **Step 3: `StageTeamPodium.astro`**

Props: `{ teams: TeamPodium[] }`. 3 tarjetas: nombre del club (enlace a `/equipos/{team_slug}`), puntos sumados en la jornada, número de corredores que puntuaron, mejor puesto alcanzado. Usar los colores del podio (`--podium-1/2/3` de `frontend/src/styles/tokens.css`) para 1/2/3.

- [ ] **Step 4: Verificar**

Run: `cd frontend && npx astro check` → 0 errores.
Run: `npm run build` → OK.
Verificar en el navegador que `/fechas/la-joya-extreme` muestra 11 bloques de podio, 3 tarjetas de equipo y 6 cifras de jornada.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/StageStatsRow.astro frontend/src/components/StagePodiumGrid.astro frontend/src/components/StageTeamPodium.astro
git commit -m "feat: bloques de stats, podio por categoria y podio de equipos"
```

### Task 2.4: El mapa real (reescritura de `RouteMapGpx`)

**Files:**
- Modify: `frontend/src/components/svelte/RouteMapGpx.svelte` (reescritura completa)
- Test: `npx astro check` + verificación visual en navegador

**Interfaces:**
- Consumes: props
  ```ts
  interface Props {
    stageName: string;
    routeGeoJson: RouteGeoJson | null;   // geometría real de la BD
    checkpoints: Checkpoint[];           // Partida / Intermedios / Meta
    distanceKm: number;                  // por vuelta
    elevationGainM: number;              // por vuelta
    gpxUrl?: string;
  }
  ```
- Produces: mapa SVG con la ruta proyectada, markers de checkpoint y altimetría sincronizada.

- [ ] **Step 1: Escribir el test visual manual como criterio de aceptación**

Antes de codificar, fijar el criterio:
- La traza de la ruta debe ocupar el ancho del contenedor y ser geométricamente correcta (la silueta de La Joya es reconocible).
- Deben aparecer 3 markers: Partida, Control Intermedio Cumbre, Meta Final.
- El tooltip del marker muestra el km y la altitud interpolados de la propia geometría.
- Ningún valor numérico se inventa: sin `Math.sin`, sin fallback aleatorio.

- [ ] **Step 2: Reescribir el componente**

Estructura:
```ts
let { stageName, routeGeoJson, checkpoints, distanceKm, elevationGainM, gpxUrl }: Props = $props();

let activeDistance = $state(0);

/** Proyecta [lon, lat, ele, dist] a un viewBox normalizado (0..100 x 0..100). */
let projected = $derived.by(() => projectRoute(routeGeoJson));

/** Punto de la traza más cercano al km activo. */
let activePoint = $derived.by(() => nearestPoint(projected, activeDistance));
```
`projectRoute` calcula el bbox de lon/lat, aplica un margen del 6% y mapea a un viewBox de 100×100 conservando la relación de aspecto (`preserveAspectRatio="xMidYMid meet"`), de modo que la geometría no se deforma. La altimetría se dibuja como un segundo SVG bajo el mapa, con el mismo eje X de km.

El rango del slider es `distanceKm` (por vuelta) y el valor por defecto 0. Al mover el slider, el marker del mapa se desplaza al punto interpolado de la geometría (no a una fórmula).

**Eliminar**: el bloque `activePoint` con `Math.sin(...)` (líneas ~67-85 del estado actual), el `svgPath` derivado con `Math.min/max` sobre `points` (líneas ~88-102) y el `$effect` que hace `fetch(gpxUrl)` y parsea el GPX en cliente (líneas ~33-64): la geometría ya viene del servidor en `route_geojson`.

- [ ] **Step 3: Verificar compilación**

Run: `cd frontend && npx astro check` → 0 errores, 0 warnings.

- [ ] **Step 4: Verificar visualmente**

Run: `npm run build` y servir; luego con `browser-use`:
```python
new_tab("http://localhost:4321/fechas/la-joya-extreme")
# comprobar que el SVG tiene un path con d de longitud > 1000
# comprobar que hay 3 elementos .chk-marker
```
Expected: la traza dibujada, 3 markers, sin `Math.sin` en el bundle.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/svelte/RouteMapGpx.svelte
git commit -m "feat: mapa vectorial real desde route_geojson con checkpoints"
```

### Task 2.5: Premios y Strava con datos de la API

**Files:**
- Modify: `frontend/src/pages/fechas/[slug].astro`

**Interfaces:**
- Consumes: `summary.awards`, `summary.strava` de la Task 2.1.

- [ ] **Step 1: Sustituir los premios hardcodeados**

Borrar los dos `<div class="award-box">` fijos con `/images/premio_coca.jpg` y `/images/rey_montana.jpg` y el texto inventado. En su lugar:

```astro
{#if summary.awards.length}
  <section class="awards-section">
    <SectionLabel number="05" label="PREMIOS DE LA JORNADA" />
    <div class="awards-grid">
      {summary.awards.map((a) => (
        <div class="award-box" data-reveal>
          {a.sponsor_logo_url && <img src={a.sponsor_logo_url} alt={a.sponsor_name ?? a.title} class="award-img" />}
          <div class="award-content">
            <h3 class="award-heading">{a.title}</h3>
            {a.sponsor_name && <p class="award-sponsor font-mono">PATROCINADOR: {a.sponsor_name}</p>}
            <p class="award-text">{a.prize_description}</p>
            {a.metric_value && <p class="award-text">{a.metric_value}</p>}
            {a.winner_name && <p class="award-winner font-mono">GANADOR: {a.winner_name}</p>}
          </div>
        </div>
      ))}
    </div>
  </section>
{/if}
```
La imagen del premio ahora sale de `a.sponsor_logo_url` (que en la BD apunta a `/images/premio_coca.jpg` y `/images/rey_montana.jpg`), no de una ruta fija en el código.

- [ ] **Step 2: Sustituir el bloque Strava**

Reemplazar el `seg.kom` por `seg.kom` (que ahora es el effort con `is_kom_qom`) y añadir el top-5 de la tabla de tiempos:

```astro
{summary.strava.map((seg) => (
  <div class="strava-card" data-reveal>
    <div class="strava-header">
      <span class="strava-logo">SEGMENTO OFICIAL // STRAVA</span>
      <span class="strava-grade">{seg.average_grade}% PEND. MEDIA</span>
    </div>
    <div class="strava-name">{seg.name}</div>
    <div class="strava-dist">DISTANCIA OFICIAL: {seg.distance_km} KM</div>
    {seg.kom && (
      <div class="strava-kom"><span class="kom-label">RÉCORD KOM:</span> {seg.kom.athlete_name} ({seg.kom.formatted_time})</div>
    )}
    <ol class="strava-board">
      {seg.efforts.slice(0, 5).map((e, i) => (
        <li><span class="board-rank">{i + 1}º</span><span class="board-name">{e.athlete_name}</span><span class="board-time font-mono">{e.formatted_time}</span></li>
      ))}
    </ol>
    <a class="strava-link font-mono" href={`https://www.strava.com/segments/${seg.strava_segment_id}`} target="_blank" rel="noopener noreferrer">VER EN STRAVA ↗</a>
  </div>
))}
```

- [ ] **Step 3: Verificar**

Run: `cd frontend && npx astro check` → 0 errores.
Verificar en navegador que los 2 segmentos de La Joya muestran su top-5 y el enlace a Strava.

- [ ] **Step 4: Commit**

```bash
git add "frontend/src/pages/fechas/[slug].astro"
git commit -m "feat: premios y segmentos strava desde la API"
```

### Task 2.6: Enlace de la tabla de resultados a la ficha

**Files:**
- Modify: `frontend/src/pages/fechas/[slug]/resultados.astro`
- Test: `npx astro check` + smoke HTTP

**Interfaces:**
- Consumes: nada nuevo. La página ya llama a `${API_V1}/stages/${slug}/results`.

- [ ] **Step 1: Añadir el enlace de retorno con contexto**

En el `header-box` de `frontend/src/pages/fechas/[slug]/resultados.astro`, el breadcrumb actual es `← VOLVER A LA FICHA DE LA FECHA`. Reemplazarlo por dos enlaces con datos reales de la ficha: el nombre de la fecha y el número de categorías participantes.

```astro
<div class="breadcrumb font-mono">
  <a href={`/fechas/${slug}`}>← VOLVER A LA FICHA</a>
  <span class="breadcrumb__sep">/</span>
  <span>{stageName}</span>
</div>
```
`stageName` ya se calcula en el frontmatter (línea ~27) como `stageData?.stage?.name`.

- [ ] **Step 2: Añadir el enlace al podio por categoría**

Debajo del título, un enlace que salte al bloque de podio de la ficha:

```astro
<a href={`/fechas/${slug}#podio`} class="btn btn--ghost font-mono">PODIO POR CATEGORÍA ↑</a>
```
Y en `frontend/src/pages/fechas/[slug].astro`, el bloque `StagePodiumGrid` debe llevar `id="podio"`.

- [ ] **Step 3: Verificar**

Run: `cd frontend && npx astro check` → 0 errores.
Run: `curl -s -o /dev/null -w "%{http_code}" http://localhost:4321/fechas/la-joya-extreme/resultados` → `200`.
Comprobar en navegador que el enlace al podio lleva a la sección correcta.

- [ ] **Step 4: Commit**

```bash
git add "frontend/src/pages/fechas/[slug]/resultados.astro"
git commit -m "feat: enlazar la tabla de resultados con el podio de la ficha"
```

---

## Fase 3 — Cierre, spec y calidad

### Task 3.1: Sincronizar la spec con lo que existe

**Files:**
- Modify: `specs/03-public-portal-and-gpx.md` §1.2 y §0.2

- [ ] **Step 1: Reescribir §1.2 con los bloques reales**

La sección debe listar: hero con datos de BD, navegación prev/next, cinta de cifras de jornada, podio por categoría (11), podio de equipos de la jornada, mapa vectorial desde `route_geojson` con checkpoints, segmentos Strava con top-10 y enlace, premios con ganador, botón a resultados.

Eliminar de §1.2: la mención a **MapLibre GL** (el mapa es SVG nativo), la **galería R2 con lightbox** (no hay `gallery_r2_prefix` sembrado ni endpoint) salvo que se implemente en una fase posterior, y el **marcador de checkpoints en mapa** si no se completó (sí se completa en 2.4, se queda).

- [ ] **Step 2: Documentar el endpoint nuevo**

Añadir a §1.3: `GET /api/v1/stages/{slug}/summary` con su forma de respuesta y su consumidor.

- [ ] **Step 3: Anotar la regla de arranque**

En §0.2: el API debe reiniciarse tras cambios de modelo; en dev usar `uvicorn --reload`; `start.sh` espera la salud del API antes de levantar el frontend.

- [ ] **Step 4: Commit**

```bash
git add specs/03-public-portal-and-gpx.md
git commit -m "docs: sincronizar spec 03 con la ficha de fecha real"
```

### Task 3.2: Barrido de gates

**Files:**
- Test: todo el repo

- [ ] **Step 1: Suite completa del backend**

Run: `PYTHONPATH=. python3 -m pytest backend/tests -v`
Expected: todos en verde (los 42 actuales + los nuevos de `test_stage_summary.py`).

- [ ] **Step 2: Tipos del frontend**

Run: `cd frontend && npx astro check`
Expected: 0 errors, 0 warnings, 0 hints.

- [ ] **Step 3: Build de producción**

Run: `cd frontend && npm run build`
Expected: OK, con `dist/server/entry.mjs`.

- [ ] **Step 4: Cero sintaxis legacy de Svelte**

Run: `grep -rn "export let\|\\$:\|on:click\|on:mouseenter\|svelte/store" frontend/src/components/svelte/`
Expected: sin coincidencias (código de salida 1).

- [ ] **Step 5: Cero mocks en la página de fecha**

Run: `grep -n "stagesDb" "frontend/src/pages/fechas/[slug].astro"`
Expected: sin coincidencias.

- [ ] **Step 6: Smoke de las 4 fechas + 404**

Run:
```bash
for s in la-joya-extreme z-xtreme-2026 vuelta-a-los-poblados quequena-xtreme no-existe; do
  printf "%s -> " "$s"; curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:4321/fechas/$s"
done
```
Expected: `200 200 200 200 404`.

- [ ] **Step 7: Verificación visual con browser-use**

```python
new_tab("http://localhost:4321/fechas/la-joya-extreme")
# comprobar: 11 bloques de podio, 3 tarjetas de equipo, 6 cifras, 3 markers de mapa,
# 2 tarjetas de strava con top-5, 2 premios, botones prev/next
```
Expected: todo presente. Repetir en `/fechas/vuelta-a-los-poblados`: **sin** bloques de podio, de equipos ni de strava, y con el mensaje de cifras no disponibles.

- [ ] **Step 8: Commit final**

```bash
git add -A
git commit -m "chore: gates finales del rediseño de la ficha de fecha"
```

---

## Fuera de alcance (se documenta, no se implementa aquí)

| Ítem | Motivo |
| :--- | :--- |
| Galería fotográfica R2 con lightbox | `gallery_r2_prefix` es NULL en las 4 fechas y no hay endpoint. Requiere sembrar las fotos en R2 primero. |
| MapLibre GL | Requisito real solo si se quiere fondo de mapa. El SVG vectorial cubre la necesidad actual sin dependencia nueva ni tiles de terceros. |
| Cronometraje en vivo dentro de la ficha | `/en-vivo` ya cubre el caso con SSE. |
| PWA del juez | Fuera del alcance de la página de carrera. |
| Content editorial (reglamento, logística, historia) | Requiere texto del organizador. La ficha expone datos; el copy editorial se añade después con contenido real. |

---

## Orden de ejecución y dependencias

```
Fase 0  Task 0.1  ──┐
                      ├──► Fase 1 (1.1 → 1.2 → 1.3 → 1.4 → 1.5) ──► Fase 2 (2.1 → 2.2 → 2.3 → 2.4 → 2.5) ──► Fase 3 (3.1 → 3.2)
                      │
                      └──  Todas las tareas de Fase 2 dependen de 1.5 (el endpoint)
```

Tasks 1.1–1.4 son independientes entre sí (mismo archivo, distintas funciones) y se pueden paralelizar en ramas separadas. 2.3 y 2.4 son paralelizables con 2.2 tras 2.1. 3.1 y 3.2 cierran.

**Costo de un error sin detectar:** el riesgo mayor es que el resumen devuelva cifras que no cuadren con el PDF oficial (198/667, 112/555). La Task 1.1 lo blinda con aserciones contra esas cifras exactas, y 3.2 lo re-verifica.
