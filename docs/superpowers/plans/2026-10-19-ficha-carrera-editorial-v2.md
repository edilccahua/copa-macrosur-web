# Plan Maestro v2 — Rediseño Editorial de la Ficha de Carrera (`/fechas/[slug]`)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convertir la ficha de carrera en un documento editorial compacto y denso al estilo GetArtCraft: navegación de fechas protagonista arriba, un leaderboard de podio por categoría sin ruido, tarjetas de referencia de artcraft para los clubes, un ranking KOM/QOM derivado de los segmentos reales, más estadísticas de jornada, y un perfil de altimetría honesto con fondo de mapa cartográfico.

**Architecture:** El backend amplía `GET /stages/{slug}/summary` con tres bloques nuevos (`kom`, `qom`, `climbs`) calculados de la geometría real y de los segmentos Strava, y un `segments` reordenado por tipo (subida / bajada). El frontend sustituye los componentes inventados por adaptaciones de las piezas reales de `copiaartcraft` (`AppCard`, `BentoCard`, `StatValue`) y añade un mapa base con tiles vectoriales (MapLibre + OpenFreeMap) sobre el que se dibuja la ruta.

**Tech Stack:** FastAPI + SQLModel (async) + Pydantic v2 · Astro 5 SSR (`@astrojs/node` standalone) · Svelte 5 Runes estricto · `maplibre-gl` (tiles vectoriales OpenFreeMap, sin API key) · CSS nativo scoped con tokens de `copiaartcraft` · pytest + httpx AsyncClient.

**Spec:** `specs/03-public-portal-and-gpx.md` §1.2 (ficha de fecha), §0 (reglas SSR). `specs/00-domain-schema.md` (entidades). `specs/01-excel-and-scoring.md` §3.1 (escala de puntos). `INTEGRIDAD-DATOS.md` (cifras oficiales).

**Fuente de diseño:** `/home/edilsonc/Documents/copiaartcraft/src/components/` y `src/styles/`. Las piezas de este plan son **adaptaciones** de `AppCard.astro`, `BentoCard.astro`, `StatValue.astro` y `SectionLabel.astro` de ese repositorio, no diseños nuevos.

---

## Global Constraints

- **Cero mocks.** La página no puede contener datos literales. Si la API no responde, la página devuelve **503** (`specs/03` §0.2). Prohibido reintroducir `stagesDb`.
- **Cero Tailwind/Bootstrap** (`AGENTS.md` §2). CSS nativo scoped.
- **Fuente de diseño obligatoria:** los componentes nuevos se adaptan de `copiaartcraft/src/components/`, no se inventan. El mecanismo de acento por tarjeta es el del origen: una clase `app-<slug>` que define `--app` y `--app-ink` (`copiaartcraft/src/styles/tokens.css:141-153`).
- **Geometría editorial:** `border-radius: 0`, hairline de 1px, `--bg-raised`, etiqueta en versalitas con `letter-spacing: 0.14em`, cifras en `--font-mono` con `tabular-nums`.
- **Svelte 5 Runes estrictos:** prohibido `export let`, `$:`, `on:click`, `svelte/store`.
- **Animación pesada solo en escaparate:** la ficha de fecha es página de presentación (autorizada por `AGENTS.md` §2). `maplibre-gl` se carga **solo** en la isla del mapa, con `client:visible`.
- **Sin API keys ni servicios de pago:** el mapa usa tiles vectoriales abiertos (OpenFreeMap), que responden 200 sin credencial. No se usa Google Maps (exige billing ni clave) ni la Static Maps API de Strava (exige token OAuth propio y devuelve PNG con marca de agua). Verificado: `https://tiles.openfreemap.org/styles/liberty` → 200.
- **Cero disco local en runtime:** los tiles se piden al CDN desde el cliente; el servidor no guarda nada.
- **Test Gate (`AGENTS.md` §3.5):** todo cálculo de_altitud, pendiente, KOM/QOM y agregado lleva su test en `pytest` y está en verde antes de cerrar la tarea.
- **Sync (`AGENTS.md` §3.6):** si cambia el contrato de la API o la estructura de la página, `specs/03-public-portal-and-gpx.md` se actualiza en la misma tarea.
- **Pydantic v2:** `.model_dump()`, `.model_validate()`, `ConfigDict(from_attributes=True)`.
- **Errores de negocio:** `422` con `{"detail": ..., "errors": [...]}`.

---

## Review Focus

Cinco modos de fallo que la spec implica y que los tests no cubren hoy. Cada línea tiene su test en la tarea dueña.

1. **La geometría tiene desnivel 0 o casi 0** (una vuelta llana). El perfil de altimetría se dibuja con un rango de altitudes degenerado: dividir por cero o un polígono plano ilegible. → Tarea 5.2, `test_stage_summary.py::test_summary_flat_route_has_degenerate_elevation_range`.
2. **Un circuito por vueltas con `laps > 1`**: la geometría guardada es de **una** vuelta (`route_geojson` cubre 11.83 km en Z Xtreme) pero la carrera son 3. La distancia y el desnivel del perfil deben salir de la geometría, no de `distance_km × laps`; y el perfil debe avisar de que muestra una vuelta, no la carrera completa. → Tarea 5.1, `test_stage_summary.py::test_summary_route_geometry_covers_one_lap_on_lap_circuits`.
3. **Una fecha sin segmentos Strava** (F3, F4): no hay KOM ni QOM. La sección de premios de montaña no debe renderizar tarjetas vacías ni "Sin registros aún". → Tarea 4.2, `test_stage_summary.py::test_summary_segments_without_kom_or_qom_are_empty`.
4. **Una categoría con un solo finisher**: el leaderboard por categoría debe mostrar una fila, no tres, y no inventar los otros dos. → Tarea 3.2, `test_stage_summary.py::test_category_podium_can_have_fewer_than_three_finishers`.
5. **Dos categorías distintas con el mismo nombre corto** (`MASTER A` / `MASTER B` comparten prefijo): el código corto de la categoría (`MSA`, `MSB`) es la clave, no el nombre. Un emparejamiento por prefijo mostraría el podio de la categoría equivocada. → Tarea 4.1, `test_stage_summary.py::test_summary_climbs_are_matched_by_short_code_not_name`.

---

## Mapa de archivos

### Backend — crear
| Archivo | Responsabilidad |
| :--- | :--- |
| `backend/app/services/route_profile_service.py` | Deriva de `route_geojson` la geometría del perfil: altitudes, desnivel positivo acumulado, pendiente por tramo, tramos de subida (≥3%) y bajada (≤-3%), y el punto más alto y el más bajo. |
| `backend/tests/test_route_profile.py` | Tests del servicio de perfil contra la geometría real de cada fecha. |

