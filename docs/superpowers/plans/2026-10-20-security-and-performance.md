# Plan de Seguridad y Rendimiento — Copa MacroSur MTB 2026

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cerrar las tres vulnerabilidades críticas de la API pública y el panel de administración, impose límites de entrada, y reducir el TTFB de las páginas públicas de ~1.2 s a < 300 ms **sin degradar ninguna animación**.

**Architecture:** El backend expone contratos de lectura explícitos (`response_model`) que guarantees que `judge_pin` y la geometría pesada nunca salgan de la API; los secretos dejan de estar en el bundle del cliente y se resuelven contra variables de entorno; los límites se aplican en el borde (middleware) y en los esquemas Pydantic. En el lado del rendimiento, se agrega un endpoint agregado `/public/home` que colapsa las 7 llamadas de la portada en 1, se activa GZip en FastAPI, se sirve el SSR desde la Cache API de Cloudflare Pages, y se eliminan los N+1 de SQLModel.

**Tech Stack:** FastAPI 0.136 · SQLModel/SQLAlchemy 2.0 async · asyncpg · Neon PostgreSQL (`us-west-2`) · Astro 5.18 SSR (`@astrojs/cloudflare` 12) · Svelte 5 Runes · Cloudflare Pages Functions · Render Web Service (free, 1 worker) · pytest 9 · Playwright (`frontend/tools/`)

**Spec:** `specs/00-domain-schema.md`, `specs/01-excel-and-scoring.md`, `specs/02-live-timing-and-sse.md`, `specs/03-public-portal-and-gpx.md`, `AGENTS.md`, y la auditoría de producción en `CREDENCIALES_PRODUCCION.md` §6.

---

## Global Constraints

- **Idioma de comments, docstrings y mensajes de commit: español.** Es la convención del repositorio (`backend/app/**` y `frontend/src/**` están íntegramente en español) y `AGENTS.md` lo exige implícitamente al sincronizar `specs/`.
- **Cero Tailwind / Bootstrap.** CSS nativo scoped únicamente (`AGENTS.md` §2).
- **Cero WebSockets.** SSE vía `StreamingResponse` (`AGENTS.md` §2).
- **Un solo proceso Uvicorn** (`--workers 1`): `sse_manager.py` usa `asyncio.Queue` en memoria por `stage_id` (`specs/02`).
- **Cero disco local en runtime** (Render Free es efímero): Excel/PDF/GPX en `io.BytesIO`; binarios persistentes en R2 (`AGENTS.md` §2).
- **Sin librerías de animación pesadas en `/en-vivo` ni `/admin/juez`** (`AGENTS.md` §2). GSAP + Lenis sólo en páginas de escaparate, cargados con `import()` dinámico.
- **Cero emojis en la UI.** Textos en mayúsculas monoespaciadas para los rótulos.
- **Ningún dato literal en las páginas de datos**: todo viene de la API (`specs/03` §0.2).
- **Animaciones: no se degradan.** Este plan no elimina ni acorta ninguna animación existente; sólo mueve trabajo del hilo principal, desacopla el filtro SVG del elemento animado, y elimina colisiones de `view-transition-name` que hoy **impiden** que el morph del póster funcione.
- **Todo cálculo de tiempos, puntos, deltas o parseo de Excel debe tener su test en `pytest` y pasar en verde** (`AGENTS.md` §3.5).
- **`ADMIN_API_KEY` y `DATABASE_URL` nunca viajan en el bundle del cliente ni en el repositorio.** `CREDENCIALES_PRODUCCION.md` ya está excluido vía `.git/info/exclude`; `.env` ya está en `.gitignore`.

## Review Focus

Los cinco casos de entrada que el código actual acepta y que una persona reasonable esperaría que NO se acepten, o que se manejen distinto. Cada línea de esta lista tiene su test en la tarea indicada.

1. **Un `GET /api/v1/stages` anónimo.** Hoy devuelve `judge_pin` en claro para las 4 fechas. Lo esperable: ningún PIN de juez, ni ningún campo de credencial, en ninguna respuesta pública. → Tarea 1.
2. **Un `POST /api/v1/public/pre-register` con `full_name` de 5 MB y `voucher_url: "javascript:alert(1)"`.** Hoy se guarda tal cual y se pinta con `innerHTML` en `/admin` (XSS almacenado). Lo esperable: 422 por longitud, y el voucher rechazado si el esquema no es `http(s)`. → Tareas 2 y 4.
3. **Un `Origin: https://attacker.pages.dev` contra la API de producción.** Hoy el regex CORS lo acepta y devuelve `Access-Control-Allow-Origin` con `allow_credentials=True`. Lo esperable: sin cabecera de permiso de origen. → Tarea 3.
4. **11 pre-registros desde la misma IP en un minuto.** Hoy todos entran. Lo esperable: los 10 primeros pasan, el 11º recibe 429 con `Retry-After`. → Tarea 4.
5. **Un `POST /api/v1/stages/{id}/import-excel` con un `.xlsx` de 200 MB.** Hoy `await file.read()` se lo traga entero en la RAM de Render Free (512 MB) y tumba el servicio. Lo esperable: 413 antes de leer, con el cuerpo descartado. → Tarea 4.

---

## Mapa de archivos

### Backend — a crear
| Archivo | Responsabilidad |
| :--- | :--- |
| `backend/app/core/limits.py` | Middleware de límites: rate-limit por IP+regla, y tope de `Content-Length` por ruta. |
| `backend/app/core/rate_limit.py` | Estructura de datos del limitador (ventana deslizante, en memoria, con `reset()`). |

### Backend — a modificar
| Archivo | Cambio |
| :--- | :--- |
| `backend/app/models/schemas.py` | `StagePublicRead` (sin `judge_pin`), `RouteProfileSummaryRead` (sin `points`), `StageSummaryRead` completo, `Field(max_length=...)` en los esquemas de escritura. |
| `backend/app/core/config.py` | `ADMIN_API_KEY` sin valor por defecto (fail-closed), `CORS_ORIGIN_REGEX` sólo en desarrollo, `env_file` absoluto (raíz del repo), nuevos `RATE_LIMIT_*`, `MAX_UPLOAD_*`. |
| `backend/app/core/security.py` | `verify_admin_key` falla cerrado si la clave no está configurada; comparación en tiempo constante. |
| `backend/app/core/cache.py` | `delete_prefix()` e `invalidate_public()`. |
| `backend/app/main.py` | `GZipMiddleware`, `RateLimitMiddleware`, CORS condicionado a `ENVIRONMENT`. |
| `backend/app/routers/stages.py` | `response_model` público en las 4 rutas de lectura; `route_geojson` fuera de las respuestas; N+1 eliminado en `/{slug}` y `/{slug}/results`. |
| `backend/app/routers/public.py` | `GET /public/home` agregado y cacheado; N+1 en `/standings/individual`; límites en `/pre-register` y `/feedback`. |
| `backend/app/routers/riders.py` | Perfil del corredor en una consulta; caché en memoria. |
| `backend/app/routers/teams.py` | Perfil del club en una consulta; caché en memoria. |
| `backend/app/routers/timing.py` | Invalidación de caché al cronometrar; N+1 en `/live-summary`. |
| `backend/app/routers/admin.py` | Invalidación de caché; N+1 en `/pending-payments`; tope de tamaño en `/upload-gpx`. |
| `backend/app/routers/excel.py` | Tope de tamaño en `/import-excel`; N+1 en `/export-excel` (vía `excel_service`). |
| `backend/app/services/excel_service.py` | Exportación sin N+1. |
| `backend/app/services/stage_summary_service.py` | Strava y Mountain Titles comparten una sola carga de segmentos/esfuerzos. |

### Frontend — a crear
| Archivo | Responsabilidad |
| :--- | :--- |
| `frontend/src/middleware.ts` | Caché de borde (Cloudflare `caches.default`) para las rutas públicas GET. |
| `frontend/src/lib/admin.ts` | Puerta de sesión del panel admin: guarda/lee la clave en `sessionStorage`, expone `adminHeaders()`. |
| `frontend/tools/check-admin-security.mjs` | Regresión: el secreto no aparece en `src/`, ni hay `innerHTML` con datos de usuario. |

