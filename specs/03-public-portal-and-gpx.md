# Spec 03: Portal Público (Estilo GetArtCraft), Mapas GPX, Perfiles y Reclamos

> **Estado:** COMPLETADO ✅  
> **Fecha de Verificación:** 20 de Octubre de 2026  
> **Evidencia:** Build limpio con Astro 5 en modo **SSR** (`npm run build` + `node dist/server/entry.mjs`), `astro check` con **0 errores de tipos**, diseño editorial GetArtCraft adaptado de `copiaartcraft`, visor GPX interactivo SVG + altimetría y cero emojis en la UI.
> **20-Oct-2026:** `/ranking-general` se rediseña como clasificación acumulada "a la fecha" con grupos PRO / NORMAL / E-MTB, selector de fecha y de categoría reutilizables, control segmentado de pestañas, celda apilada en móvil y una sola identidad cromática por vista (el Δ usa colores semánticos). Ver §1.3.1.

## 0. Modo de Render: SSR (Server-Side Rendering) — decisión de integridad de datos

> **Cambio del 20 de Octubre de 2026.** El portal pasó de prerenderizado (SSG) a **SSR con adaptador Node** (`output: 'server'` + `@astrojs/node` en modo `standalone`).

### 0.1 Por qué

Las páginas de datos (resultados por fecha, fichas de fecha, ranking general, perfiles de corredor y de equipo) se construían con `getStaticPaths()` + un `fetch` a la API **durante el build**. El `fetch` estaba envuelto en un `try/catch` vacío, de modo que:

1. Si el backend no estaba levantado al ejecutar `npm run build`, las tablas se horneaban **VACÍAS** sin ningún error ni aviso visible. El sitio se publicaba con ceros resultados y parecía un fallo de datos, no de build.
2. Los `getStaticPaths()` tenían **slugs hardcodeados** (`la-joya-extreme`, `z-xtreme-2026`, `vuelta-a-los-poblados`, `quequena-xtreme`). Cualquier cambio de nombre o slug en el seed rompía las rutas con un 404 silencioso.
3. Los perfiles de corredor y equipo servían un **mock hardcodeado** (`riderMock` con nombre real y DNI ficticio) cuando la API no respondía, y sus slugs no coincidían con los de la BD, de modo que todo enlace a `/corredor/{slug}` terminaba en 404.

Con la corrección de integridad de datos (ver `specs/01` §1.5) se volvió crítico que la web **siempre** muestre el estado real de la BD: con SSG, un build ejecutado con la BD desactualizada publicaba datos viejos de forma silenciosa e irreversible.

### 0.2 Reglas

- **Todo el portal es SSR.** Las páginas que dependen de la API se renderizan contra la BD en cada request.
- **Sin `getStaticPaths()`** en rutas dinámicas: el `slug` se resuelve en runtime y, si la API responde `404`, la página devuelve **HTTP 404** con un mensaje propio (no una página de error genérica).
- **Sin mocks.** Si la API no responde, la página devuelve `503`; nunca se inventan datos de_argumento fictitious.
- **Sin datos ficticios:** los perfiles de corredor y equipo muestran únicamente lo que devuelve la API.
- **El `fetch` de servidor usa `PUBLIC_API_URL`** (`frontend/src/lib/api.ts`), igual que el cliente.
- **Los recursos estáticos siguen serviéndose desde `public/`** (manifiesto PWA, `sw.js`, imágenes, GPX).
- **`/en-vivo` y `/admin/juez` siguen usando `Base.astro`** y **no cargan GSAP ni Lenis** (ver `AGENTS.md` §2). El SSR no altera esa regla: el motion editorial sigue únicamente en `Showcase.astro`.
- **Ejecución:** `npm run build && node dist/server/entry.mjs` (producción) o `npm run dev` (desarrollo). `start.sh` acepta `dev` (por defecto) y `prod`.

### 0.3 Verificación

| Comprobación | Resultado |
| :--- | :--- |
| `npm run build` | OK — bundle cliente + `dist/server/entry.mjs` |
| `npx astro check` | **0 errores**, 0 warnings, 0 hints (33 archivos) |
| `GET /fechas/la-joya-extreme/resultados` | 200 con **198 resultados con tiempo** (225 filas) |
| `GET /fechas/z-xtreme-2026/resultados` | 200 con **112 resultados con tiempo** (167 filas) |
| `GET /fechas/no-existe` | **404** |
| `GET /corredor/no-existe` / `/equipos/no-existe` | **404** |