### Backend — modificar
| Archivo | Cambio |
| :--- | :--- |
| `backend/app/services/stage_summary_service.py` | Añade `compute_route_profile()` y `compute_stage_climbs()`; enriquece `compute_stage_strava()` con `kind` (CLIMB / DESCENT / FLAT) y el `kom`/`qom` de la fecha. |
| `backend/app/models/schemas.py` | Esquemas `RouteProfileRead`, `ClimbSegmentRead`, `StageSummaryRead` extendido (`route_profile`, `climbs`, `kom`, `qom`). |
| `backend/app/routers/stages.py` | Añade los campos nuevos a la respuesta de `/summary`. |

### Frontend — crear
| Archivo | Responsabilidad |
| :--- | :--- |
| `frontend/src/components/StageLeaderboard.astro` | El leaderboard de podio por categoría: una fila por categoría con el recuadro de código y los tres nombres. Sin dorsal, sin tiempo, sin puntos. |
| `frontend/src/components/StageTeamCard.astro` | Adaptación de `copiaartcraft/src/components/AppCard.astro` para un club: recuadro con iniciales, índice, categoría, nombre, texto, estado y etiquetas de medallas. |
| `frontend/src/components/StageHighlightGrid.astro` | Grilla de las tarjetas deMomento de la jornada (bento de 12 columnas). |
| `frontend/src/components/svelte/RouteMapGpx.svelte` (reescribir) | Mapa con fondo cartográfico vectorial + ruta + checkpoints, y perfil de altimetría a escala declarada con líneas de msnm. |

### Frontend — modificar
| Archivo | Cambio |
| :--- | :--- |
| `frontend/src/pages/fechas/[slug].astro` | Navegación de fechas arriba del hero; nuevo orden de secciones; leaderboard; tarjetas de club; más highlights; tarjetas KOM/QOM. |
| `frontend/src/lib/api.ts` | Tipos del perfil, climbs, kom/qom y `StageSummary` extendido. |
| `frontend/src/lib/datetime.ts` | (ya existe) sin cambios. |
| `frontend/src/styles/tokens.css` | Añade la paleta de acento por club (`app-club-*`) usada por las tarjetas. |
| `specs/03-public-portal-and-gpx.md` | §1.2 y §1.4 reescritas con lo que exista al terminar. |

### Frontend — eliminar
| Archivo | Motivo |
| :--- | :--- |
| `frontend/src/components/StagePodiumGrid.astro` | Sustituido por `StageLeaderboard.astro` (leaderboard compacto). |
| `frontend/src/components/StageTeamPodium.astro` | Sustituido por `StageTeamCard.astro` (tarjeta de artcraft). |

---

## Fase 0 — Datos primero (todo lo demás depende de esto)

### Task 0.1: Servicio de perfil de ruta

**Files:**
- Create: `backend/app/services/route_profile_service.py`
- Create: `backend/tests/test_route_profile.py`

**Interfaces:**
- Consumes: `Stage.route_geojson` (FeatureCollection con una LineString de coordenadas `[lon, lat, ele, km]`).
- Produces:
  ```python
  # backend/app/services/route_profile_service.py
  def build_route_profile(
      route_geojson: Optional[Dict[str, Any]],
      *,
      stage_laps: int = 1,
  ) -> Optional[RouteProfileRead]
  ```
  con `RouteProfileRead`:
  ```python
  class RouteProfileRead(BaseModel):
      distance_km: float          # distancia REAL cubierta por la geometría
      elevation_min_m: int
      elevation_max_m: int
      elevation_gain_m: int       # desnivel positivo acumulado real
      elevation_loss_m: int
      mean_grade_pct: float       # pendiente media de la geometría
      max_grade_pct: float        # pendiente máxima por tramo
      max_grade_at_km: float
      geometry_covers_full_stage: bool   # False si la geometría es de una vuelta
      climbs: List[ClimbSegmentRead]     # tramos >= 3% de pendiente
      descents: List[ClimbSegmentRead]   # tramos <= -3%
  ```
  y `ClimbSegmentRead`:
  ```python
  class ClimbSegmentRead(BaseModel):
      label: str            # "SUBIDA 1"
      from_km: float
      to_km: float
      distance_km: float
      gain_m: int
      avg_grade_pct: float
      max_grade_pct: float
      elevation_start_m: int
      elevation_end_m: int
  ```
  **Si `route_geojson` es `None` o tiene menos de 2 coordenadas, devuelve `None`** (no un perfil vacío).

- [ ] **Step 1: Escribir el test que falla**

```python
def test_route_profile_from_real_geometry():
    """El perfil sale de la geometría, no de multiplicar distancia × vueltas."""
    profile = build_route_profile(LA_JOYA_GEOJSON, stage_laps=1)
    assert profile is not None
    assert profile.distance_km == pytest.approx(40.85, abs=0.1)
    assert profile.elevation_min_m == 1632
    assert profile.elevation_max_m == 2281
    assert profile.elevation_gain_m > 0
    assert profile.mean_grade_pct == pytest.approx(1.59, abs=0.15)
    assert profile.max_grade_pct > 30
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `PYTHONPATH=. python3 -m pytest backend/tests/test_route_profile.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_route_profile'`.

- [ ] **Step 3: Implementar `build_route_profile`**

```python
def build_route_profile(route_geojson, *, stage_laps: int = 1) -> Optional[RouteProfileRead]:
    """Deriva el perfil de altimetría de la geometría real de la ruta.

    La geometría se guarda en coordenadas [lon, lat, ele, km]. El desnivel
    positivo se acumula tramo a tramo (como lo hace un GPS), no como la
    diferencia entre el mínimo y el máximo: un vaivén no es un desnivel.

    `geometry_covers_full_stage` es False cuando la geometría cubre una sola
    vuelta de un circuito por vueltas.
    """
```
Algoritmo: recorrer los puntos; acumular `gain` cuando `Δele > 0` y `loss` cuando `Δele < 0`; pendiente del tramo = `Δele / (Δkm × 1000) × 100`; agrupar tramos contiguos con pendiente ≥ 3% en subidas y ≤ -3% en bajadas, con etiqueta correlativa; la geometría cubre la etapa completa si su último `km` es ≥ `0.95 × distance_km × stage_laps` del total de la carrera.

- [ ] **Step 4: Ejecutar y ver que pasa**

Run: `PYTHONPATH=. python3 -m pytest backend/tests/test_route_profile.py -v`
Expected: PASS.

- [ ] **Step 5: Añadir los casos límite del Review Focus**