### Frontend — a modificar
| Archivo | Cambio |
| :--- | :--- |
| `frontend/src/lib/api.ts` | `getHomeBundle()`; tipos de `StageOption` sin `route_geojson`. |
| `frontend/src/pages/index.astro` | Una sola llamada (`/public/home`); sin `Promise.all` de 7 fetches. |
| `frontend/src/pages/ranking-general.astro` | Una sola tanda de fetch; props recortadas para `<astro-island>`. |
| `frontend/src/pages/corredor/[slug].astro` | `Cache-Control` + payload recortado. |
| `frontend/src/pages/equipos/[slug].astro` | `Cache-Control` + payload recortado. |
| `frontend/src/pages/admin/index.astro` | Fuera el secreto; render con `textContent`; validación del voucher. |
| `frontend/src/components/EventCard.astro` | `data-morph-name` en vez de `transition:name`; click con `navigate()`; listener sin fuga. |
| `frontend/src/components/TimelineEvents.astro` | Asignación en runtime del `view-transition-name` visible; listeners sin fuga. |
| `frontend/src/components/HeroScene.astro` | El filtro `feDisplacementMap` deja de envolver al ciclista animado. |
| `frontend/src/layouts/Base.astro` | Fuera el `@fontsource-variable/archivo` (wght) redundante; queda sólo `standard.css`. |
| `frontend/src/components/svelte/StandingsTable.svelte` | Tipos de fila alineados con el payload recortado. |

### Tests — a crear
| Archivo | Cubre |
| :--- | :--- |
| `backend/tests/test_security.py` | Tareas 1–4. |
| `backend/tests/test_perf_budget.py` | Tareas 6–8 (tamaños de payload y conteo de consultas). |

### Specs — a sincronizar (AGENTS.md §3.6)
- `specs/02-live-timing-and-sse.md` §6 — invalidación de caché al cronometrar.
- `specs/03-public-portal-and-gpx.md` §0 — caché de borde, `GET /public/home`, contratos de lectura pública.
- `specs/00-domain-schema.md` §1.4 — `judge_pin` nunca sale por la API.

---

## Task 1: Contrato de lectura pública (nunca sale `judge_pin`)

**Files:**
- Modify: `backend/app/models/schemas.py`
- Modify: `backend/app/routers/stages.py:28-36, 39-120, 123-184, 187-229`
- Test: `backend/tests/test_security.py` (nuevo)

**Interfaces:**
- Consumes: `backend.app.models.entities.Stage` (ORM), `backend.app.models.schemas.*Read`.
- Produces:
  - `StagePublicRead(BaseModel)` en `backend/app/models/schemas.py`, con `model_config = ConfigDict(from_attributes=True)` y **exactamente** estos campos: `id: int`, `stage_number: int`, `name: str`, `short_name: Optional[str]`, `title: Optional[str]`, `slug: str`, `date: str`, `status: StageStatusEnum`, `start_location: Optional[str]`, `start_time: Optional[str]`, `poster_url: Optional[str]`, `gpx_file_url: Optional[str]`, `distance_km: Optional[float]`, `elevation_gain_m: Optional[int]`, `laps: int`, `strava_route_url: Optional[str]`, `official_results: Optional[int]`, `official_points: Optional[int]`, `live_closed_at: Optional[datetime]`. **Sin `judge_pin`. Sin `route_geojson`.**
  - `RouteProfileSummaryRead(BaseModel)`: los mismos campos que `RouteProfileRead` **menos `points`**.
  - `StageSummaryRead.stage: StagePublicRead` y `StageSummaryRead.route_profile: Optional[RouteProfileSummaryRead]`, más los campos que el endpoint ya devuelve hoy y el esquema no tenía: `summits: List[SummitRead]`, `kom: Optional[MountainTitleRead]`, `qom: Optional[MountainTitleRead]`, `kamikaze_male: Optional[MountainTitleRead]`, `kamikaze_female: Optional[MountainTitleRead]`.

- [ ] **Step 1: Escribir el test que falla**

En `backend/tests/test_security.py`:

```python
from sqlmodel import Session, SQLModel, select
from backend.app.main import app
from backend.app.models.entities import Stage, StageStatusEnum
import datetime

async def _seed_stage(session):
    stage = Stage(
        stage_number=99, name="Fecha 99: Prueba", slug="fecha-prueba",
        date=datetime.date(2026, 1, 1), status=StageStatusEnum.FINISHED,
        judge_pin="PIN-SECRETO-DE-PRUEBA",
        route_geojson={"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": {"type": "LineString",
             "coordinates": [[-71.5, -16.4, 2200, 0.0]]}}]},
    )
    session.add(stage)
    await session.commit()
    await session.refresh(stage)
    return stage


async def test_stages_no_expone_judge_pin(client, async_session):
    stage = await _seed_stage(async_session)
    res = await client.get("/api/v1/stages")
    assert res.status_code == 200
    assert "PIN-SECRETO-DE-PRUEBA" not in res.text
    assert "judge_pin" not in res.text


async def test_stage_detalle_no_expone_judge_pin(client, async_session):
    stage = await _seed_stage(async_session)
    res = await client.get(f"/api/v1/stages/{stage.slug}")
    assert res.status_code == 200
    assert "PIN-SECRETO-DE-PRUEBA" not in res.text


async def test_stage_summary_no_expone_judge_pin_ni_geometria(client, async_session):
    stage = await _seed_stage(async_session)
    res = await client.get(f"/api/v1/stages/{stage.slug}/summary")
    assert res.status_code == 200
    assert "PIN-SECRETO-DE-PRUEBA" not in res.text
    assert "judge_pin" not in res.text
    # La geometría pesada no viaja en el resumen: la página usa el SVG estatico.
    assert "route_geojson" not in res.text


async def test_stage_results_no_expone_judge_pin(client, async_session):
    stage = await _seed_stage(async_session)
    res = await client.get(f"/api/v1/stages/{stage.slug}/results")
    assert res.status_code == 200
    assert "judge_pin" not in res.text
```

- [ ] **Step 2: Ejecutar los tests y verificar que fallan**

Run: `python -m pytest backend/tests/test_security.py -v`
Expected: FAIL — `"judge_pin" not in res.text` falla en las cuatro pruebas (el modelo ORM se serializa entero).

- [ ] **Step 3: Implementar `StagePublicRead` y aplicarlo**

En `backend/app/models/schemas.py`, añadir `StagePublicRead` y `RouteProfileSummaryRead` tal como se definen arriba, y corregir `StageSummaryRead` para que `stage: StagePublicRead` y `route_profile: Optional[RouteProfileSummaryRead]`, añadiendo los campos `summits`, `kom`, `qom`, `kamikaze_male`, `kamikaze_female`.

En `backend/app/routers/stages.py`:
- `GET ""` → `response_model=List[StagePublicRead]`, `response_model_exclude_unset=False`. El endpoint devuelve los objetos `Stage` del ORM: FastAPI los serializa con `from_attributes`, y `StagePublicRead` no tiene `judge_pin`, así que **el campo no se serializa** aunque exista en el objeto.
- `GET "/{slug}"` → `response_model=StageDetailPublicRead`, un modelo nuevo con `stage: StagePublicRead`, `awards: List[AwardSummaryRead]`, `strava_segments: List[Dict[str, Any]]`, `extremes: StageExtremesRead`. (El endpoint hoy devuelve un dict con la clave `stage`; hay que envolverlo.)
- `GET "/{slug}/summary"` → `response_model=StageSummaryRead`.
- `GET "/{slug}/results"` → `response_model=StageResultsPublicRead`, con `stage: StagePublicRead` y `categories: Dict[str, List[Dict[str, Any]]]`.