---

## 1. Mapa de Rutas Públicas (Astro Frontend)

### 1.1 Portada del Campeonato (`/`)
Diseño Bento Grid modular oscuro (estilo GetArtCraft consumiendo los estilos y layout de referencia):
- **Hero Box:** Cuenta regresiva para la próxima fecha (o indicador rojo parpadeante `EN VIVO AHORA` con enlace directo a `/en-vivo` si `Stage.status == LIVE`), más botón destacado de Pre-Inscripción.
- **Grilla de las 4 Fechas:** 4 tarjetas Bento modulares mostrando el cartel oficial (generado con Nanobanana y alojado en Cloudflare R2), fecha, distancia (`km`), desnivel (`+m`) y estado (`Finalizada`, `Inscripciones Abiertas`, `Próximamente`).
- **Resumen del Ranking Acumulado:** Top 5 de cada categoría individual con enlace directo a `/ranking-general`.
- **Showcase Copa de Equipos:** Tarjeta Bento destacada con el **Team Líder del Campeonato** (logo, puntos y victorias) y podio de los 3 mejores equipos.
- **Showcase de Premios Especiales:** Cajas destacadas para premios de marca (ej. *Premio Especial Coca*, *Rey de la Montaña*).

### 1.2 Página de Fecha Individual (`/fechas/[slug]`)
> Ruta **dinámica en SSR**: el `slug` se resuelve contra la API en cada request. Si la fecha no existe, la respuesta es `404`.
1. **Cabecera y Ganadores:** Podio oficial por categoría y botón prominente hacia la tabla completa de resultados de esa fecha.
2. **Bento de Estadísticas Extremas de la Fecha:**
   - Tarjeta **"El Más Rápido (Scratch)"**: Nombre, categoría, dorsal y tiempo mínimo (`MIN(finish_elapsed_ms)`).
   - Tarjeta **"El Más Persistente / Farolito en Meta"**: Nombre, dorsal y tiempo máximo (`MAX(finish_elapsed_ms)`).
3. **Podio de Equipos de la Fecha:** Los 3 Teams con mayor cantidad de puntos sumados en la jornada.
4. **Bento de Ruta Interactiva y Descarga GPX (Isla Svelte 5 `client:visible`):**
   - Botón de descarga directa del archivo `.gpx` alojado en Cloudflare R2.
   - Mapa interactivo (`MapLibre GL` o `Leaflet` con capa oscura) dibujando `Stage.route_geojson` y marcando la ubicación de los `Checkpoints` (Partida, Intermedios, Meta).
   - Gráfico interactivo de altimetría: al deslizar el dedo o ratón sobre el perfil de elevación, un indicador se desplaza en tiempo real sobre el trazado del mapa mostrando la ubicación exacta de la subida.
5. **Bento de Segmentos Strava de la Fecha:**
   - Lista de segmentos oficiales de la ruta con distancia, pendiente media (`%`) y el Top 10 de tiempos registrados en el día (alimentado por `StravaEffort`).
6. **Bento de Premios de la Fecha:** Ganadores y descripción de premios especiales de la jornada.
7. **Collage Fotográfico (Cloudflare R2):**
   - Galería de alta velocidad con miniaturas optimizadas (`webp`/`avif`) desde el bucket R2 de la fecha, visor modal tipo lightbox y enlace al álbum completo en alta resolución.

### 1.3 Tabla de Posiciones y Acumulado (`/ranking-general` y `/fechas/[slug]/resultados`)

#### 1.3.1 Clasificación acumulada "a la fecha" (`/ranking-general`)

Rediseño del 20 de Octubre de 2026 siguiendo el patrón de navegación de
`letour.fr/es/clasificaciones` y la identidad cromática de `getartcraft.com/apps`
(sección `02 / The Lineup`).

**Modelo de datos (backend `standings_service.py`):**
- La clasificación se **deriva de `StageEntry`** (los resultados oficiales), no de
  tablas de cache. Así un corte por fecha es siempre coherente con
  `/fechas/[slug]/resultados`.