```python
def test_flat_route_has_degenerate_elevation_range():
    """Una vuelta llana: el rango de altitudes es 0 y no se divide por él."""
    flat = {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {
        "type": "LineString", "coordinates": [[-71.0, -16.0, 100.0, 0.0], [-71.1, -16.0, 100.0, 5.0]]}}]}
    profile = build_route_profile(flat)
    assert profile is not None
    assert profile.elevation_gain_m == 0
    assert profile.elevation_min_m == profile.elevation_max_m == 100
    assert profile.mean_grade_pct == 0.0
    assert profile.climbs == []

def test_route_geometry_covers_one_lap_on_lap_circuits():
    """En un circuito por vueltas la geometría es de UNA vuelta."""
    profile = build_route_profile(Z_XTREME_GEOJSON, stage_laps=3)
    assert profile is not None
    assert profile.distance_km == pytest.approx(11.83, abs=0.1)
    assert profile.geometry_covers_full_stage is False
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/route_profile_service.py backend/tests/test_route_profile.py backend/app/models/schemas.py
git commit -m "feat: servicio de perfil de ruta derivado de la geometria real"
```

### Task 0.2: KOM y QOM de la fecha

**Files:**
- Modify: `backend/app/services/stage_summary_service.py`
- Modify: `backend/app/models/schemas.py`
- Test: `backend/tests/test_stage_summary.py`

**Interfaces:**
- Consumes: `StravaSegment` (con `average_grade` y `distance_m`), `StravaEffort`.
- Produces:
  ```python
  async def compute_stage_kom_qom(session: AsyncSession, stage_id: int) -> Dict[str, Any]
  ```
  Devuelve `{"kom": {...} | None, "qom": {...} | None}` con la forma:
  ```python
  {
      "segment_id": int,
      "strava_segment_id": str,
      "segment_name": str,
      "distance_km": float,
      "average_grade": float,
      "athlete_name": str,
      "formatted_time": str,
      "elapsed_time_sec": int,
  }
  ```
  **Regla:** el **KOM** es el segmento con la **pendiente media positiva más alta** y, a igualdad de pendiente, el más largo. El **QOM** es el de la **pendiente media negativa más pronunciada** (la bajada más empinada) y, a igualdad, el más largo. El efforts que acompaña a cada uno es el más rápido de ese segmento.

- [ ] **Step 1: Escribir el test que falla**

```python
async def test_summary_kom_is_the_steepest_climb_and_qom_the_steepest_descent(async_session):
    """KOM = la subida más empinada; QOM = la bajada más empinada."""
    # Dos segmentos: +6% (subida) y -4% (bajada), más otro plano
    ...
    result = await compute_stage_kom_qom(session, stage.id)
    assert result["kom"]["segment_name"] == "SUBIDA EMPINADA"
    assert result["kom"]["average_grade"] == 6.0
    assert result["qom"]["segment_name"] == "BAJADA EMPINADA"
    assert result["qom"]["average_grade"] == -4.0
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `PYTHONPATH=. python3 -m pytest backend/tests/test_stage_summary.py::test_summary_kom_is_the_steepest_climb_and_qom_the_steepest_descent -v`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Implementar `compute_stage_kom_qom`**

```python
async def compute_stage_kom_qom(session: AsyncSession, stage_id: int) -> Dict[str, Any]:
    """El Rey de la Montaña y la Reina de la Bajada de la fecha.

    KOM: el segmento de subida más empinado (pendiente media positiva mayor);
    a igualdad, el más largo. QOM: el de bajada más empinada (pendiente media
    negativa más pronunciada); a igualdad, el más largo.
    """
```
Consultar los segmentos de la fecha con sus efforts en una sola pasada (reusar el patrón de `compute_stage_strava`).

- [ ] **Step 4: Ejecutar y ver que pasa**

Run: `PYTHONPATH=. python3 -m pytest backend/tests/test_stage_summary.py -v`
Expected: PASS.

- [ ] **Step 5: Añadir el caso sin segmentos del Review Focus**

```python
async def test_summary_segments_without_kom_or_qom_are_empty(async_session):
    """Sin segmentos no hay KOM ni QOM: la sección no renderiza tarjetas vacías."""
    stage = await _seed_stage_with_results(async_session, entries=1, finishers=1, points=10, categories=1)
    result = await compute_stage_kom_qom(session, stage.id)
    assert result["kom"] is None
    assert result["qom"] is None
```

- [ ] **Step 6: Verificar contra la BD real**

```bash
curl -s http://localhost:8000/api/v1/stages/la-joya-extreme/summary | python3 -c "
import sys,json
d=json.load(sys.stdin)
print('KOM:', d.get('kom'))
print('QOM:', d.get('qom'))
"
```
Expected: KOM = `Pte. Quishuarani / Antes bajada a La Joya` (+0.7%, 6.92 km) — el único segmento en subida; QOM = `La Joya Xtreme 26` (-1.6%, 38.80 km) — la única bajada.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/stage_summary_service.py backend/app/models/schemas.py backend/tests/test_stage_summary.py
git commit -m "feat: KOM y QOM de la fecha derivados de los segmentos Strava"
```

### Task 0.3: El resumen expone el perfil y los climbers

**Files:**
- Modify: `backend/app/services/stage_summary_service.py`
- Modify: `backend/app/models/schemas.py`
- Modify: `backend/app/routers/stages.py`
- Test: `backend/tests/test_stage_summary.py`

**Interfaces:**
- Produces: la respuesta de `/summary` gana tres claves:
  ```json
  "route_profile": { ...RouteProfileRead... } | null,
  "kom": { ... } | null,
  "qom": { ... } | null
  ```
  y cada elemento de `strava` gana `"kind": "CLIMB" | "DESCENT" | "FLAT"`.

- [ ] **Step 1: Escribir el test que falla**