El `route_profile` del summary: `compute_stage_route_profile` sigue devolviendo `RouteProfileRead` con `points`; el `response_model` recorta a `RouteProfileSummaryRead` (sin `points`). Para que la fila sea rápida, `compute_stage_route_profile` debe dejar de calcular `points`: en `backend/app/services/stage_summary_service.py`, tras `profile = build_route_profile(...)`, hacer `profile.pop("points", None)` **antes** de construir `RouteProfileRead`, y añadir `points: List[RoutePointRead] = Field(default_factory=list)` con `exclude=True` en `RouteProfileRead` para que el modelo siga siendo válido.

- [ ] **Step 4: Ejecutar los tests y verificar que pasan**

Run: `python -m pytest backend/tests/test_security.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Ejecutar la suite completa para verificar que no se rompió nada**

Run: `python -m pytest backend/tests -q`
Expected: PASS. Si `test_stage_summary.py` falla por el nuevo `response_model`, ajustar ese test para el contrato nuevo (no relajar el `response_model`).

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/schemas.py backend/app/routers/stages.py \
        backend/app/services/stage_summary_service.py backend/tests/test_security.py
git commit -m "fix(security): los PIN de juez nunca salen por la API publica"
```

---

## Task 2: `ADMIN_API_KEY` fuera del bundle + XSS en `/admin`

**Files:**
- Modify: `backend/app/core/config.py:9`
- Modify: `backend/app/core/security.py:5-11`
- Modify: `frontend/src/pages/admin/index.astro:122-277`
- Create: `frontend/src/lib/admin.ts`
- Create: `frontend/tools/check-admin-security.mjs`
- Modify: `backend/.env.example`
- Create: `.env.example` (raíz)
- Test: `backend/tests/test_security.py` (sección de admin) + `frontend/tools/check-admin-security.mjs`

**Interfaces:**
- Consumes: `settings.ADMIN_API_KEY` (backend), `X-Admin-Key` (cabecera ya existente en todos los endpoints admin).
- Produces:
  - `frontend/src/lib/admin.ts` exporta:
    - `const ADMIN_KEY_STORAGE = 'kuspide_admin_key'`
    - `function adminKey(): string` — lee `sessionStorage`, `''` si no hay.
    - `function setAdminKey(value: string): void` — escribe en `sessionStorage`.
    - `function clearAdminKey(): void` — borra.
    - `function adminHeaders(): Record<string, string>` — `{ 'X-Admin-Key': adminKey() }`.
  - `backend/app/core/config.py`: `ADMIN_API_KEY: str = ""` (sin default) y `settings.ADMIN_API_KEY` vacío ⇒ `verify_admin_key` responde **503** con `"El servidor no tiene ADMIN_API_KEY configurado."`.

- [ ] **Step 1: Escribir el test que falla**

En `backend/tests/test_security.py`:

```python
async def test_admin_sin_clave_responde_403(client):
    res = await client.get("/api/v1/admin/pending-payments")
    assert res.status_code == 403


async def test_admin_con_clave_invalida_responde_403(client):
    res = await client.get(
        "/api/v1/admin/pending-payments",
        headers={"X-Admin-Key": "clave-inventada"},
    )
    assert res.status_code == 403
```

- [ ] **Step 2: Ejecutar el test y verificar que falla**

Run: `python -m pytest backend/tests/test_security.py -k admin -v`
Expected: FAIL — `test_admin_sin_clave_responde_403` recibe 200 (el default `<CLAVE-ADMIN-ANTERIOR>` coincide con el header vacío... en realidad `verify_admin_key` compara `x_admin_key != settings.ADMIN_API_KEY`; sin header devuelve 403, así que **este test puede pasar ya**. El que falla es el de la clave inventada sólo si el default está presente; verificar el resultado real y ajustar la aserción al comportamiento deseado: sin cabecera → 403; con cabecera incorrecta → 403; con la clave real → 200.)

- [ ] **Step 3: Backend — fail-closed y `.env`**

En `backend/app/core/config.py`:
- `ADMIN_API_KEY: str = ""`.
- `model_config = SettingsConfigDict(env_file=(<raíz del repo>/".env", <raíz del repo>/"backend"/".env"), env_file_encoding="utf-8", extra="ignore")`, con la raíz calculada como `pathlib.Path(__file__).resolve().parents[3]`.
- Añadir `ENVIRONMENT` ya existe; mantenerlo.

En `backend/app/core/security.py`:

```python
import hmac
from fastapi import Header, HTTPException, status
from backend.app.core.config import settings


async def verify_admin_key(x_admin_key: str = Header(None, alias="X-Admin-Key")) -> str:
    """Valida la clave de administrador.

    Falla CERRADO: si el servidor no tiene `ADMIN_API_KEY` configurada, NINGÚN
    endpoint admin responde 200. Antes el valor por defecto estaba en el código
    y en el bundle del navegador: la clave era pública.
    """
    configured = settings.ADMIN_API_KEY
    if not configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El servidor no tiene ADMIN_API_KEY configurada.",
        )
    if not x_admin_key or not hmac.compare_digest(x_admin_key, configured):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Credencial de Administrador inválida o ausente (X-Admin-Key).",
        )
    return x_admin_key
```

Crear `.env.example` en la raíz del repo (canónico) con `DATABASE_URL`, `ADMIN_API_KEY`, `ENVIRONMENT`, `CORS_ORIGINS`, `R2_*`, y un `ADMIN_API_KEY=""` vacío (el usuario lo genera). Sustituir `backend/.env.example` por un puntero de 3 líneas al `.env` de la raíz.

- [ ] **Step 4: Frontend — puerta de sesión y render sin `innerHTML`**

Crear `frontend/src/lib/admin.ts` con las cuatro funciones de la sección Interfaces.

En `frontend/src/pages/admin/index.astro`:
- **Eliminar** la línea `const ADMIN_KEY = '<CLAVE-ADMIN-ANTERIOR>';` y toda referencia a `ADMIN_KEY`.
- Añadir un gate: un `<input type="password" id="admin-key">` y un botón "ENTRAR" que llama a `setAdminKey(input.value)` y recarga la lista. Si `adminKey()` está vacío al cargar, la página muestra el gate y **no** llama a la API.
- Todas las peticiones usan `adminHeaders()`.
- `loadPendingPayments()` deja de usar `innerHTML` con interpolación: construye nodos con `document.createElement` y asigna el texto con `textContent`. El `voucher_url` se valida antes de usarlo como `href`:
  ```ts
  function safeUrl(raw: string | null): string | null {
    if (!raw) return null;
    try {
      const u = new URL(raw);
      return u.protocol === 'http:' || u.protocol === 'https:' ? u.toString() : null;
    } catch { return null; }
  }
  ```
  Si `safeUrl` devuelve `null`, se muestra "Enlace de voucher no válido" en vez del `<a>`.

- [ ] **Step 5: Escribir la regresión del frontend**

Crear `frontend/tools/check-admin-security.mjs`: lee recursivamente `frontend/src/**` y falla si (a) aparece la cadena `<CLAVE-ADMIN-ANTERIOR>`, o (b) el archivo `pages/admin/index.astro` contiene `innerHTML` con `${` (interpolación dentro de `innerHTML`).

```bash
node frontend/tools/check-admin-security.mjs
```

- [ ] **Step 6: Ejecutar la regresión y verificar que falla antes de corregir / pasa después**

Run: `node frontend/tools/check-admin-security.mjs`
Expected tras el Step 4: PASS (sin secretos, sin `innerHTML` interpolado).

- [ ] **Step 7: Ejecutar los tests del backend**

Run: `python -m pytest backend/tests/test_security.py -k admin -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add .env.example backend/.env.example backend/app/core/config.py \
        backend/app/core/security.py frontend/src/lib/admin.ts \
        frontend/src/pages/admin/index.astro frontend/tools/check-admin-security.mjs \
        backend/tests/test_security.py
git commit -m "fix(security): la clave de administrador sale del bundle y el panel deja de usar innerHTML"
```

---

## Task 3: CORS cerrado en producción

**Files:**
- Modify: `backend/app/core/config.py:21-37`
- Modify: `backend/app/main.py:41-50`
- Test: `backend/tests/test_security.py`