- **Ámbitos** (el tiempo acumulado solo es comparable dentro de un ámbito, porque
  las distancias y los desniveles no son homologables entre modalidades):

  | Grupo | Categorías | Color |
  | :--- | :--- | :--- |
  | `PRO` | ELITE, MASTER A, MASTER B, MASTER C | azul `#2f7bf5` |
  | `NORMAL` | TURISMO OPEN, TURISMO MASTER, MASTER D, OPEN DAMAS, DAMAS MASTER, JUVENILES 15-17 | lima `#7bb51c` |
  | `E-MTB` | E-BIKE OPEN | naranja `#f26b1d` |
  | `EQUIPO` | Copa de Clubes (todas las categorías) | magenta `#e0368f` |

  El color identifica **una cosa por vista**: el grupo activo. Los tokens viven
  en `frontend/src/styles/tokens.css` (`.scope-*` → `--scope` / `--scope-ink`).

- **Desempate del ámbito:** puntos DESC → victorias DESC → tiempo acumulado ASC →
  nombre ASC. Es la regla de `specs/01` §3.2 con el "puesto en la última fecha"
  sustituido por el tiempo acumulado, porque en un ranking agrupado por
  categorías ese puesto pertenece a otra categoría y no es comparable.
- Cada fila expone además el **puesto dentro de su propia categoría** y el
  **delta contra la fecha anterior** (`▲` subió, `▼` bajó, `NUEVO` debuted,
  `—` en la primera fecha, donde no hay con qué comparar).
- La **diferencia** es la brecha de tiempo acumulado con el líder. Puede ser
  negativa: el líder por puntos no siempre es el más rápido (puede haber corrido
  más etapas o de categoría más lenta). Se muestra con su signo, es información
  real.

**Interfaz:**
1. **Cinta:** rótulo `CATEGORÍAS` + el grupo o la categoría seleccionada, y a la
   derecha los metadatos (fechas disputadas, km acumulados, fecha de corte).
2. **Pestañas = control segmentado en dos grupos:** `[ PRO | NORMAL | E-MTB ]` y
   `[ EQUIPO ]`, con un hueco deliberado de 12px entre ambos. La Copa de Equipos es
   una clasificación distinta, no una categoría más. Cada grupo lleva borde de 1px,
   las celdas se separan por hairline y **la celda activa se invierte**
   (`--invert-bg` / `--invert-fg`), como las pastillas de `getartcraft.com`. Solo
   el rótulo: sin cuadros ni numeración. La inversión la aplica la **pastilla**
   con `mix-blend-mode: difference` (ver §1.3.3): el rótulo se invierte
   únicamente donde la pastilla lo cubre, así que **nunca queda ilegible ni al
   llegar ni al irse**. En móvil las cuatro pestañas se estrechan
   (`3.5 / 5 / 4.25 / 4.75rem`, interletraje 0.08em) para que **EQUIPO también
   quepa**: en 390px la barra completa mide 356px y no hay scroll horizontal.
3. **Selector de CATEGORÍA (casi escondido):** dentro de la pestaña activa
   ofrece **TODOS** (agrupa las categorías de esa pestaña) o una categoría
   concreta, que aísla su clasificación.
4. **Selector de FECHA (casi escondido):** elige el corte del acumulado (patrón
   Tour). Es el **mismo componente** (`ScopeControl.svelte`) que el selector de
   categoría: lista desplazable, mono 11px en mayúsculas y el elemento activo
   invertido en el color del grupo. El panel va con `z-index: 50` y sombra
   profunda para leerse por encima de los badges de la tabla, y su **foco usa el
   color del grupo activo** (`--scope-ink`), nunca el azul por defecto del
   navegador. El botón muestra **solo el nombre de la carrera**
   (`LA JOYA EXTREME`, `KÚSPIDE Z XTREME III`): con el número de fecha y la
   fecha era una línea interminable en la cabecera. La fecha sí aparece en la
   **lista desplegable** (`hideMeta` lo saca solo del botón) y en la cinta
   (`CORTE …`).