```python
async def test_summary_endpoint_includes_route_profile_kom_and_qom(async_session, client):
    """El resumen lleva el perfil de la ruta y los dos titulos de montana."""
    await _seed_stage_with_results(async_session, entries=20, finishers=20, points=200, categories=3)
    res = await client.get("/api/v1/stages/la-joya-extreme/summary")
    assert res.status_code == 200
    body = res.json()
    assert "route_profile" in body
    assert "kom" in body
    assert "qom" in body
    for seg in body["strava"]:
        assert seg["kind"] in {"CLIMB", "DESCENT", "FLAT"}
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `PYTHONPATH=. python3 -m pytest backend/tests/test_stage_summary.py::test_summary_endpoint_includes_route_profile_kom_and_qom -v`
Expected: FAIL — `KeyError: 'route_profile'`.

- [ ] **Step 3: Implementar**

En `compute_stage_strava`, añadir el `kind` de cada segmento según su `average_grade`: `> 0.5` → `CLIMB`, `< -0.5` → `DESCENT`, resto `FLAT`. En el endpoint, añadir `route_profile=build_route_profile(stage.route_geojson, stage_laps=stage.laps)` y `kom`/`qom` de `compute_stage_kom_qom`.

- [ ] **Step 4: Ejecutar y ver que pasa**

Run: `PYTHONPATH=. python3 -m pytest backend/tests/test_stage_summary.py -v`
Expected: PASS.

- [ ] **Step 5: Smoke contra la BD real**

```bash
curl -s http://localhost:8000/api/v1/stages/la-joya-extreme/summary | python3 -c "
import sys,json
d=json.load(sys.stdin)
p=d['route_profile']
print('dist real:', p['distance_km'], '| desnivel real:', p['elevation_gain_m'], '| max pendiente:', p['max_grade_pct'])
print('cubre etapa completa:', p['geometry_covers_full_stage'])
print('subidas:', [(c['label'], c['from_km'], c['to_km'], c['gain_m'], c['avg_grade_pct']) for c in p['climbs']])
print('bajadas:', len(p['descents']))
print('segmentos:', [(s['name'], s['kind'], s['average_grade']) for s in d['strava']])
"
```
Expected: `distance_km 40.85`, `geometry_covers_full_stage True`, y las subidas con el km 7.1 (el muro de 53%) entre ellas.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/stage_summary_service.py backend/app/models/schemas.py backend/app/routers/stages.py backend/tests/test_stage_summary.py
git commit -m "feat: el resumen expone el perfil de ruta, el KOM y el QOM"
```

---

## Fase 1 — El leaderboard de podio (sección 02)

### Task 1.1: Leaderboard de categorías

**Files:**
- Create: `frontend/src/components/StageLeaderboard.astro`
- Delete: `frontend/src/components/StagePodiumGrid.astro`
- Modify: `frontend/src/pages/fechas/[slug].astro`
- Test: `npx astro check` + verificación en navegador

**Interfaces:**
- Consumes: `CategoryPodium[]` de `frontend/src/lib/api.ts` (ya existe, sin cambios).
- Produces: componente estático sin JS.

**Criterio de aceptación (el diseño exacto, medido sobre la referencia):**

La sección 02 pasa de 11 bloques con 6 datos por fila a **una fila por categoría**, con esta estructura (adaptación de `copiaartcraft/src/components/AppCard.astro`, no diseño nuevo):

```
┌──────────────────────────────────────────────────────────────────────┐
│ ▪MSA  MASTER A                                    01:07:55  01:08:58 │  ← 1er puesto
│ RONALD LUZA CALLO · TEAM COLCA BIKE                                  │  ← 2do
│ RODRIGO SANCHEZ · TEAM VULCANO DESERT            01:13:30            │  ← 3er
└──────────────────────────────────────────────────────────────────────┘
```

- **Una fila por categoría.** Inside, tres líneas: una por puesto.
- **El recuadro de la categoría** (el equivalente al `appcard__icon` de artcraft: `1.75rem × 1.75rem`, `background: var(--bg-sunken)`, hairline, `font-display`, `font-size: var(--text-xs)`) lleva el **código corto** de la categoría (`MSA`, `ELI`, `TOV`), **no un número**. Es el ancla visual de la categoría, en la esquina superior izquierda de la fila.
- **El título de la categoría** va a la derecha del recuadro, en `font-display` `var(--text-lg)`.
- **Cada puesto**: nombre completo en `font-weight: 600` (enlace a `/corredor/{slug}`), club debajo en `var(--text-xs)` `var(--muted)`. **Sin dorsal, sin tiempo y sin puntos** (el usuario los pidió fuera: el detalle va en `/fechas/{slug}/resultados`).
- **El tiempo del primer puesto** sí aparece, en la esquina derecha de la primera línea, mono tabular: es el dato que resume la categoría. Los puestos 2º y 3º no llevan tiempo.
- **Animación al pasar por encima** (el hover que pide el usuario): la fila de la categoría levanta su fondo de `var(--bg-raised)` a `var(--bg-sunken)`, el recuadro de la categoría invierte (`background: var(--app-ink)`, `color: var(--bg-raised)`) y el nombre del primer puesto pasa a `var(--accent)`. Todo con `--default-transition-duration` (150ms), sin animación de entrada.

**Colores de acento por categoría:** se deriva del grupo (`PRO` / `NORMAL` / `E-MTB`) con el mecanismo `app-<slug>` del origen: `.app-pro { --app: #2f7bf5; --app-ink: #1a5bc4; }`, `.app-normal { --app: #7bb51c; --app-ink: #457008; }`, `.app-ebike { --app: #f26b1d; --app-ink: #ad4306; }`, más las variantes dark (`copiaartcraft/src/styles/tokens.css:155-167`).

- [ ] **Step 1: Escribir el componente**

`frontend/src/components/StageLeaderboard.astro` con props `{ podium: CategoryPodium[] }`. La categoría se asigna a un grupo por el prefijo del `short_code`: `ELI, MSA, MSB, MSC` → `PRO`; `TOV, TMV, MSD, OPD, DMM, JUV` → `NORMAL`; `EBK` → `E-MTB`. La asignación va en el **backend** (el resumen ya trae `scope` por fila) para no duplicar la tabla de grupos en el frontend: `CategoryPodiumRead` gana un campo `group: str` con el valor `PRO` | `NORMAL` | `E-MTB`.

- [ ] **Step 2: Añadir `group` al schema y al servicio**

`backend/app/models/schemas.py`: `CategoryPodiumRead.group: str`. `backend/app/services/stage_summary_service.py`: `compute_category_podium` calcula el grupo a partir de los `short_code` de las 11 categorías (misma tabla que usa `standings_service.scope_short_codes`). Test:

```python
async def test_category_podium_carries_the_scope_group(async_session):
    """Cada categoría declara su grupo (PRO/NORMAL/E-MTB) para el acento."""
    podium = await compute_category_podium(async_session, stage.id)
    groups = {c.short_code: c.group for c in podium}
    assert groups["MSA"] == "PRO"
    assert groups["TOV"] == "NORMAL"
    assert groups["EBK"] == "E-MTB"
```

- [ ] **Step 3: Sustituir en la página**

En `frontend/src/pages/fechas/[slug].astro`, cambiar `<StagePodiumGrid id="podio" podium={summary.podium} />` por `<StageLeaderboard id="podio" podium={summary.podium} />` y borrar el import de `StagePodiumGrid`. Borrar el archivo `StagePodiumGrid.astro`.

- [ ] **Step 4: Verificar**