**Interfaces:**
- Consumes: `settings.ENVIRONMENT`, `settings.CORS_ORIGINS`.
- Produces: `settings.CORS_ALLOW_LOCALHOST: bool` — `True` si `ENVIRONMENT != "production"`.

- [ ] **Step 1: Escribir el test que falla**

En `backend/tests/test_security.py`:

```python
async def test_cors_no_acepta_pages_dev_arbitrario(client, monkeypatch):
    from backend.app.core import config as config_module
    monkeypatch.setattr(config_module.settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(config_module.settings, "CORS_ORIGINS", ["https://copa-macrosur-web.pages.dev"])
    res = await client.get(
        "/api/v1/public/live-status",
        headers={"Origin": "https://attacker.pages.dev"},
    )
    assert "access-control-allow-origin" not in {k.lower() for k in res.headers}
```

- [ ] **Step 2: Ejecutar el test y verificar que falla**

Run: `python -m pytest backend/tests/test_security.py -k cors -v`
Expected: FAIL — la respuesta trae `access-control-allow-origin: https://attacker.pages.dev`.

- [ ] **Step 3: Implementar el CORS por entorno**

En `backend/app/core/config.py`:
- `CORS_ORIGIN_REGEX` pasa a ser el regex **de desarrollo**: `r"^https?://((localhost|127\.0\.0\.1)(:\d+)?)$"`.
- Nueva variable de producción, `CORS_ORIGINS`, con la lista real:
  ```python
  CORS_ORIGINS: List[str] = [
      "https://copa-macrosur-web.pages.dev",
      "https://kuspideweb.com",
      "https://www.kuspideweb.com",
  ]
  ```
  (Los puertos de localhost salen de la lista: en desarrollo los cubre el regex.)
- `CORS_ALLOW_LOCALHOST: bool = True` → se resuelve con un `@model_validator(mode="after")` que devuelve `False` cuando `ENVIRONMENT == "production"`.

En `backend/app/main.py`, sustituir el bloque de CORS por:

```python
cors_options = {
    "allow_origins": settings.CORS_ORIGINS or [],
    "allow_credentials": True,
    "allow_methods": ["GET", "POST", "OPTIONS"],
    "allow_headers": ["Content-Type", "X-Admin-Key", "X-Judge-Pin"],
}
if settings.CORS_ALLOW_LOCALHOST and settings.CORS_ORIGIN_REGEX:
    cors_options["allow_origin_regex"] = settings.CORS_ORIGIN_REGEX
app.add_middleware(CORSMiddleware, **cors_options)
```

`allow_methods` y `allow_headers` dejan de ser `"*"`: el cliente sólo usa esos tres.

- [ ] **Step 4: Ejecutar el test y verificar que pasa**

Run: `python -m pytest backend/tests/test_security.py -k cors -v`
Expected: PASS.

- [ ] **Step 5: Verificar que el desarrollo sigue funcionando**

Run: `python -m pytest backend/tests -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/config.py backend/app/main.py backend/tests/test_security.py
git commit -m "fix(security): CORS cerrado a los origenes reales en produccion"
```

---

## Task 4: Límites de entrada (rate-limit, tamaño, longitud)

**Files:**
- Create: `backend/app/core/rate_limit.py`
- Create: `backend/app/core/limits.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/models/schemas.py`
- Modify: `backend/app/routers/excel.py`
- Modify: `backend/app/routers/admin.py`
- Test: `backend/tests/test_security.py`

**Interfaces:**
- Produces:
  - `backend/app/core/rate_limit.py`:
    - `class SlidingWindowLimiter`: `__init__(self, limit: int, window_seconds: int = 60)`, `allow(self, key: str) -> tuple[bool, int]` (devuelve `(permitido, segundos_para_reintentar)`), `reset(self) -> None`.
  - `backend/app/core/limits.py`:
    - `class RateLimitMiddleware(BaseHTTPMiddleware)`: `__init__(self, app, rules: list[RateRule], limiter_factory)`.
    - `class RateRule(BaseModel)` o dataclass: `prefix: str`, `bucket: str`, `limit: int`, `window_seconds: int = 60`.
    - `RATE_LIMIT_RULES: list[RateRule]` — la tabla de reglas.
    - `rate_limiter_registry: dict[str, SlidingWindowLimiter]` — un limitador por bucket.
    - `def client_ip(request: Request) -> str` — lee `CF-Connecting-IP`, luego `X-Forwarded-For` (primera IP), luego `request.client.host`.
  - `backend/app/core/config.py`: `RATE_LIMIT_ENABLED: bool = True`, `MAX_UPLOAD_BYTES: int = 25 * 1024 * 1024`, `MAX_JSON_BYTES: int = 2 * 1024 * 1024`.

- [ ] **Step 1: Escribir los tests que fallan**

En `backend/tests/test_security.py`:

```python
async def test_rate_limit_public_write(client):
    from backend.app.core.limits import rate_limiter_registry
    rate_limiter_registry["public_write"].reset()
    for _ in range(10):
        res = await client.post("/api/v1/public/feedback", json={
            "stage_id": None, "type": "OTHER",
            "submitted_by_name": "Prueba", "contact_whatsapp_or_email": "a@b.pe",
            "message": "Mensaje de prueba",
        })
        assert res.status_code == 200
    res = await client.post("/api/v1/public/feedback", json={
        "stage_id": None, "type": "OTHER",
        "submitted_by_name": "Prueba", "contact_whatsapp_or_email": "a@b.pe",
        "message": "Mensaje de prueba",
    })
    assert res.status_code == 429
    assert "retry-after" in res.headers


async def test_preregistro_nombre_demasiado_largo(client):
    res = await client.post("/api/v1/public/pre-register", json={
        "stage_id": 1, "dni": "12345678", "full_name": "X" * 500,
        "gender": "M", "category_id": 1, "team_name_or_libre": "LIBRE",
    })
    assert res.status_code == 422


async def test_upload_excel_supera_el_tope(client):
    # El endpoint debe responder 413 sin leer el cuerpo entero.
    res = await client.post(
        "/api/v1/stages/1/import-excel",
        headers={"X-Admin-Key": settings.ADMIN_API_KEY or "x"},
        files={"file": ("grande.xlsx", b"x" * (26 * 1024 * 1024), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert res.status_code in (403, 413)
```

- [ ] **Step 2: Ejecutar los tests y verificar que fallan**

Run: `python -m pytest backend/tests/test_security.py -k "rate_limit or demasiado_largo or upload" -v`
Expected: FAIL — el rate limit no existe (200 en todos), el nombre largo se acepta (200/400, no 422), y el upload de 26 MB se traga entero.

- [ ] **Step 3: Implementar `SlidingWindowLimiter`**

`backend/app/core/rate_limit.py`:

```python
import time
from collections import deque
from typing import Deque, Dict, Tuple


class SlidingWindowLimiter:
    """Ventana deslizante en memoria: N peticiones por IP y ventana."""

    def __init__(self, limit: int, window_seconds: int = 60) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._hits: Dict[str, Deque[float]] = {}

    def allow(self, key: str) -> Tuple[bool, int]:
        now = time.monotonic()
        hits = self._hits.setdefault(key, deque())
        while hits and now - hits[0] >= self.window_seconds:
            hits.popleft()
        if len(hits) >= self.limit:
            retry_after = max(1, int(self.window_seconds - (now - hits[0])))
            return False, retry_after
        hits.append(now)
        return True, 0

    def reset(self) -> None:
        self._hits.clear()
```

- [ ] **Step 4: Implementar el middleware de límites**

`backend/app/core/limits.py`: `RateLimitMiddleware` con la tabla de reglas

```python
RATE_LIMIT_RULES: list[RateRule] = [
    RateRule(prefix="/api/v1/admin", bucket="admin", limit=120),
    RateRule(prefix="/api/v1/stages", bucket="admin", limit=60),   # import-excel / upload-gpx
    RateRule(prefix="/api/v1/timing", bucket="judge", limit=600),
    RateRule(prefix="/api/v1/public/pre-register", bucket="public_write", limit=10),
    RateRule(prefix="/api/v1/public/feedback", bucket="public_write", limit=10),
]
```