5. **Barra de controles:** el buscador **ocupa el espacio disponible**
   (`flex: 1 1 14rem`, hasta `24rem`) entre los dos selectores; no es una caja
   mínima. En móvil los dos selectores van en una fila de dos columnas
   (`1fr 1fr`) y el buscador al 100% debajo: ~80px menos de alto.
6. **Tabla:** Puesto · Δ · Ciclista · Categoría · En cat. · Equipo / Club ·
   Tiempo Acum. · Diferencia · Puntos. Todas las columnas numéricas declaran
   `font-variant-numeric: tabular-nums`.
7. **Color: uno por vista.** Solo el grupo activo tiene color (`.scope-*` →
   `--scope` / `--scope-ink`): la cinta, la celda activa de la pestaña, la ficha
   del podio y el velo del líder. Las etiquetas de categoría son monocromas.
9. **El Δ usa colores SEMÁNTICOS**, no el color del grupo: `▲` verde
   (`--status-up`), `▼` rojo (`--status-down`), `=` a α .45 (`--status-flat`),
   en tema claro y oscuro. Informa de ranking, no de estilo.
10. **Podio.** El podio se marca en la caja del puesto: **1 oro · 2 plata · 3 bronce**
   (`--podium-1/2/3`), **insignia SÓLIDA** con texto oscuro encima (`--podium-fg`):
   los tres primeros tienen que verse de un vistazo, también en móvil y con los
   tonos apagados de una tabla con mucha información. Además, borde izquierdo de
   `3px` en la fila (`inset box-shadow`) con el metal correspondiente.
   **Ninguna fila tiene estado persistente**: el 1º NO lleva velo (una fila
   teñida parecía una selección) y el único realce es el **hover** (velo del 5%
   del color del grupo). Nada de fichas con iniciales: eran ruido de plantilla
   y obligaban a reservar un hueco para alinear los nombres.
11. **Hover discreto:** velo del 5% del color del grupo al pasar el ratón. Es un
    paso de ratón, no un estado de la fila.
12. **Ejes de columna:** sin fichas ni huecos reservados, los nombres caen
    solos en el mismo eje X. El club es la columna que respira
    (`width: 30%; min-width: 180px`, sin recorte): "CLUB ORIGINAL BIKES…" ya no
    se corta cuando sobra espacio en pantalla.
13. **Diferencia:** la brecha de tiempo acumulado respecto al líder de la
    clasificación (ordenada por puntos). **Puede ser negativa** si un corredor
    con menos puntos acumula menos tiempo; la cabecera y esas celdas llevan un
    `title` que lo explica.
14. **Móvil (<48em) — celda apilada de 3 columnas**
    (`44px 1fr auto`, `gap 10px`, `padding 10px 12px`):
    - col 1: caja de `PUESTO` y debajo el `Δ` (11px);
    - col 2: nombre (700 / 13px, con puntos suspensivos) y debajo el badge de
      `CATEGORÍA` + el `EQUIPO / CLUB` en secundario (11px);
    - col 3: `20 pts` (número 800 / 14px, `pts` 11px) y debajo el
      `TIEMPO ACUM.` en mono tabular.
    La **fila de equipo usa el mismo patrón**: rango · club + subtítulo con
    etiquetas (`3 OROS · 3 PLATAS · 5 BRONCES`) · puntos + tiempo. Las columnas
    sueltas OROS/PLATAS/BRONCES/CORREDORES se ocultan en móvil: sin etiqueta
    eran números huérfanos que no se sabían leer.
    La barra de pestañas desliza con `overflow-x: auto` y `scrollbar-width: none`.
    **Sin scroll horizontal**: la tabla cabe en 390px.
15. **Ancho:** la página usa un contenedor de `108rem` (no el de `80rem` de las
    demás): una clasificación es una tabla densa y debe aprovechar la pantalla.

**Endpoint:** `GET /api/v1/public/standings?stage=&scope=&category_id=&kind=`
devuelve `{rows, context}`; `context` lleva las fechas disponibles, los grupos
con sus categorías, el catálogo de categorías y los metadatos de cabecera.

### 1.3.3 Movimiento de la clasificación

La página es de datos, no de escaparate: **no carga GSAP ni Lenis** (regla de
`AGENTS.md` §2). El movimiento sale de las primitivas de Svelte 5 y de CSS, y
todo respeta `prefers-reduced-motion`.

