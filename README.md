# Copa MacroSur MTB 2026 — Plataforma de cronometraje y clasificación

Plataforma web para organizar, cronometrar y publicar un campeonato de
ciclismo MTB de cuatro fechas: portal público, panel de cronometraje en vivo,
motor de clasificación acumulada y perfiles de ruta.

El proyecto existe por cuatro motivos a la vez:

| | |
| :--- | :--- |
| **Probar tecnología** | Un campeonato real es el mejor banco de pruebas posible: datos sucios de verdad, usuarios reales, una carrera que empieza a las 08:00 y una montaña de casos límite que ningún tutorial cubre. |
| **Usar agentes de IA** | Todo el proyecto se construye con agentes, siguiendo un proceso de contrato → plan → implementación → revisión, con un registro de decisiones y un revisor independiente por tarea. Ver [Desarrollo con agentes](#desarrollo-con-agentes). |
| **Presentar una carrera MTB** | El campeonato Copa MacroSur MTB es real: cuatro fechas en Arequipa, con corredores, equipos, premios en dólares y un público que mira desde el móvil. |
| **Hobby** | Es un proyecto de fin de semana, sin jefe y sin plazos: se hace porque da gusto. |

---

## Qué hace

- **Portal público** (12 páginas): calendario del campeonato, ficha completa de
  cada fecha, ranking acumulado y por fecha, clasificación por equipo, premios,
  eventos de ruta, inscripciones, reclamos y perfil de cada corredor.
- **Cronometraje en vivo**: el juez marca llegadas desde un móvil y el tablero
  público se actualiza en el acto, **también sin cobertura**.
- **Clasificación acumulada**: motor de puntajes propio con desempates por
  reglas de reglamento y corte "a la fecha" al estilo de la Vuelta a Francia.
- **Perfil de ruta**: altimetría, puertos, cimas, track GPX descargable y
  visor del trazado.
- **Títulos de montaña**: King y Queen of the Mountain y los dos Kamikaze (el
  descenso más rápido), resueltos sobre intentos reales de Strava.
- **Consola del organizador**: aprobación de pagos, ingesta masiva de listas de
  inscritos, subida de rutas y control de la ventana de transmisión.
- **Relevo instantáneo**: cada marcación del juez se refleja en el portal en el
  acto; no hay ventana de datos caducados.
- **Morph del póster**: al abrir la ficha de una fecha, su póster se transforma
  en el sitio, desde la tarjeta del calendario.
- **Portada editorial animada**: relieve volcánico con textura de tinta, línea
  de tiempo con recorrido iluminado al hacer scroll, y transiciones de página
  de 180 ms.
- **Sin JavaScript no se pierde nada**: cada página se renderiza en servidor y
  se puede leer, imprimir y compartir con el intérprete desactivado.

---

## Stack

### Backend — Python 3.12

| | |
| :--- | :--- |
| **Framework** | FastAPI 0.136 con `StreamingResponse` para SSE |
| **ORM** | SQLModel sobre SQLAlchemy 2.0 **async** |
| **Base de datos** | PostgreSQL (asyncpg) · SQLite (aiosqlite) en local |
| **Migraciones** | Alembic |
| **Procesamiento de datos** | `openpyxl` (Excel), `pypdf` (PDF de resultados), `gpxpy` (tracks GPX), `boto3` (objetos compatible con S3) |
| **Validación** | Pydantic v2 con `SettingsConfigDict` |
| **Tiempo real** | Server-Sent Events. **Sin WebSockets**, por decisión propia |
| **Pruebas** | pytest + pytest-asyncio + httpx (`ASGITransport`) |

### Frontend — Astro 5 + Svelte 5

| | |
| :--- | :--- |
| **Framework** | Astro 5.18 en modo `output: 'server'` (SSR) |
| **Islas** | Svelte 5.57 con **Runes** exclusivamente (`$state`, `$derived`, `$effect`, `$props`) |
| **Estilos** | CSS nativo con `<style>` scoped. **Cero Tailwind, cero Bootstrap** |
| **Animación** | GSAP 3.15 (ScrollTrigger) + Lenis 1.3, cargados con `import()` dinámico |
| **Offline** | `idb` sobre IndexedDB · Service Worker con precarga |
| **Tipografías** | Archivo, Inter, Geist Mono e Instrument Serif, autoalojadas |
| **Tipado** | TypeScript estricto (`strict: true`) |
| **Pruebas de interfaz** | Playwright (`playwright-core`) |

### En el navegador

- **IndexedDB** para las marcaciones del juez cuando no hay red.
- **Service Worker** para que el panel del juez abra sin conexión.
- **`navigator.wakeLock`** para que la pantalla no se apague durante la meta.
- **`crypto.randomUUID()`** como clave idempotente de cada marcación.

---

## Arquitectura

```
                      ┌──────────────────────────────┐
   navegador  ───────►│  Astro 5 SSR (12 páginas)    │
                      │  · 6 islas Svelte (Runes)    │
                      │  · caché de borde en el CDN  │
                      └──────────────┬───────────────┘
                                     │  fetch (1 llamada por página)
                                     ▼
                      ┌──────────────────────────────┐
                      │  FastAPI                     │
                      │  · router /public            │
                      │  · router /stages            │
                      │  · router /timing (SSE)      │
                      │  · router /admin             │
                      └──────────────┬───────────────┘
                                     │  SQLAlchemy async
                                     ▼
                      ┌──────────────────────────────┐
                      │  PostgreSQL                  │
                      │  18 tablas · 6 enums         │
                      │  Alembic                     │
                      └──────────────────────────────┘

   juez (móvil)  ──►  IndexedDB  ──►  batch-sync idempotente  ──►  SSE
                                          (UUID, con reloj del servidor)
```

**24 entidades de dominio**, 18 tablas: `Team`, `Rider`, `Category`, `Stage`,
`StartWave`, `Checkpoint`, `RouteSummit`, `StageEntry`, `TimingEvent`,
`ChampionshipStanding`, `TeamStageStanding`, `TeamChampionshipStanding`,
`StravaSegment`, `StravaEffort`, `SpecialAward`, `FeedbackTicket`,
`ExtraEvent`, `PrizeTier`.

---

## Datos de origen

El plataforma se alimenta de los archivos que produce la organización, y cada
formato tiene su regla de lectura.

**Listas de inscritos (`.xlsx`).** Llegan por bloques de categoría, con
cabeceras repetidas, celdas sucias y una columna de club con valores de ruido
(`LIBRE`, `TEAM`, guiones sueltos). El importador es **transaccional**: si
hay un solo error crítico revierte todo y responde `422` con la lista de
errores por fila y campo. El upsert es idempotente, así que reimportar la
misma lista no duplica nada.

**Resultados oficiales (`.pdf`).** El extractor trabaja en **dos fases**: la
primera rearma los renglones que el PDF parte cuando el nombre del club o del
corredor es largo; la segunda extrae dorsal, tiempo, puesto y puntos. El
cuerpo del renglón es la autoridad: el dorsal publicado manda sobre el de la
lista de inscritos, y cuando ambos chocan se liberan los dorsales en dos
fases antes de aplicar los nuevos. Un dorsal que aparece en los resultados y
no en la lista **se reconstruye** como corredor e inscripción, en lugar de perderse.

**Tracks GPX (`.gpx`).** Se parsean en memoria y se simplifican a 500 puntos
para la geometría que se guarda. El desnivel que se **publica** es el de la
ruta oficial a resolución completa: la simplificación pierde unos treinta
metros de subida y el perfil acababa dando dos cifras distintas para la misma
carrera.

**Strava.** Los segmentos y los tiempos de los intentos se extraen de las
rutas oficiales con automatización de navegador (CDP). De ahí salen el KOM, el
QOM y los dos Kamikaze, con dos reglas: sólo cuentan intentos **medidos el día
de la carrera** y **de corredores inscritos**.

**Regeneración.** `seed.py` es idempotente (UPSERT): se puede volver a
ejecutar sin duplicar corredores, inscripciones ni resultados.

---

## Cronometraje y trabajo sin conexión

El panel del juez (`/admin/juez`) está pensado para una montaña, con el móvil
en una mano y la cobertura perdiéndose:

- **Teclado numérico táctil** para marcar dorsales sin abrir el teclado del
  sistema.
- **Modo ráfaga**: se *congela* el instante de un sprint masivo y luego se
  asigna un dorsal a cada instante capturado.
- **Cola local en IndexedDB**: cada marcación se guarda en el dispositivo
  antes de intentar enviarla.
- **Sincronización por lotes** cuando vuelve la red, con **idempotencia por
  UUID**: reenviar la misma marcación no duplica nada.
- **Reloj calibrado contra el servidor**: el juez ve la hora oficial, no la de
  su teléfono, que puede desviarse.
- **Conflicto 409 explícito**: si un dorsal ya cruzó meta, el backend responde
  con el tiempo que ya tenía y el juez decide si lo reemplaza.
- **`wakeLock`** para que la pantalla no se apague en la meta.
- **Service Worker** para que el panel abra sin cobertura.

El lado público recibe los eventos por **SSE** con *heartbeat* cada 20
segundos, y el cliente se reconecta solo.

---

## Motor de clasificación

Escala de puntos por puesto (1.º 10 … 10.º 1, y 1 punto desde el 11.º en
adelante; DNF/DNS/DSQ, 0), con desempates en este orden: puntos, victorias de
categoría, tiempo acumulado y nombre.

El ranking acumulado se calcula **a la fecha** (patrón Vuelta a Francia): la
fecha elegida es el corte, y la delta de puestos compara contra la fecha
anterior. Existe además el modo "fecha", que muestra sólo esa carrera.

Todo el cálculo vive en `backend/app/services/scoring.py` y
`standings_service.py`, y está cubierto por tests: los tiempos, los puntos y
las deltas tienen aserciones.

---

## Seguridad aplicada al código

- **El PIN de juez nunca sale por la API.** Los endpoints de lectura
  responden con esquemas de salida explícitos (`response_model`), así que el
  campo no se serializa aunque exista en el objeto. La geometría de la ruta
  (~58 KB por fecha), que ninguna página consume, tampoco viaja.
- **Los secretos no están en el repositorio.** La clave de administración no
  tiene valor por defecto: si falta, los endpoints de administración fallan
  **cerrados** en vez de aceptarla. Los PIN de juez se siembran en la base de
  datos desde el entorno y se rotan con un script, sin tocar el código.
- **Comparación en tiempo constante** (`hmac.compare_digest`) de las
  credenciales, y **CORS cerrado a los orígenes reales**: un origen de
  terceros no recibe permiso.
- **Límites de entrada**: cuota por IP y regla con ventana deslizante, techo
  del tamaño del cuerpo y de los archivos antes de leerlos en memoria, y
  longitudes máximas en los campos de texto libre.
- **Sin XSS en el panel**: la lista de pagos se construye con nodos DOM y
  `textContent`, nunca con `innerHTML` interpolado, y el enlace del
  comprobante sólo se acepta si el esquema es `http`/`https`.
- **Historial limpio**: los valores que estuvieron en el código se purgaron
  del historial de Git y se rotaron, de modo que un clon del repositorio no
  expone ninguna credencial.

---

## Diseño

Sistema de diseño editorial propio: rejilla *bento*, bordes finos, esquinas
rectas, tipografía con contraste serif/sans y números tabulares.

- **127 variables CSS** de token: color, tipografía, escala de espaciado,
  grosores de línea, radios y tiempos de transición.
- **Cuatro tipografías autoalojadas**, sin peticiones a terceros.
- **Tema claro y oscuro** con un conmutador que se aplica antes del primer
  pintado (sin destello).
- **Sin emojis** en la interfaz: los rótulos son monoespaciados y en
  mayúsculas.

El sistema de diseño está **adaptado de ArtCraft**
([github.com/storytold/artcraft](https://github.com/storytold/artcraft)),
proyecto de doble licencia MIT / Apache-2.0. La atribución completa, con los
ficheros derivados y las licencias de terceros, está en [`NOTICE`](./NOTICE) y
[`LICENSE-ARTCRAFT`](./LICENSE-ARTCRAFT).

---

## Desarrollo con agentes

El proyecto se construye con un proceso agéntico explícito.

1. **Contrato antes que código.** `specs/` fija el dominio, el motor de
   puntuación, el cronometraje y el portal. `AGENTS.md` es la constitución del
   proyecto: stack innegociable, convenciones y protocolo.
2. **Plan escrito y ejecutado por tareas.** Cada tarea tiene su brief, sus
   pasos, sus tests y su mensaje de commit. Los planes están en
   `docs/superpowers/plans/`.
3. **Un implementador y un revisor por tarea.** El implementador escribe el
   código y sus tests; un revisor **independiente** recibe el diff y dicta
   veredicto de especificación y de calidad. Un fallo entra en un bucle de
   corrección con re-revisión acotada.
4. **Registro de decisiones.** Cada decisión que el controlador toma en nombre
   del proyecto queda escrita con su motivo y con lo que costaría
   equivocarse.
5. **Las revisiones se comprueban ejecutando.** Los revisores levantan el
   servidor, miden el resultado real en el navegador y verifican que un test
   falla con el código anterior.

Resultado: **192 tests** en el backend y **8 regresiones de interfaz** en
navegador real, sobre ~32.000 líneas de código propio (backend ~8.000,
tests ~5.200, frontend ~18.500).

---

## Estructura

```
.
├── AGENTS.md              constitución del proyecto (stack, protocolo)
├── PLAN.md                plan maestro del campeonato
├── NOTICE                 atribución del material de terceros
├── specs/                 contratos: dominio, excel y scoring, SSE, portal
├── races/                 datos de origen: xlsx, pdf, gpx
├── docs/superpowers/plans/ planes de implementación
├── backend/
│   ├── app/
│   │   ├── core/          config, db, caché, seguridad, límites, secretos
│   │   ├── models/        entidades y esquemas
│   │   ├── routers/       public, stages, riders, teams, timing, admin, excel
│   │   └── services/      scoring, standings, excel, pdf, gpx, strava, perfiles
│   ├── migrations/        Alembic
│   ├── scripts/           rotación de PIN, perfil SVG, sincronización Strava
│   └── tests/             18 ficheros de test, 192 tests
└── frontend/
    ├── src/
    │   ├── pages/         12 páginas Astro
    │   ├── components/    24 componentes Astro + 6 islas Svelte
    │   ├── layouts/       Base (shell) y Showcase (escaparate)
    │   ├── lib/           cliente de API, IndexedDB, admin, navegación
    │   ├── scripts/       shell del sitio, movimiento, regulador de scroll
    │   ├── styles/        tokens, reset, display, motion
    │   └── middleware.ts  caché de borde
    └── tools/             regresiones de interfaz (Playwright) y utilidades
```

---

## Correrlo en local

```bash
# 1) Dependencias
pip install -r backend/requirements.txt
cd frontend && npm install && cd ..

# 2) Variables de entorno
cp .env.example .env        # y rellena ADMIN_API_KEY y JUDGE_PIN_F1..F4

# 3) Base de datos y datos reales
PYTHONPATH=. python -m backend.app.seed

# 4) Backend y frontend
./start.sh                  # API en :8000, portal en :4321
```

El portal queda en `http://localhost:4321`, la API en
`http://localhost:8000/docs` y el panel del juez en
`http://localhost:4321/admin/juez`.

---

## Pruebas

```bash
python -m pytest backend/tests -q          # 192 tests
cd frontend && npx astro check             # 0 errores de tipos
cd frontend && npm run build               # build de producción

# regresiones de interfaz (con el servidor levantado)
node frontend/tools/check-morph.mjs            # el morph del póster
node frontend/tools/check-shell.mjs            # navegación de cliente, cabecera
node frontend/tools/check-admin-security.mjs   # sin secretos en el bundle
```

---

## Créditos y licencias

- **Diseño**: adaptado de **ArtCraft**
  ([github.com/storytold/artcraft](https://github.com/storytold/artcraft) ·
  [getartcraft.com](https://getartcraft.com)), bajo doble licencia MIT /
  Apache-2.0. Ver [`NOTICE`](./NOTICE) y [`LICENSE-ARTCRAFT`](./LICENSE-ARTCRAFT).
- **Tipografías**: Archivo, Inter, Geist Mono e Instrument Serif, autoalojadas
  con `@fontsource` bajo SIL Open Font License 1.1.
- **Datos**: las listas de inscritos, los resultados oficiales y los tracks
  pertenecen a la organización del campeonato.