Run: `cd frontend && npx astro check` → 0 errores.
Run: `npm run build` → OK.
En navegador: la sección 02 mide menos de la mitad de alto que antes; cada categoría es una fila; el recuadro lleva `MSA`, `ELI`, `TOV`…; el hover invierte el recuadro.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/StageLeaderboard.astro frontend/src/pages/fechas/[slug].astro backend/app/models/schemas.py backend/app/services/stage_summary_service.py backend/tests/test_stage_summary.py
git rm frontend/src/components/StagePodiumGrid.astro
git commit -m "feat: leaderboard compacto de podio por categoria"
```

### Task 1.2: Podio de clubes con la tarjeta de artcraft

**Files:**
- Create: `frontend/src/components/StageTeamCard.astro`
- Delete: `frontend/src/components/StageTeamPodium.astro`
- Modify: `frontend/src/pages/fechas/[slug].astro`
- Test: `npx astro check` + verificación en navegador

**Interfaces:**
- Consumes: `TeamPodium[]` (ya existe en `frontend/src/lib/api.ts`).
- Produces: componente estático sin JS.

**Adaptación de `copiaartcraft/src/components/AppCard.astro`** (el original, línea 21-47), con la ficha de un club:

| Pieza de artcraft | En la tarjeta del club |
| :--- | :--- |
| `appcard__media` + `appcard__initial` | Recuadro 16/10 con las **iniciales del club** en `font-display` `var(--text-5xl)` a `opacity: 0.35` sobre `var(--bg-sunken)` |
| `appcard__head` → `index` + `category` | `01` en mono `var(--text-xs)` `var(--app-ink)` + `CLUB` en versalitas `0.14em` `var(--muted)` |
| `appcard__title-row` → `icon` + `name` | Nombre del club en `font-display` `var(--text-2xl)` peso 620, `letter-spacing: -0.03em` |
| `appcard__text` | Una línea de contexto: `27 corredores en la fecha` |
| `appcard__status` | `107 PTS` en mono `0.6875rem` `var(--app-ink)` |
| `appcard__platforms` | Etiquetas: `3 OROS`, `1 PLATA`, `2 BRONCES` |
| `appcard__explore` | `Ver ficha del club →` |
| `appcard:hover` | `border-color: var(--app)` |

**Acento por posición:** `--app` del 1º es `--podium-1` (oro), del 2º `--podium-2` (plata), del 3º `--podium-3` (bronce); el resto usa `--scope` (magenta de la Copa de Equipos, `tokens.css:175`). Se asigna por clase `app-club-1` / `app-club-2` / `app-club-3` / `app-club-rest`.

- [ ] **Step 1: Escribir el componente**

`frontend/src/components/StageTeamCard.astro` con props `{ teams: TeamPodium[] }`. La tarjeta es un `<article class="appcard app-club-{n}">` con la misma estructura de clases que el original, para que el CSS sea reconocible.

- [ ] **Step 2: Añadir las medallas al resumen**

`TeamPodiumRead` ya trae `points`, `riders_counted` y `best_rank`, pero **no** las medallas. Añadir `first_places: int`, `second_places: int`, `third_places: int` al schema y al servicio:

```python
# en compute_stage_team_podium, añadir al SELECT:
func.sum(func.cast(StageEntry.category_rank == 1, Integer)),
func.sum(func.cast(StageEntry.category_rank == 2, Integer)),
func.sum(func.cast(StageEntry.category_rank == 3, Integer)),
```
Test:
```python
async def test_team_podium_counts_medals(async_session):
    """El podio de clubes expone sus medallas de la jornada."""
    podium = await compute_stage_team_podium(async_session, stage.id)
    assert podium[0].first_places == 3
    assert podium[0].second_places == 1
```

- [ ] **Step 3: Sustituir en la página y borrar el componente viejo**

Cambiar `<StageTeamPodium teams={summary.teams} />` por `<StageTeamCard teams={summary.teams} />`, borrar el import y el archivo `StageTeamPodium.astro`.

- [ ] **Step 4: Verificar**

Run: `cd frontend && npx astro check` → 0 errores; `npm run build` → OK. En navegador: 3 tarjetas con recuadro de iniciales, `01` + `CLUB`, nombre grande, `107 PTS`, etiquetas de medallas y `Ver ficha del club →`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/StageTeamCard.astro frontend/src/pages/fechas/[slug].astro backend/app/models/schemas.py backend/app/services/stage_summary_service.py backend/tests/test_stage_summary.py
git rm frontend/src/components/StageTeamPodium.astro
git commit -m "feat: podio de clubes con la tarjeta de referencia de artcraft"
```

---

## Fase 2 — Los momentos de la jornada (sección 04)

### Task 2.1: Más tarjetas de estadísticas extremas

**Files:**
- Create: `frontend/src/components/StageHighlightGrid.astro`
- Modify: `backend/app/services/stage_summary_service.py`
- Modify: `backend/app/models/schemas.py`
- Modify: `frontend/src/pages/fechas/[slug].astro`
- Test: `backend/tests/test_stage_summary.py`

**Interfaces:**
- Produces: en el resumen, una clave `highlights: List[HighlightRead]`:
  ```python
  class HighlightRead(BaseModel):
      key: str            # "scratch" | "farolito" | "kom" | "qom" | "mean_time" | "biggest_climb" | "top_category" | "top_team"
      label: str          # "SCRATCH // TIEMPO MÁS RÁPIDO EN META"
      value: str          # "01:07:55"
      detail: str         # "RONALD LUZA CALLO · MASTER A"
      meta: Optional[str] # "+384 M EN EL KM 7.1"
  ```
  Criterios de la lista (todos con dato disponible hoy, verificado en la BD):
  1. **Scratch** — el más rápido (ya existe).
  2. **Farolito** — el más lento (ya existe).
  3. **KOM** — mejor escalador del segmento de subida (Task 0.2).
  4. **QOM** — mejor bajador del segmento de bajada (Task 0.2).
  5. **Ritmo medio** — tiempo medio de los que llegaron a meta (`AVG(finish_elapsed_ms)`), formateado.
  6. **Mayor subida** — el tramo de subida con más desnivel acumulado (del perfil, Task 0.1): `"+184 M EN EL KM 7.1"`.
  7. **Categoría más poblada** — la de más inscritos: `"MASTER B · 48 CORREDORES"`.
  8. **Club más numeroso** — el de más corredores en la fecha: `"CLUB ORIGINAL BIKES · 27"`.

- [ ] **Step 1: Escribir el test que falla**