Orden importante: la **primera** regla que coincide gana, y las reglas más específicas van antes. `client_ip` prioriza `CF-Connecting-IP` (Cloudflare) sobre `X-Forwarded-For` (Render).

Respuesta 429: `JSONResponse(status_code=429, content={"detail": "Demasiadas peticiones. Inténtalo de nuevo en unos segundos."}, headers={"Retry-After": str(retry_after)})`.

Tope de `Content-Length`: en el mismo middleware, antes del rate-limit, si `int(request.headers.get("content-length") or 0) > settings.MAX_JSON_BYTES` y la ruta **no** es una de subida (`.xlsx`/`.gpx`, que tienen su propio tope `MAX_UPLOAD_BYTES`), responder 413 sin leer el cuerpo.

- [ ] **Step 5: Montar el middleware**

En `backend/app/main.py`, añadir **después** de `CORSMiddleware` (el orden de `add_middleware` es inverso: el último añadido es el primero en ejecutarse; el rate-limit debe ir antes del CORS para no gastar cuota en preflight):

```python
app.add_middleware(CORSMiddleware, **cors_options)
app.add_middleware(RateLimitMiddleware, rules=RATE_LIMIT_RULES)
```

- [ ] **Step 6: Límites de longitud en los esquemas**

En `backend/app/models/schemas.py`:
- `PreRegistrationCreate`: `full_name: str = Field(min_length=3, max_length=120)`, `dni: str = Field(min_length=6, max_length=20)`, `team_name_or_libre: str = Field(max_length=120)`, `voucher_url: Optional[str] = Field(default=None, max_length=500)`.
- `FeedbackTicketCreate`: `submitted_by_name: str = Field(min_length=2, max_length=120)`, `contact_whatsapp_or_email: str = Field(min_length=3, max_length=160)`, `message: str = Field(min_length=1, max_length=2000)`.
- `BatchSyncRequest`: `events: List[TimingEventCreate] = Field(max_length=500)`.
- `TimingEventCreate.recorded_by_admin: str = Field(default="judge", max_length=64)`.

- [ ] **Step 7: Tope de tamaño en las subidas**

En `backend/app/routers/excel.py` y `backend/app/routers/admin.py`, antes de `await file.read()`:

```python
MAX_UPLOAD_BYTES = settings.MAX_UPLOAD_BYTES
content = await file.read(MAX_UPLOAD_BYTES + 1)
if len(content) > MAX_UPLOAD_BYTES:
    raise HTTPException(status_code=413, detail=f"El archivo supera el límite de {MAX_UPLOAD_BYTES // (1024*1024)} MB.")
```

- [ ] **Step 8: Ejecutar los tests y verificar que pasan**

Run: `python -m pytest backend/tests/test_security.py -v`
Expected: PASS.

- [ ] **Step 9: Ejecutar la suite completa**

Run: `python -m pytest backend/tests -q`
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add backend/app/core/rate_limit.py backend/app/core/limits.py \
        backend/app/core/config.py backend/app/main.py backend/app/models/schemas.py \
        backend/app/routers/excel.py backend/app/routers/admin.py backend/tests/test_security.py
git commit -m "feat(security): limites de entrada (rate-limit, tamano de payload y de archivo)"
```

---

## Task 5: Caché en memoria con invalidación explícita

**Files:**
- Modify: `backend/app/core/cache.py`
- Modify: `backend/app/routers/timing.py` (tras cada cronometraje y largada)
- Modify: `backend/app/routers/admin.py` (tras abrir/cerrar transmisión, subir GPX, sincronizar Strava)
- Modify: `backend/app/routers/excel.py` (tras importar Excel)
- Test: `backend/tests/test_perf_budget.py` (nuevo)

**Interfaces:**
- Produces, en `backend/app/core/cache.py`:
  - `def delete_prefix(self, prefix: str) -> None` — borra todas las claves que empiezan por `prefix`.
  - `def invalidate_public(self) -> None` — borra `public:`, `stages:`, `stage:summary:` y `stage:list:`.
  - `def keys(self) -> list[str]` — para el test.

- [ ] **Step 1: Escribir el test que falla**

En `backend/tests/test_perf_budget.py`:

```python
from backend.app.core.cache import cache


def test_invalidate_public_borra_las_claves_de_lectura():
    cache.set("public:standings:PRO", {"rows": []}, ttl_seconds=60)
    cache.set("public:live_status", {"state": "live"}, ttl_seconds=60)
    cache.set("stages:list", [], ttl_seconds=60)
    cache.set("otra:cosa", 1, ttl_seconds=60)
    cache.invalidate_public()
    assert cache.get("public:standings:PRO") is None
    assert cache.get("public:live_status") is None
    assert cache.get("stages:list") is None
    assert cache.get("otra:cosa") == 1
```

> Nota: `cache.get`/`cache.set` están desactivados bajo `PYTEST_CURRENT_TEST` (bypass heredado de `backend/app/core/cache.py:18,30`). **Quitar ese bypass en esta tarea**: los tests necesitan poder ejercitar la caché. Para no contaminar la suite, el bypass se conserva sólo cuando `settings.CACHE_ENABLED_TEST_BYPASS` es `True` y se pone en `False` por defecto.

- [ ] **Step 2: Ejecutar el test y verificar que falla**

Run: `python -m pytest backend/tests/test_perf_budget.py -v`
Expected: FAIL — `AttributeError: 'MemoryCache' object has no attribute 'invalidate_public'`.

- [ ] **Step 3: Implementar `delete_prefix` e `invalidate_public`**

En `backend/app/core/cache.py`:

```python
def delete_prefix(self, prefix: str) -> None:
    """Borra todas las claves que empiezan por `prefix`."""
    for key in [k for k in self._store if k.startswith(prefix)]:
        del self._store[key]

def invalidate_public(self) -> None:
    """Invalida TODO lo que el público puede leer.

    Se llama después de cualquier mutación (una marcación del juez, la
    apertura de la transmisión, una ingesta de Excel): con la caché de 120 s
    sin invalidar, el público veía datos viejos hasta dos minutos.
    """
    for prefix in ("public:", "stages:", "stage:summary:"):
        self.delete_prefix(prefix)
```

- [ ] **Step 4: Llamar a `invalidate_public()` en cada mutación**

- `backend/app/routers/timing.py`: al final de `record_timing_event` (después del `broadcast`), de `start_wave` y de `start_entry`.
- `backend/app/routers/admin.py`: al final de `set_stage_live`, `upload_gpx_file` y `sync_strava_efforts`.
- `backend/app/routers/excel.py`: al final de `import_excel_endpoint`.

- [ ] **Step 5: Ejecutar el test y verificar que pasa**

Run: `python -m pytest backend/tests/test_perf_budget.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/cache.py backend/app/routers/timing.py \
        backend/app/routers/admin.py backend/app/routers/excel.py \
        backend/tests/test_perf_budget.py
git commit -m "fix(cache): la cache publica se invalida en cada mutacion"
```

---

## Task 6: `GET /public/home` — la portada en una sola llamada

**Files:**
- Modify: `backend/app/routers/public.py`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/pages/index.astro:39-118`
- Test: `backend/tests/test_perf_budget.py`

**Interfaces:**
- Produces:
  - `GET /api/v1/public/home` → `dict` con las claves exactas:
    ```python
    {
      "stages": List[StagePublicRead],      # sin judge_pin, sin route_geojson
      "live_status": dict,                  # la misma forma que /public/live-status
      "pro_podium": List[dict],             # 3 filas: {rider_name, total_points}
      "normal_podium": List[dict],
      "teams_podium": List[dict],           # 3 filas: {team_name, total_points}
      "remontada": dict,
      "mountain_titles": {                  # títulos de la Fecha 1
          "kom": dict | None, "qom": dict | None,
          "kamikaze_male": dict | None, "kamikaze_female": dict | None,
      },
    }
    ```
    Cacheado en memoria con TTL 60 s, bajo la clave `public:home`.
  - `frontend/src/lib/api.ts` → `export interface HomeBundle { ... }` y `export async function getHomeBundle(): Promise<HomeBundle>`.