| Momento | Técnica | Detalle |
| :--- | :--- | :--- |
| **Selección de pestaña** | Pastilla invertida deslizante, **CSS puro** | Una pastilla absoluta dentro de cada grupo se posiciona con `data-active` y los anchos de cada pestaña (`--w-pro/--w-normal/--w-ebike/--w-teams`); `transform` + `width` con `transition` de 300ms. La selección **se ve moverse** en vez de saltar |
| Cambio de fecha → **las filas se reordenan** | `animate:flip` (Svelte 5) | 320ms `cubicOut`: el corredor que sube de puesto se mueve en lugar de saltar |
| Entrada/salida de filas | `transition:fade` (Svelte) | 150ms: al cambiar de ámbito, las filas que entran aparecen y las que salen se van |
| Entrada del contenido | keyframe CSS `rank-in` sobre el `<tbody>` | 240ms: **translateY + desenfoque, NUNCA opacidad 0** (ver abajo) |
| Carga de datos | Línea de progreso de 2px | `position: absolute` sobre el cuerpo de la tabla: **cero layout shift** (el `thead` no se mueve) |
| Hover de fila | transición del velo | 150ms (`--default-transition-duration`) |
| Celda activa del segmentado | "press" de 90ms | `scale(0.98)` al pulsar |

**Tres reglas que-no-negociables (learned the hard way):**

1. **La tabla nunca puede ocultarse durante una animación.** La keyframe de
   entrada arrancaba en `opacity: 0`; al cambiar de pestaña el `<tbody>` se
   recreaba y la tabla se volvía invisible 260ms sobre el fondo `--bg-raised`
   (un bloque negro). Ahora la entrada solo desplaza y desenfoca: la opacidad
   se queda en 1.
2. **La pastilla se posiciona sin JavaScript.** Medirla con `getBoundingClientRect`
   obligaba a esperar al ciclo de render (`tick()` o `requestAnimationFrame`): en
   una pestaña de segundo plano la espera no se resolvía y la pastilla se quedaba
   sin medir (o con 300ms de retraso). Con `data-active` + anchos fijos en CSS
   la pastilla está en su sitio desde el primer pintado.
3. **La inversión la hace la pastilla, no el rótulo.** La celda activa invertía
   su propio color (`color: --invert-fg`) en el mismo instante en que cambiaba
   la clase, mientras la pastilla tardaba 300ms en llegar: durante ese hueco los
   dos rótulos implicados quedaban **invisibles** (en tema oscuro, texto casi
   negro sobre fondo casi negro; en tema claro, texto blanco sobre blanco).
   Ahora la pastilla es blanca con `mix-blend-mode: difference` y está **por
   encima** de los rótulos: invierte píxel a píxel lo que cubre, así que en
   tema oscuro el bloque queda blanco con el rótulo negro y en tema claro al
   revés, y **durante el desplazamiento los dos rótulos siguen siendo
   legibles** (el que sale vuelve a su color, el que entra se invierte poco a
   poco). Con `--invert-bg` sólido + `color` por clase, el rótulo se invierte
   de golpe y se pierde.

**Coste medido** (con `PerformanceObserver` de tareas largas y muestreo de `rAF`):
al cambiar de fecha en el ámbito PRO (102 filas) **no hay ninguna tarea larga** y
solo **un frame de 54 ms**; en NORMAL (137 filas), **un frame de 67 ms**. El
resto del tiempo se mantiene a 60 fps. Si el número de filas creciera mucho, el
`animate:flip` es lo primero que habría que acotar.

#### 1.3.2 Resultados por fecha (`/fechas/[slug]/resultados`)

Isla Svelte 5 (`<StandingsTable client:visible />`):- **Selector de Pestaña Principal:**
  1. **Clasificación Individual:**
     - Selector de Categoría (`Elite`, `Master A`, `Damas`, etc.).
     - Buscador reactivo instantáneo por nombre, team o número de dorsal (`$derived`).
     - Columnas: `Puesto Actual`, `Cambio (▲ +N / ▼ -N / =)` con color semántico, `Ciclista`, `Team / Club` (o "Libre"), `Pts Fecha 1`, `Pts Fecha 2`, `Pts Fecha 3`, `Pts Fecha 4`, `Total Puntos` y `Tiempo Acumulado`.
  2. **Copa de Equipos (Clasificación por Teams):**
     - Buscador por nombre de Team.
     - Columnas: `Puesto`, `Cambio (▲ / ▼ / =)`, `Equipo`, `Puntos Acumulados`, `Oros (1°)` | `Platas (2°)` | `Bronces (3°)`, `Corredores Puntuadores` y `Tiempo Total`.
     - Clic en el nombre del Team navega a su ficha `/equipos/[slug]`.