```python
async def test_summary_highlights_cover_the_eight_moments(async_session):
    """La jornada expone los ocho momentos con dato real."""
    stage = await _seed_stage_with_results(async_session, entries=20, finishers=18, points=180, categories=3)
    highlights = await compute_stage_highlights(session, stage.id)
    keys = {h.key for h in highlights}
    assert {"scratch", "farolito", "mean_time", "top_category"} <= keys
    for h in highlights:
        assert h.value  # nunca vacío
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `PYTHONPATH=. python3 -m pytest backend/tests/test_stage_summary.py::test_summary_highlights_cover_the_eight_moments -v`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Implementar `compute_stage_highlights`**

```python
async def compute_stage_highlights(session: AsyncSession, stage_id: int) -> List[HighlightRead]:
    """Los momentos de la jornada: los ocho datos que la resumen.

    Solo se incluye un momento si hay dato para él (una fecha sin segmentos
    no tiene KOM; una fecha sin meta no tiene scratch).
    """
```
Reutiliza `compute_stage_extremes`, `compute_stage_kom_qom` y `build_route_profile`.

- [ ] **Step 4: Ejecutar y ver que pasa**

Run: `PYTHONPATH=. python3 -m pytest backend/tests/test_stage_summary.py -v`
Expected: PASS.

- [ ] **Step 5: Añadir el caso de categoría con pocos finalistas del Review Focus**

```python
async def test_category_podium_can_have_fewer_than_three_finishers(async_session):
    """Una categoría con un solo 수입ido devuelve una fila, no tres."""
    # ...
    podium = await compute_category_podium(async_session, stage.id)
    assert len(podium) == 1
    assert len(podium[0].entries) == 1
```

- [ ] **Step 6: Montar el componente**

`frontend/src/components/StageHighlightGrid.astro` con props `{ highlights: HighlightRead[] }`. Rejilla de **12 columnas** como el bento de artcraft (`copiaartcraft/src/components/bento/BentoCard.astro:179-195`): el scratch ocupa `span 6`, el farolito `span 6`, el KOM `span 4`, el QOM `span 4`, el ritmo medio `span 4`, y los tres restantes `span 4` cada uno. Cada tarjeta: `border: var(--hairline) solid var(--line)`, `background: var(--bg-raised)`, `border-radius: var(--radius)` (0), etiqueta en versalitas `0.14em` `var(--faint)`, valor en `font-display` `var(--text-2xl)`, detalle en `var(--text-sm)` `var(--muted)`.

- [ ] **Step 7: Sustituir la sección de extremos en la página**

Borrar el bloque `extremes-section` actual (las dos tarjetas escritas a mano) y montar `<StageHighlightGrid highlights={summary.highlights} />` dentro de la sección 04.

- [ ] **Step 8: Verificar**

Run: `cd frontend && npx astro check` → 0 errores; `npm run build` → OK. En navegador: 8 tarjetas con dato real.

- [ ] **Step 9: Commit**

```bash
git add backend/app/services/stage_summary_service.py backend/app/models/schemas.py backend/tests/test_stage_summary.py frontend/src/components/StageHighlightGrid.astro frontend/src/pages/fechas/[slug].astro
git commit -m "feat: ocho momentos de la jornada en la seccion de extremos"
```

---

## Fase 3 — Strava con la regla KOM/QOM (sección 06)

### Task 3.1: Reordenar los segmentos por tipo y destacar el KOM/QOM

**Files:**
- Modify: `frontend/src/pages/fechas/[slug].astro`
- Test: `npx astro check` + verificación en navegador

**Interfaces:**
- Consumes: `summary.strava[]` con el nuevo campo `kind`, y `summary.kom` / `summary.qom`.

- [ ] **Step 1: Ordenar los segmentos**

En la página, ordenar antes de renderizar: primero los `CLIMB`, después los `DESCENT`, después los `FLAT`; dentro de cada grupo, por distancia descendente. El segmento del KOM de la fecha va primero entre los `CLIMB` y el del QOM primero entre los `DESCENT`.

- [ ] **Step 2: Marcar visualmente el KOM y el QOM**

La tarjeta del segmento que es KOM lleva el borde superior de acento (`box-shadow: inset 0 3px 0 0 var(--podium-1)`) y una etiqueta `[ KING OF THE MOUNTAIN ]`; la del QOM, `[ QUEEN OF THE MOUNTAIN ]` con `--podium-2`. El rótulo del premio de la sección 07 (que hoy es genérico) pasa a decir **qué segmento es el KOM de la fecha**.

- [ ] **Step 3: Mostrar el KOM y el QOM en su propia tarjeta**

Encima de la grilla de segmentos, dos tarjetas: **"MEJOR ESCALADOR — KING OF THE MOUNTAIN"** (con el nombre del segmento, su pendiente media, su longitud y el tiempo del mejor) y **"MEJOR BAJADOR — QUEEN OF THE MOUNTAIN"** (idem). Si no hay dato, la tarjeta no se renderiza.

- [ ] **Step 4: Verificar**

Run: `cd frontend && npx astro check` → 0 errores; `npm run build` → OK. En navegador, F1: el KOM es `Pte. Quishuarani` (+0.7%, 6.92 km) y el QOM es `La Joya Xtreme 26` (-1.6%, 38.80 km); el orden de la grilla empieza por la subida.

- [ ] **Step 5: Commit**

```bash
git add "frontend/src/pages/fechas/[slug].astro"
git commit -m "feat: segmentos ordenados por tipo con KOM y QOM destacados"
```

---

## Fase 4 — El perfil técnico y el mapa (sección 05)

### Task 4.1: Mapa con fondo cartográfico

**Files:**
- Modify: `frontend/src/components/svelte/RouteMapGpx.svelte` (reescritura)
- Modify: `frontend/package.json` (añadir `maplibre-gl`)
- Test: `npx astro check` + verificación en navegador

**Interfaces:**
- Consumes: props
  ```ts
  interface Props {
    stageName: string;
    routeGeoJson: RouteGeoJson | null;
    checkpoints: Checkpoint[];
    distanceKm: number;
    elevationGainM: number;
    gpxUrl?: string;
  }
  ```
- Produces: mapa con tiles vectoriales de fondo + la ruta de la BD encima.

**Decisión de fondo de mapa (medida):**

| Opción | Estado verificado | Veredicto |
| :--- | :--- | :--- |
| **OpenFreeMap** (vector, sin key) | `tiles.openfreemap.org/styles/liberty` → **200**; tile `.pbf` → **200** | **Elegida** |
| OSM raster | `tile.openstreetmap.org/12/1925/2730.png` → 200 | Alternativa de reserva (más pesada, sin vectorial) |
| Google Static Maps | `maps.googleapis.com/…` → **400** sin key; exige billing y expone la clave | Descartada |
| Strava Static Maps | `api.strava.com/v3/maps/static` → sin token OAuth | Descartada (el proyecto no tiene API token; su sync Strava es por CDP) |

- [ ] **Step 1: Instalar la dependencia**

```bash
cd frontend && npm install maplibre-gl
```
Solo se usa en la isla del mapa, con `client:visible` (ya es el caso). No se carga en `/en-vivo` ni en `/admin/juez` (`AGENTS.md` §2).

- [ ] **Step 2: Configurar el estilo oscuro**

Crear el estilo en el propio componente (no una dependencia de un archivo externo): un `StyleSpecification` con `sources: { ofm: { type: 'vector', url: 'https://tiles.openfreemap.org/planet' } }` y las capas de agua, vía yondrous en los colores del tema: `--bg-sunken` (#060607), líneas en `#2a2d33`, y la ruta en `--accent` (#2d81ff). Se **oscurece** el mapa base con un `raster` de velo negro a 0.35 para que la ruta naranja (`--accent` del portal, #ff5500 en el tema de ruta) destaque.