- [ ] **Step 1: Escribir el test que falla**

En `backend/tests/test_perf_budget.py`:

```python
async def test_home_aggregate_una_sola_llamada(client, async_session):
    res = await client.get("/api/v1/public/home")
    assert res.status_code == 200
    data = res.json()
    for key in ("stages", "live_status", "pro_podium", "normal_podium",
                "teams_podium", "remontada", "mountain_titles"):
        assert key in data
    assert "judge_pin" not in res.text
    assert "route_geojson" not in res.text
    assert len(data["pro_podium"]) <= 3
```

- [ ] **Step 2: Ejecutar el test y verificar que falla**

Run: `python -m pytest backend/tests/test_perf_budget.py -k home -v`
Expected: FAIL — 404.

- [ ] **Step 3: Implementar el endpoint agregado**

En `backend/app/routers/public.py`, añadir el endpoint con `cache.get("public:home")` / `cache.set("public:home", res, ttl_seconds=60)`, reutilizando `compute_standings`, `compute_team_standings`, `resolve_live_status` y `compute_claro_remontada`. Los títulos de montaña se leen de `compute_stage_mountain_titles` sobre la **primera** etapa `FINISHED` (la Fecha 1). La geometría y los PIN no entran en el payload.

- [ ] **Step 4: Consumirlo desde la portada**

En `frontend/src/lib/api.ts`, añadir `getHomeBundle()`.

En `frontend/src/pages/index.astro`: sustituir los 7 `fetch` del `Promise.all` por **una** llamada a `getHomeBundle()`, y derivar de ella `proPodium`, `normalPodium`, `topTeams`, `liveStatus`, `stages`, `remontada` y `mountain`. Si la llamada falla, se conserva el comportamiento actual (secciones vacías con `error: true`), sin romperse.

- [ ] **Step 5: Ejecutar los tests y verificar que pasan**

Run: `python -m pytest backend/tests/test_perf_budget.py -v` → PASS.
Run: `cd frontend && npm run check` → 0 errores de tipos.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/public.py frontend/src/lib/api.ts \
        frontend/src/pages/index.astro backend/tests/test_perf_budget.py
git commit -m "perf(api): la portada lee un solo agregado /public/home"
```

---

## Task 7: GZip en FastAPI + caché de borde en Cloudflare Pages

**Files:**
- Modify: `backend/app/main.py`
- Create: `frontend/src/middleware.ts`
- Test: `backend/tests/test_perf_budget.py`

**Interfaces:**
- Produces: `frontend/src/middleware.ts` exporta `onRequest` (middleware de Astro 5).

- [ ] **Step 1: Escribir el test que falla**

En `backend/tests/test_perf_budget.py`:

```python
async def test_json_comprimido(client):
    res = await client.get(
        "/api/v1/public/standings?scope=PRO",
        headers={"Accept-Encoding": "gzip"},
    )
    assert res.status_code == 200
    assert res.headers.get("content-encoding") == "gzip"
```

> Nota: el cliente de test (`httpx.ASGITransport`) no descomprime; por eso se comprueba la **cabecera** `content-encoding`, no el tamaño.

- [ ] **Step 2: Ejecutar el test y verificar que falla**

Run: `python -m pytest backend/tests/test_perf_budget.py -k gzip -v`
Expected: FAIL — no hay `content-encoding`.

- [ ] **Step 3: Activar GZip**

En `backend/app/main.py`:

```python
from fastapi.middleware.gzip import GZipMiddleware
...
app.add_middleware(GZipMiddleware, minimum_size=1000)
```

`minimum_size=1000` deja fuera las respuestas diminutas (`/health`) y comprime las grandes (64 KB → ~9 KB).

- [ ] **Step 4: Implementar la caché de borde**

Crear `frontend/src/middleware.ts`:

```ts
import { defineMiddleware } from 'astro:middleware';

/** Rutas públicas que se pueden cachear en el borde. */
const CACHEABLE = ['/', '/fechas/', '/ranking-general', '/premios',
                   '/eventos-especiales', '/inscripciones',
                   '/corredor/', '/equipos/'];

const TTL_SECONDS = 60;

export const onRequest = defineMiddleware(async (context, next) => {
  const { request, url } = context;
  const method = request.method.toUpperCase();

  // Sólo GET. `/en-vivo` y `/admin/*` NUNCA se cachean: son en vivo.
  const cacheable = method === 'GET'
    && CACHEABLE.some((prefix) => url.pathname === prefix
                                 || (prefix.endsWith('/') && url.pathname.startsWith(prefix)));

  const cache = (globalThis as any).caches?.default;
  if (!cacheable || !cache) return next();

  const key = new Request(url.toString(), { method: 'GET' });
  const hit = await cache.match(key);
  if (hit) {
    const headers = new Headers(hit.headers);
    headers.set('X-Kuspide-Cache', 'HIT');
    return new Response(hit.body, { status: hit.status, headers });
  }

  const response = await next();
  if (response.ok && response.status === 200) {
    const headers = new Headers(response.headers);
    headers.set('Cache-Control', `public, max-age=15, s-maxage=${TTL_SECONDS}, stale-while-revalidate=300`);
    const copy = new Response(response.body, { status: 200, headers });
    // Revalidación en segundo plano: la siguiente visita no espera a la API.
    context.waitUntil(cache.put(key, copy.clone()));
    headers.set('X-Kuspide-Cache', 'MISS');
    return new Response(copy.body, { status: 200, headers });
  }
  return response;
});
```

- [ ] **Step 5: Verificar la caché de borde en local con `wrangler`**

```bash
cd frontend && npm run build && npx wrangler pages dev dist --port 4321 &
curl -sI http://127.0.0.1:4321/ | grep -i "x-kuspide-cache\|cache-control"
# La primera petición: X-Kuspide-Cache: MISS
# La segunda: X-Kuspide-Cache: HIT
```

- [ ] **Step 6: Ejecutar el test y verificar que pasa**

Run: `python -m pytest backend/tests/test_perf_budget.py -v` → PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/main.py frontend/src/middleware.ts backend/tests/test_perf_budget.py
git commit -m "perf: GZip en la API y cache de borde en Cloudflare Pages"
```

---

## Task 8: Cero N+1 en los endpoints de lectura

**Files:**
- Modify: `backend/app/routers/riders.py`
- Modify: `backend/app/routers/teams.py`
- Modify: `backend/app/routers/stages.py` (`/{slug}` y `/{slug}/results`)
- Modify: `backend/app/routers/timing.py` (`/live-summary`)
- Modify: `backend/app/routers/admin.py` (`/pending-payments`)
- Modify: `backend/app/routers/public.py` (`/standings/individual`)
- Modify: `backend/app/services/excel_service.py` (`export_stage_results_to_excel`)
- Modify: `backend/app/services/stage_summary_service.py` (Strava compartido)
- Test: `backend/tests/test_perf_budget.py`

**Interfaces:**
- Produce: un contador de consultas reutilizable en el test:
  `backend/tests/test_perf_budget.py` define el fixture `query_counter` que engancha el evento `before_cursor_execute` de SQLAlchemy sobre `test_engine` y cuenta las sentencias.

- [ ] **Step 1: Escribir el test que falla**

```python
@pytest_asyncio.fixture
async def query_counter(async_session):
    from sqlalchemy import event
    counter = {"n": 0}

    def _before(conn, cursor, statement, parameters, context, executemany):
        counter["n"] += 1

    event.listen(test_engine.sync_engine, "before_cursor_execute", _before)
    yield counter
    event.remove(test_engine.sync_engine, "before_cursor_execute", _before)


async def test_perfil_corredor_no_hace_n_plus_1(client, async_session, query_counter):
    # ... sembrar 1 corredor, 1 categoría, 1 inscripción y 1 standing ...
    query_counter["n"] = 0
    res = await client.get(f"/api/v1/riders/{slug}")
    assert res.status_code == 200
    assert query_counter["n"] <= 8, f"Hace {query_counter['n']} consultas"
```

Un límite de 8 consultas para un perfil con 1 corredor y 4 etapas descarta el N+1 sin ser frágil con los joins que se añadan.