### 1.4 Perfil Público del Ciclista (`/corredor/[slug]`)
> Ruta **dinámica en SSR**: perfil resuelto contra `GET /api/v1/riders/{slug}`. Sin mock: si el corredor no existe, la respuesta es `404`.
Accesible al hacer clic en cualquier corredor (sin requerir registro ni login):
- Ficha del ciclista: Nombre, DNI enmascarado (`***4567`), Team actual (con enlace a su equipo o indicador "Corredor Libre"), Categoría y Puesto en el Ranking General.
- Historial en las 4 fechas: Puesto en cada carrera, tiempo oficial en meta y en puntos intermedios, dorsal utilizado en cada fecha y puntos sumados.
- Tiempos en Segmentos de Strava asociados al corredor.

### 1.5 Perfil Público del Equipo (`/equipos/[slug]`)
> Ruta **dinámica en SSR**: perfil resuelto contra `GET /api/v1/teams/{slug}`. Sin mock: si el equipo no existe, la respuesta es `404`.
- Cabecera del Team: Nombre oficial, logo (Cloudflare R2), descripción y puesto en la Copa de Equipos.
- Estadísticas del Team: Puntos acumulados, total de victorias de categoría (medallas), cantidad de corredores activos.
- Plantilla de Corredores: Listado de todos los ciclistas que corrieron representando al Team en cualquiera de las fechas, con su categoría y los puntos aportados al equipo.

### 1.6 Inscripciones y Buzón de Reclamos (`/inscripciones` y `/reclamos`)
- **Pre-inscripciones (`/inscripciones`):**
  - Formulario público para la fecha activa:
    - `DNI`: Campo obligatorio con validación estricta (8 dígitos para DNI peruano o formato de extranjería).
    - Nombre completo, Género, Categoría, Team (autocompletado de equipos existentes o check "Corredor Libre / Sin Equipo").
  - Carga de Comprobante de Pago: Campo para adjuntar la captura/comprobante de Yape, Plin o transferencia bancaria, que se sube directamente a Cloudflare R2.
  - El registro se crea en `StageEntry` con `payment_status = PENDING` para revisión y aprobación con 1 clic por el administrador en el panel.
- **Buzón de Reclamos y Sugerencias (`/reclamos`):**
  - Formulario conectado a `FeedbackTicket` para reclamos de tiempos (con referencia a dorsal y DNI), observaciones de ruta o sugerencias técnicas.

---

## 2. Directrices de Implementación Visual y Assets

### 2.1 Fuente de Verdad para Estilos y Layout: `/home/edilsonc/Documents/copiaartcraft`
- Cualquier agente o desarrollador que construya páginas, cabeceras, pies de página o componentes visuales debe consultar obligatoriamente el clon en `/home/edilsonc/Documents/copiaartcraft`:
  - **Estilos globales:** Replicar y adaptar `tokens.css`, `motion.css`, `display.css` y `reset.css`.
  - **Componentes:** Adaptar `GhostWord.astro`, `DisplayTitle.astro`, `HeroWordmark.astro`, `SiteHeader.astro`, `SiteFooter.astro`, `PageRuler.astro` y la suite de `bento/`.
  - **Scroll Motion:** Adaptar las animaciones de revelado y fijación de `src/scripts/showcase-motion.ts` exclusivamente para la Home y presentaciones de fecha.

### 2.2 Generación de Imágenes con Nanobanana
- Para todos los recursos visuales del sitio (carteles de las 4 fechas, banners de patrocinadores, cabeceras de alta resolución, medallas y avatars):
  - Si el agente activo es Gemini, tiene la directriz de generarlas mediante la herramienta `generate_image` (**nanobanana** / Imagen 3).