- [ ] **Step 3: Montar el mapa**

Inicializar `maplibregl.Map` en un `$effect` con cleanup (`map.remove()`), `center` en el centroide del `route_geojson`, `zoom` calculado del bbox, y una fuente GeoJSON con la línea de la ruta en `#ff5500`, `line-width: 3`, `line-join: round`. Los checkpoints van como marcadores circulares con etiqueta (`Partida`, `Control Intermedio Cumbre`, `Meta Final`).

- [ ] **Step 4: Mantener el SVG como respaldo**

Si `routeGeoJson` es `null`, se mantiene el render SVG actual (sin tiles) para no romper las fechas sin geometría.

- [ ] **Step 5: Verificar**

Run: `cd frontend && npx astro check` → 0 errores; `npm run build` → OK.
En navegador: el mapa de La Joya muestra calles de fondo y la ruta naranja encima; los 3 checkpoints marcados; la consola sin errores de red.

- [ ] **Step 6: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/components/svelte/RouteMapGpx.svelte
git commit -m "feat: mapa con fondo cartografico vectorial sobre la ruta real"
```

### Task 4.2: Perfil de altimetría honesto con líneas de msnm

**Files:**
- Modify: `frontend/src/components/svelte/RouteMapGpx.svelte`
- Modify: `frontend/src/lib/api.ts` (tipos del perfil)
- Test: `npx astro check` + medición en navegador

**Interfaces:**
- Consumes: la prop `routeProfile: RouteProfileRead | null` (nueva).
- Produces: el perfil con escala vertical declarada.

**El defecto que se corrige (medido):** el perfil actual mapea el desnivel **siempre** al 82% del alto del gráfico (`RouteMapGpx.svelte`, `elevationPath`), con independencia del desnivel real. Medido sobre las tres rutas:

| Fecha | Pendiente media real | Lo que se ve | Exageración |
| :--- | :--- | :--- | :--- |
| La Joya | 1.59 % | 82 % | **×52** |
| Z Xtreme | 2.22 % | 82 % | **×37** |
| Poblados | 1.93 % | 82 % | **×43** |

Una ruta de 40 km con 650 m de desnivel dibujada a escala isométrica ocupa 1.6 unidades de 100: una línea casi plana. El perfil actual la convierte en un zigzag montagne que no existe.

- [ ] **Step 1: Añadir los tipos del perfil al cliente**

`frontend/src/lib/api.ts`:
```ts
export interface ClimbSegment {
  label: string;
  from_km: number;
  to_km: number;
  distance_km: number;
  gain_m: number;
  avg_grade_pct: number;
  max_grade_pct: number;
  elevation_start_m: number;
  elevation_end_m: number;
}
export interface RouteProfile {
  distance_km: number;
  elevation_min_m: number;
  elevation_max_m: number;
  elevation_gain_m: number;
  elevation_loss_m: number;
  mean_grade_pct: number;
  max_grade_pct: number;
  max_grade_at_km: number;
  geometry_covers_full_stage: boolean;
  climbs: ClimbSegment[];
  descents: ClimbSegment[];
}
```
Y `StageSummary` gana `route_profile: RouteProfile | null`.

- [ ] **Step 2: Dibujar el perfil con escala declarada**

El perfil usa la geometría real (`route_geojson`), no el perfil agregado. La escala vertical se declara en pantalla: el componente calcula la **exageración** que hace falta para que el desnivel ocupe el 55% del alto y la rotula (`ESCALA VERTICAL ×12` o `PROPORCIONAL` si la isométrica cabe). Con la isométrica real, La Joya daría una línea plana: por eso la exageración se declara, pero **se declara el número**, que es lo que un lector de mapas necesita.

Reimplementar `elevationPath` con:
- Eje X: kilómetros reales (`km` de cada punto).
- Eje Y: altitud real, mapeada al rango de la geometría.
- El factor de exageración se calcula y se muestra.

- [ ] **Step 3: Añadir las líneas de msnm**

Sobre el SVG del perfil, una retícula horizontal con **5 líneas de altitud** (mínimo, máximo y tres intermedias equiespaciadas), cada una con su etiqueta en msnm a la derecha, en `var(--faint)` mono `0.6875rem`, y una línea vertical en el km activo. Retícula vertical cada 5 km con su etiqueta.

- [ ] **Step 4: Marcar los tramos de subida y bajada**

Del perfil (`routeProfile.climbs` / `.descents`), marcar en el SVG los tramos con la pendiente ≥3% con una banda `var(--accent)` al 12% de opacidad, y los de bajada con una banda `var(--status-down)` al 10%. La banda del tramo con más desnivel va marcada con su etiqueta (`+184 M · KM 7.1`).

- [ ] **Step 5: Avisar del circuito por vueltas**

Si `routeProfile.geometry_covers_full_stage === false`, el bloque muestra bajo el título: `PERFIL DE UNA VUELTA (11.83 KM) — LA CARRERA SON 3 VUELTAS`. Es un dato que hoy no aparece en ninguna parte y desorienta.

- [ ] **Step 6: Verificar la escala declarada**

En el navegador, para La Joya el rótulo debe mostrar una exageración **explícita** y el perfil debe ocupar un alto razonable. Comprobación numérica: la pendiente media que se ve multiplicada por la exageración declarada debe ser la real (±0.1%).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/api.ts frontend/src/components/svelte/RouteMapGpx.svelte "frontend/src/pages/fechas/[slug].astro"
git commit -m "feat: perfil de altimetria con escala declarada y lineas de msnm"
```

---

## Fase 5 — Navegación, orden y cierre

### Task 5.1: Navegación de fechas arriba y notoria

**Files:**
- Modify: `frontend/src/pages/fechas/[slug].astro`
- Test: `npx astro check` + verificación en navegador

**Interfaces:**
- Consumes: `summary.navigation` (ya existe).

- [ ] **Step 1: Mover la navegación**