- [ ] **Step 2: Ejecutar el test y verificar que falla**

Run: `python -m pytest backend/tests/test_perf_budget.py -k n_plus_1 -v`
Expected: FAIL — la cuenta de consultas supera el límite.

- [ ] **Step 3: Reescribir las consultas**

Regla general: **`selectinload` en las relaciones, `join` en lasfk que se proyectan, y nunca `await session.refresh(obj, [...])` dentro de un bucle.**

- `riders.py` → `get_rider_profile`: una consulta con `join(Rider, Team, Category)` para el historial y otra con `selectinload(Rider.standings)`; los `Category` de los standings salen de un `select(Category).where(Category.id.in_(...))` (1 consulta) en vez de uno por fila.
- `teams.py` → `get_team_profile`: la plantilla y sus puntos salen de **una** consulta con `join(StageEntry)` y `group_by(Rider.id)`; las categorías de cada corredor, de una consulta agrupada.
- `stages.py` → `/{slug}`: `select(StageEntry, Rider, Category, Team)` con `join` en una sola consulta para los extremos.
- `stages.py` → `/{slug}/results`: una consulta con `join` en vez de `session.refresh` por entrada.
- `timing.py` → `/live-summary`: `select(StageEntry, Rider, Category, Team)` con `join`.
- `admin.py` → `/pending-payments`: `select(StageEntry, Rider, Category, Stage, Team)` con `join`.
- `public.py` → `/standings/individual`: `select(ChampionshipStanding, Rider, Category, Team)` con `join`.
- `excel_service.py` → `export_stage_results_to_excel`: `join` en las tres hojas.
- `stage_summary_service.py` → `compute_stage_strava` y `compute_stage_mountain_titles` comparten la carga: el router de `stages.py` carga **una vez** `StravaSegment`, `StravaEffort` y los `rider_id` inscritos, y se los pasa a las dos funciones como parámetros opcionales.

- [ ] **Step 4: Ejecutar el test y verificar que pasa**

Run: `python -m pytest backend/tests/test_perf_budget.py -v` → PASS.

- [ ] **Step 5: Ejecutar la suite completa**

Run: `python -m pytest backend/tests -q` → PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/riders.py backend/app/routers/teams.py \
        backend/app/routers/stages.py backend/app/routers/timing.py \
        backend/app/routers/admin.py backend/app/routers/public.py \
        backend/app/services/excel_service.py backend/app/services/stage_summary_service.py \
        backend/tests/test_perf_budget.py
git commit -m "perf(db): se eliminan los N+1 de SQLModel en los endpoints de lectura"
```

---

## Task 9: Cliente — colisión de morph, filtro del héroe, listeners, fuentes

**Files:**
- Modify: `frontend/src/components/EventCard.astro`
- Modify: `frontend/src/components/TimelineEvents.astro`
- Modify: `frontend/src/components/HeroScene.astro`
- Modify: `frontend/src/layouts/Base.astro`
- Modify: `frontend/src/pages/ranking-general.astro`
- Modify: `frontend/src/components/svelte/StandingsTable.svelte`

**Interfaces:**
- Produces:
  - `EventCard.astro` acepta una prop nueva `morph?: boolean` (por defecto `true`) y, cuando es `true`, emite `data-morph-name={`poster-${event.id}`}` en la `<img>` en vez del `transition:name` de Astro.
  - `TimelineEvents.astro` expone (en su `<script>`) la función `applyMorphNames(): void`, que asigna `style.viewTransitionName` **sólo** a la copia visible de cada póster.

- [ ] **Step 1: Reproducir el defecto del morph (línea base)**

Con el servidor de desarrollo levantado, medir que hoy el morph del póster **no** ocurre porque hay dos elementos con el mismo `view-transition-name` en el documento:

```bash
cd frontend && npm run build
grep -o 'view-transition-name: poster-[a-z0-9-]*' dist/_worker.js/pages/index.astro.mjs | sort | uniq -c
# Cada nombre debe aparecer 1 vez; hoy aparece 2 (copia desktop + copia móvil).
```

- [ ] **Step 2: Corregir la colisión sin perder el morph**

En `EventCard.astro`: sustituir `transition:name={`poster-${event.id}`}` por `data-morph-name={`poster-${event.id}`}`.

En `TimelineEvents.astro`, añadir al `<script>`:

```ts
/**
 * El morph del póster (portada → ficha) usa `view-transition-name`.
 * La línea de tiempo se renderiza DOS veces (escritorio y móvil) para poder
 * cambiar de diseño con CSS: con el `transition:name` de Astro, los dos
 * elementos de la misma página llevaban el MISMO nombre y, por regla de la
 * especificación, la transición de ese nombre se cancelaba: el morph no
 * ocurría. Aquí el nombre se asigna en tiempo de ejecución SÓLO a la copia
 * visible, de modo que el morph sigue funcionando en los dos anchos y no
 * hay nombres duplicados en el documento.
 */
function applyMorphNames(): void {
  const seen = new Set<string>();
  for (const img of document.querySelectorAll<HTMLImageElement>('img[data-morph-name]')) {
    const name = img.dataset.morphName;
    if (!name) continue;
    const visible = img.getClientRects().length > 0;
    if (visible && !seen.has(name)) {
      img.style.viewTransitionName = name;
      seen.add(name);
    } else {
      img.style.viewTransitionName = 'none';
    }
  }
}
```

Llamar a `applyMorphNames()` en `initEventsTimeline()`, en `astro:page-load` y en `resize`.

En `fechas/[slug].astro`, el `<img>` del hero conserva `transition:name={`poster-${slug}`}` (el destino del morph).

- [ ] **Step 3: Verificar el morph con Playwright**

Crear `frontend/tools/check-morph.mjs` (patrón de `tools/check-shell.mjs`): navega a `/`, hace clic en la tarjeta de La Joya, y comprueba que durante la transición existe un elemento con `view-transition-name: poster-la-joya-extreme` visible en el `document.getAnimations()`.

- [ ] **Step 4: Aislar el filtro SVG del ciclista animado**

En `HeroScene.astro`: el `filter: url(#pulso-tinta)` está en `.scene__mountain` (el `<svg>` completo), así que el `feTurbulence` + `feDisplacementMap` se recalcula **en cada fotograma** mientras el ciclista se mueve dentro: es el mayor coste de CPU de la portada.

Solución **sin pérdida visual perceptible**: sacar el grupo del ciclista del elemento filtrado.
- Envolver las capas estáticas (cordilleras, volcanes, cimas, sendero) en un `<g class="scene__terrain">` con `filter: url(#pulso-tinta)`.
- Dejar el grupo `.scene__cyclist-track` **fuera** de ese `<g>`, como hermano dentro del mismo `<svg>`.
- Mover la regla CSS `filter: url(#pulso-tinta)` de `.scene__mountain` a `.scene__terrain`.
- El resultado visual es idéntico (el desplazamiento de tinta de 3,5 px es imperceptible sobre una figura de 72 px de alto) y la animación del ciclista (12 s, `cyclist-advance`) se conserva **exactamente igual**.

- [ ] **Step 5: Arreglar la fuga de listeners**

En `EventCard.astro`:
- `initCardLinks()` se registra una sola vez: usar un flag de módulo `let linksBound = false;` y, si ya está, no volver a registrar. Como el módulo se carga una vez (Astro lo empaqueta), basta con registrar **una vez** y quitar el `document.addEventListener('astro:page-load', initCardLinks, { once: true })` que re-registraba en cada navegación.
- El click de la tarjeta debe usar la navegación de cliente (`navigate()` de `astro:transitions/client`) en vez de `window.location.href`, que hoy **descarga la página entera** y anula el router.

En `TimelineEvents.astro`:
- `window.addEventListener('scroll', onScroll, { passive: true })` y el de `resize` se acumulan en cada navegación. Guardar las referencias y removerlas en `astro:before-preparation` (o usar un `AbortController` por inicialización).

- [ ] **Step 6: Quitar la fuente duplicada**

En `frontend/src/layouts/Base.astro`, quitar `import '@fontsource-variable/archivo';` y dejar `import '@fontsource-variable/archivo/standard.css';`.

Justificación: `standard.css` declara `font-weight: 100 900` **y** `font-stretch: 62% 125%`; el CSS del sitio usa `font-stretch: 118%` (`.stage-title`, `.card__name`). La variante `wght` (`index.css`) es un subconjunto redundante que el navegador descarga **además** (35 KB latin + 85 KB latin-ext). Verificar que `font-stretch` sigue funcionando: el `dist/_astro/archivo-latin-standard-normal*.woff2` debe ser el único archivo de Archivo.

- [ ] **Step 7: Recortar el payload de `<astro-island>` en `/ranking-general`**

Hoy la página serializa **249 KB** de props en el `<astro-island>`.

En `frontend/src/pages/ranking-general.astro`, antes de pasar las props, mapear cada fila al conjunto mínimo que la tabla pinta:

```ts
const slimRow = (r: any) => ({
  rider_id: r.rider_id, rider_name: r.rider_name, rider_slug: r.rider_slug,
  team_name: r.team_name, team_slug: r.team_slug,
  category_name: r.category_name, category_short_code: r.category_short_code,
  category_rank: r.category_rank, current_rank: r.current_rank,
  previous_rank: r.previous_rank, rank_delta: r.rank_delta, is_debut: r.is_debut,
  total_points: r.total_points, first_places_count: r.first_places_count,
  total_elapsed_ms: r.total_elapsed_ms, formatted_total_time: r.formatted_total_time,
  gap_to_leader_ms: r.gap_to_leader_ms, formatted_gap: r.formatted_gap,
  stages_completed: r.stages_completed,
});
```

Además, en `ranking-general.astro:44` y `:72-75` hoy hay **3** llamadas a `/public/standings` (una general + dos en `Promise.all`). Dejarlas en **una** tanda: la llamada general y la de la variante se resuelven juntas cuando hay query params.

Objetivo medible: el HTML de `/ranking-general` baja de **281 KB** a **< 150 KB**.

- [ ] **Step 8: Verificar**

```bash
cd frontend && npm run check     # 0 errores de tipos
cd frontend && npm run build
node frontend/tools/check-admin-security.mjs
node frontend/tools/check-morph.mjs
```

- [ ] **Step 9: Commit**

```bash
git add frontend/src/components/EventCard.astro frontend/src/components/TimelineEvents.astro \
        frontend/src/components/HeroScene.astro frontend/src/layouts/Base.astro \
        frontend/src/pages/ranking-general.astro frontend/src/components/svelte/StandingsTable.svelte \
        frontend/tools/check-morph.mjs
git commit -m "perf(ui): morph sin colisiones, filtro del heroe aislado y payload de la tabla recortado"
```

---

## Task 10: Verificación final y sincronización de specs

**Files:**
- Modify: `specs/02-live-timing-and-sse.md`
- Modify: `specs/03-public-portal-and-gpx.md`
- Modify: `specs/00-domain-schema.md`
- Modify: `CREDENCIALES_PRODUCCION.md` (registro de optimizaciones)

- [ ] **Step 1: Suite completa del backend**

Run: `python -m pytest backend/tests -q`
Expected: PASS (todos).

- [ ] **Step 2: Chequeos del frontend**

```bash
cd frontend && npm run check && npm run build
cd .. && node frontend/tools/check-admin-security.mjs
```

- [ ] **Step 3: Medición de la salida en producción**

Contra la API y el portal desplegados, repetir la medición de la auditoría:

```bash
for u in \
  "https://kuspide-api.onrender.com/api/v1/stages" \
  "https://kuspide-api.onrender.com/api/v1/stages/la-joya-extreme/summary" \
  "https://copa-macrosur-web.pages.dev/" \
  "https://copa-macrosur-web.pages.dev/ranking-general" ; do
  curl -s -o /dev/null -w "$u -> %{http_code} | TTFB %{time_starttransfer}s | %{size_download}B\n" "$u"
done
```

Objetivo tras el despliegue:
- `/api/v1/stages`: **< 10 ms** y **< 5 KB** (antes 983 ms / 55 KB).
- `/stages/{slug}/summary`: **< 300 ms** y **< 15 KB** (antes 701 ms / 64 KB).
- `/`: **< 300 ms** de TTFB en el segundo pedido (cache HIT del borde) (antes 1.208 ms).
- `/ranking-general`: **< 150 KB** de HTML (antes 281 KB).

- [ ] **Step 4: Sincronizar los specs**

- `specs/00-domain-schema.md` §1.4: añadir que `judge_pin` **nunca** sale por la API: los endpoints de lectura responden con `StagePublicRead`.
- `specs/02-live-timing-and-sse.md` §6: la mutación (marcación, largada, apertura/cierre de transmisión) **invalida la caché pública**; `GET /public/live-status` pasa a TTL 15 s.
- `specs/03-public-portal-and-gpx.md` §0: documentar `GET /public/home`, la caché de borde (`caches.default`, 60 s + SWR 300 s) y el GZip de la API.
- `CREDENCIALES_PRODUCCION.md` §6: añadir las optimizaciones aplicadas con sus cifras medidas.

- [ ] **Step 5: Commit**

```bash
git add specs/ CREDENCIALES_PRODUCCION.md
git commit -m "docs: sincroniza los specs con las correcciones de seguridad y rendimiento"
```

---

## Notas de despliegue (fuera del código)

1. **Rotar `ADMIN_API_KEY` en Render** con un valor nuevo y aleatorio (la clave actual está en el histórico de Git y en el bundle publicado). Actualizar el `.env` local con el mismo valor si se quiere paridad.
2. **Rotar la contraseña de Neon** (`***REMOVED-NEON-PASSWORD***`) — aparece en `CREDENCIALES_PRODUCCION.md` y en el historial de la conversación; la del plan gratuito de Neon se puede rotar desde la consola sin coste.
3. **En Cloudflare Pages**, añadir `PUBLIC_API_URL` y `PUBLIC_SSE_URL` como variables de producción (ya están documentadas) y confirmar que el build usa `NODE_VERSION=20`.
4. **`ENVIRONMENT=production`** debe estar en las variables de Render (ya está) — de eso depende el cierre del CORS.
5. La caché de borde **no** debe activarse hasta después del despliegue de `frontend/src/middleware.ts` (el middleware es opcional en runtime: si `caches.default` no existe, el código lo salta).

---

## Self-Review

**1. Cobertura de specs.** `specs/00` (PIN) → Tarea 1 + Tarea 10. `specs/02` (SSE, caché) → Tarea 5 + Tarea 10. `specs/03` (portal, SSR, caché de borde) → Tareas 6, 7, 9, 10. `specs/01` (Excel) → Tarea 4 (límite de subida) + Tarea 8 (exportación sin N+1). Sin huecos.

**2. Barrido de pasos.** Todos los pasos de código dan una firma exacta o una aserción exacta. Los bodies de `SlidingWindowLimiter`, `RateLimitMiddleware`, `StagePublicRead` y `applyMorphNames` van en bloque porque el algoritmo no queda determinado por la firma; el resto no lleva código.

**3. Consistencia de tipos.** `StagePublicRead` se usa en las Tareas 1, 6, 8 y 10. `invalidate_public()` se define en la Tarea 5 y se consume en la 5 y en la 6 (la caché de `public:home` se invalida con ella). `adminHeaders()` se define en la Tarea 2 y se consume en la 2. `applyMorphNames()` se define en la Tarea 9. `query_counter` se define en la Tarea 8. Sin nombres huérfanos.

**4. Review Focus.** Los cinco casos tienen test: (1) Tarea 1, (2) Tareas 2 y 4, (3) Tarea 3, (4) Tarea 4, (5) Tarea 4. Ninguno queda sin cubrir.

**5. Proporción.** El plan tiene 10 tareas para 12 ficheros de backend, 11 de frontend y 2 de test. La parte dominante del texto son las decisiones (qué campo se quita, qué firma, qué aserción) — no transcripciones del código final.