Sacar el `<nav class="stage-nav">` del pie del hero y ponerlo **encima del hero**, en una fila propia, antes del poster. Es lo que el usuario pide: "las flechas de siguiente/anterior carrera estén arriba al inicio, y más notorias".

- [ ] **Step 2: Hacerla notoria**

En vez de texto mono de 11px con un `←` suelto, usar dos bloques a los extremos de la fila, con:
- la **flecha grande** (SVG de 16px, `stroke-width: 1.5`) en el color del acento,
- el **nombre de la fecha** en `font-display` `var(--text-base)` peso 620,
- la **etiqueta** `FECHA ANTERIOR` / `FECHA SIGUIENTE` en versalitas `0.14em` `var(--faint)`,
- `border: var(--hairline) solid var(--line)` y `background: var(--bg-raised)`,
- **hover**: `border-color: var(--line-strong)`, la flecha pasa a `var(--accent)` y la fila se desplaza 2px hacia su lado (`transform: translateX(±2px)`), 150ms.

El bloque vacío (no hay fecha anterior) se oculta por completo en vez de dejar una flecha huérfana.

- [ ] **Step 3: Verificar**

Run: `cd frontend && npx astro check` → 0 errores; `npm run build` → OK. En navegador: la navegación aparece arriba de todo, con los dos bloques y su hover.

- [ ] **Step 4: Commit**

```bash
git add "frontend/src/pages/fechas/[slug].astro"
git commit -m "feat: navegacion de fechas arriba del hero y notoria"
```

### Task 5.2: Orden final de secciones y sincronización de la spec

**Files:**
- Modify: `frontend/src/pages/fechas/[slug].astro`
- Modify: `specs/03-public-portal-and-gpx.md`
- Test: suite completa

**Interfaces:**
- Produce: el orden final de la ficha.

- [ ] **Step 1: Fijar el orden**

| # | Sección | Origen |
| :--- | :--- | :--- |
| 00 | Navegación de fechas (arriba del hero) | `summary.navigation` |
| 01 | CIFRAS DE LA JORNADA | `StageStatsRow` |
| 02 | PODIO OFICIAL POR CATEGORÍA | `StageLeaderboard` |
| 03 | PODIO DE CLUBES DE LA FECHA | `StageTeamCard` (tarjeta artcraft) |
| 04 | ESTADÍSTICAS EXTREMAS DE LA JORNADA | `StageHighlightGrid` (8 tarjetas) |
| 05 | PERFIL TÉCNICO Y RUTA DE CARRERA | `RouteMapGpx` (mapa + perfil) |
| 06 | SEGMENTOS OFICIALES STRAVA (KOM / QOM) | `summary.strava` + `summary.kom` / `summary.qom` |
| 07 | PREMIOS DE LA JORNADA | `summary.awards` |

La numeración sigue siendo dinámica (consecutiva, sin huecos) como ya está implementado.

- [ ] **Step 2: Reescribir §1.2 de la spec**

Describir lo que existe: navegación arriba, leaderboard compacto, tarjetas de club de artcraft, ocho momentos, mapa con fondo cartográfico, perfil con escala declarada y líneas de msnm, KOM/QOM por tipo de segmento, premios desde la BD. Eliminar las referencias a cosas que no existen (MapLibre como "opción", galería R2).

- [ ] **Step 3: Documentar la regla KOM/QOM en §1.4**

Anotar que el KOM es el segmento de subida más empinado y el QOM el de bajada más empinada, y que `is_kom_qom` es la marca del efforts dentro de un segmento (no la elección del segmento).

- [ ] **Step 4: Suite completa**

Run: `PYTHONPATH=. python3 -m pytest backend/tests -q` → todos en verde.
Run: `cd frontend && npx astro check` → 0 errores, 0 warnings, 0 hints.
Run: `cd frontend && npm run build` → OK.

- [ ] **Step 5: Verificación visual de las 4 fechas**

Las 4 fechas en 200; el slug inexistente en 404; con el API parado, 503. En navegador, en cada fecha: la navegación arriba, el leaderboard compacto, las 8 tarjetas de momentos, el mapa con fondo, el perfil con escala declarada, y los segmentos ordenados por tipo.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "docs: sincronizar spec 03 con la ficha de carrera editorial"
```

---

## Fuera de alcance (se documenta, no se implementa aquí)

| Ítem | Motivo |
| :--- | :--- |
| Galería fotográfica R2 con lightbox | `gallery_r2_prefix` es NULL en las 4 fechas y no hay endpoint. Requiere sembrar las fotos en R2. |
| Parciales por checkpoint | `timing_events` tiene 0 filas: no hay tiempos intermedios capturados. Cuando el juez los registre, se podrá añadir "mejor en el control intermedio". |
| Mapa de Strava o Google | Medido: Strava exige token OAuth propio y devuelve PNG con marca de agua; Google exige billing y expone la clave. Se usa OpenFreeMap, que responde 200 sin credencial. |
| Strava en vivo (leaderboard de efforts) | El sync de Strava es local por CDP (skill `strava-playwright`); no hay token de API para consultar en vivo desde el servidor. |
| Copy editorial (reglamento, logística, historia) | Requiere texto del organizador. |

---

## Orden de ejecución y dependencias

```
Fase 0 (0.1 → 0.2 → 0.3) ──► Fase 1 (1.1 → 1.2) ──► Fase 2 (2.1) ──► Fase 3 (3.1) ──► Fase 4 (4.1 → 4.2) ──► Fase 5 (5.1 → 5.2)
        │                        │                      │                        │
        │                        └── Fase 2 necesita kom/qom de 0.2 ─────────────┘
        └── Fase 4.2 necesita el perfil de 0.1 y el group de 1.1
```

- **0.1 → 0.2 → 0.3** son secuenciales (el resumen depende de ambos servicios).
- **1.1 y 1.2** son paralelizables entre sí (archivos distintos), salvo el `group` que 1.1 añade al schema y 1.2 no toca.
- **2.1** necesita `kom`/`qom` de 0.2 y el perfil de 0.1.
- **4.1 y 4.2** tocan el mismo archivo (`RouteMapGpx.svelte`): secuenciales.
- **5.2** cierra y sincroniza la spec.

**Riesgo principal:** el cálculo de KOM/QOM depende de `average_grade` por segmento, que Strava reporta con signo y redondeo. Con la F1 actual hay un segmento de bajada (-1.6%) y uno de subida (+0.7%), sin ambigüedad; con un tercer segmento plano (+0.0%) la regla "pendiente > 0.5 = subida" lo deja fuera de ambos, que es lo correcto. La Task 0.2 fija esa regla con tests, de modo que un cambio de datos no rompe la página.
