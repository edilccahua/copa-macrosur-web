# Spec 03: Portal Público (Estilo GetArtCraft), Mapas GPX, Perfiles y Reclamos

> **Estado:** COMPLETADO ✅  
> **Fecha de Verificación:** 20 de Octubre de 2026  
> **Evidencia:** Build limpio con Astro 5 en modo **SSR** (`npm run build` + `node dist/server/entry.mjs`), `astro check` con **0 errores de tipos**, diseño editorial GetArtCraft adaptado de `copiaartcraft`, visor GPX interactivo SVG + altimetría y cero emojis en la UI.
> **20-Oct-2026:** `/ranking-general` se rediseña como clasificación acumulada "a la fecha" con grupos PRO / NORMAL / E-MTB, selector de fecha y de categoría reutilizables, control segmentado de pestañas, celda apilada en móvil y una sola identidad cromática por vista (el Δ usa colores semánticos). Ver §1.3.1.

## 0. Modo de Render: SSR (Server-Side Rendering) — decisión de integridad de datos

> **Cambio del 20 de Octubre de 2026.** El portal pasó de prerenderizado (SSG) a **SSR con adaptador Node** (`output: 'server'` + `@astrojs/node` en modo `standalone`).

### 0.0 Navegación de cliente (`astro:transitions`)

> **Añadido el 20 de Octubre de 2026.** El portal navega **de cliente**, en la
> **misma pestaña**, con un fundido corto. Antes cada clic recargaba la
> página entera: la barra volvía a animarse, el scroll suave se reiniciaba y
> la lectura se cortaba.

- `<ClientRouter />` se monta en `Base.astro` (todas las páginas).
- La cabecera lleva `transition:persist="site-header"`: **persiste** entre
  navegaciones, no se reconstruye y su animación de entrada ocurre **una
  sola vez por sesión**.
- El estado activo del menú **se calcula en el cliente** (`site-shell.ts`),
  porque el HTML del servidor no vuelve a pintarse. Usa **prefijos de
  ruta**, no el `href`: el fragmento (`/#fechas`) nunca está en el
  `pathname` y con `startsWith` sobre el href la pestaña "Fechas" no se
  activaba nunca.
- Eventos del router que gobiernan el movimiento:

  | Evento | Qué hace |
  | :--- | :--- |
  | `astro:before-preparation` | Destruye el movimiento de la página que sale (Lenis + ScrollTrigger) |
  | `astro:before-swap` | Calcula el item activo del menú con la ruta de destino |
  | `astro:after-swap` | Repone el tema (el `<html>` se reemplaza) y marca los elementos que quedan fuera de pantalla |
  | `astro:page-load` | Rearma el movimiento de la página nueva |

- El módulo de movimiento se carga con `import()` **dinámico**
  (`site-shell.ts` → `showcase-motion.ts`): `/en-vivo` y `/admin/juez` **no
  descargan GSAP ni Lenis** (AGENTS.md §2). Expone `init()` y `teardown()`.
- La entrada de la barra es una **animación CSS** (`hdr-item-in`), no de GSAP:
  el estado inicial vive en la hoja de estilos, así que no hay destello y no
  depende de que GSAP haya cargado. Al navegar, el router reinserta la
  cabecera y eso **reinicia las animaciones CSS del elemento**: por eso la
  clase `is-ready` desactiva la animación una vez terminada, para que la
  barra **no desaparezca y vuelva a entrar en cada clic**.
- **Transición de página:** cross-fade de 180 ms (`::view-transition-*`). Los
  elementos que ya están a la vista entran con el fundido; los que quedan
  por debajo del pliegue se ocultan (`.is-reveal-pending`) y se revelan al
  hacer scroll. En la primera carga los oculta `html.motion-ready`.
- **Morph del póster:** la tarjeta del timeline de la portada y el póster del
  hero de la ficha comparten `transition:name="poster-{slug}"`: al abrir la
  ficha, el póster se transforma en su sitio.
- Regresión automatizada: `frontend/tools/check-shell.mjs` (navegación de
  cliente, persistencia de la cabecera, estado activo, clicabilidad del CTA y
  del tema entre 768 y 1280 px) y `frontend/tools/detect-fouc.mjs` (destello
  del primer pintado).

### 0.0.1 Menú del sitio

Fuente única: `frontend/src/lib/nav.ts`. La barra, el cajón móvil y el pie se
derivan de ella (antes cada uno tenía su propia lista, con destinos que no
coincidían).

```
[ KÚSPIDE ] │ INICIO  FECHAS  CLASIFICACIONES  ESPECIALES  PREMIOS        │  [☀]
              ↑ marca (logo)                                    ↑ hueco    ↑ iconos
```

| Elemento | Decisión |
| :--- | :--- |
| `KÚSPIDE` | **Wordmark‑logo**, no un item de menú. Enlaza a la portada, pero **nunca se marca** |
| `INICIO` | La portada. Comparte destino con la marca, y es el que **se queda marcado** |
| `FECHAS` | `/#fechas` (la sección del calendario de la portada) |
| `CLASIFICACIONES` | `/ranking-general` (agrupa también `/corredor`, `/equipos`) |
| `ESPECIALES` | `/eventos-especiales` (las clásicas de ruta) |
| `PREMIOS` | `/premios` (página en blanco, lista para los `SpecialAward`) |
| `Campeonato` | **Fuera**: iba al mismo sitio que el logo (la incompatibilidad Kúspide/Campeonato) |
| `Reclamos` | Al **pie** (utilidad pública, no navegación principal) |
| `INSCRIPCIÓN` | **Fuera de la barra**: estaba duplicada y no es un destino de navegación. Se llega desde la portada y el pie |
| Panel del juez | **Cero enlaces públicos**. La URL la comparte el organizador |

**Geometría tomada de `getartcraft.com` (medida en vivo a 1600 px):**

| Medida | Valor |
| :--- | :--- |
| Barra | 48 px, `display:flex; justify-content:space-between`, full‑bleed |
| Marca | wordmark + separador vertical a la derecha |
| Items | `padding: 0 .75rem` · 0.6875rem mono · tracking 0.15em · versalitas |
| Pastilla | un `<span>` interior con `padding: .125rem .375rem` (medido en la referencia: chip de 45×21 px dentro de una celda de 65×48) |
| Activo | **pastilla invertida** sobre el texto (`--invert-bg` / `--invert-fg`) |
| Hover | **la misma pastilla invertida** (en la referencia es `group-hover:bg-invert` sobre el span) |
| Grupos | separación con `margin-left` + `border-left` + `padding-left` (13 px) |

**La pastilla va sobre el TEXTO, no sobre la celda.** Es el detalle que
distingue la referencia de una imitación: el fondo invertido está en un
`<span>` interior al enlace, no en el enlace. Por eso el item activo **no
ocupa todo su espacio** (21 px de alto dentro de una celda de 48) y por eso
el puntero puede mostrar **la misma pastilla** que el activo. Con el fondo en
el enlace entero, la pastilla llenaba la celda y el hover sólo podía ser un
cambio de color de la letra.

Entre dos pastillas quedan **24 px** (12 px de padding del enlace + 6 px de
pastilla a cada lado); la referencia deja 20 px.

El menú va **pegado a la marca, a la izquierda** (como la referencia): el hueco
grande queda a la derecha, entre el nav y las celdas de iconos. El nav de
escritorio aparece a partir de **900 px**; por debajo, el cajón.

**El ancla del menú la resuelve el shell, no el router.** El router de Astro
**no desplaza al fragmento** al navegar (verificado: la ruta cambia pero
`scrollY` se queda en 0) y llega a perder el `#`. Por eso los items con
ancla se interceptan en `site-shell.ts`:
- si ya se está en la página → `preventDefault` + desplazamiento suave con
  Lenis (`window.__kuspideScrollTo`, expuesto por el módulo de movimiento);
- si no → `navigate()` (la API del router) y, en `astro:page-load`, se
  desplaza al elemento.

### 0.0.1.1 Cajón de navegación (móvil)

- Va **superpuesto** al contenido (`position: fixed` + velo): abrirlo **no
  desplaza la página** y no produce salto de layout.
- Entra con un desplazamiento corto (`translateY(-10px)` + opacidad, 260 ms) y
  los items se **escalonan** (35 ms de retraso por item).
- **Dice en qué sección estás**: el indicador de la **barra** (no del cajón).
  En escritorio el nav ya lo dice; en móvil, donde el nav está oculto, una
  celda de la barra entre la marca y los iconos muestra **sólo el nombre de
  la sección** (`INICIO`, `FECHAS`, `CLASIFICACIONES`, `ESPECIALES`,
  `PREMIOS`), sin ninguna descripción. El cajón no lleva la línea
  "PÁGINA ACTUAL": ahí basta con que el item activo tenga la pastilla
  invertida y la barra de acento.
- Accesibilidad: al abrir, el foco entra en el cajón y queda **atrapado**
  (Tab cicla dentro); con Escape se cierra y el foco vuelve al botón; el
  velo cierra al tocarlo; se cierra solo al navegar o al pasar a escritorio.
- El scroll del cajón no se encadena con el de la página
  (`overscroll-behavior: contain`) y la rueda sobre el velo no desplaza la
  página por detrás.
- `prefers-reduced-motion` lo desactiva todo (regla global de `reset.css`).

**Regresión automatizada:** `frontend/tools/check-menu.mjs` (items exactos, sin
CTA ni enlaces al juez, menú pegado a la marca, item activo correcto en 7
rutas, la marca nunca marcada, el ancla de FECHAS desplazando, y en móvil: el
cajón superpuesto, sin salto de layout, con la página actual marcada y el
foco dentro) y `frontend/tools/check-shell.mjs`.

### 0.0.2 Capas: lo pegajoso NUNCA tapa la cabecera

La cabecera es `position: sticky; top: 0; z-index: 20`. Todo lo que también
sea pegajoso tiene que quedar **debajo** de ella:

| Elemento | Desplazamiento | z-index |
| :--- | :--- | :--- |
| Barra de sección (`SectionLabel`) | `var(--header-offset)` / `var(--header-offset-mobile)` | **19** (uno menos que la cabecera) |
| Cabecera de la tabla (`StandingsTable` `thead`) | `var(--header-offset)` | 10 |
| Regulador lateral (`PageRuler`) | `inset-block: 0` (altura completa) | 40 |
| Cajón móvil (`SiteHeader`) | `top: var(--header-offset-mobile)` | 2 (dentro de la cabecera) |

El regulador lateral va **en todas las páginas** (la de clasificaciones
incluida) y su banda es de **altura completa**, como en `copiaartcraft`:
el regulador y el menú forman un solo instrumento y no queda un hueco entre
la cabecera y la regleta. Para que la banda no se coma los clics del menú,
el regulador entero es `pointer-events: none` y sólo `.ruler__grab` —que
empieza bajo la cabecera— es agarrable.

Por lo mismo la barra de scroll nativa se oculta **sólo a partir de 48em**
(`.no-scrollbar` dentro de la media query): por debajo, la banda del
regulador no se dibuja y sin barra nativa el usuario se queda sin
indicación de scroll.

La regleta se inicializa desde `frontend/src/scripts/page-ruler.ts`, un
módulo **sin GSAP ni Lenis**: así puede estar en todas las páginas sin que
`/en-vivo` ni `/admin/juez` descarguen las librerías pesadas. Si la página
tiene Lenis, la regleta le pide el salto a `window.__kuspideLenis`.

Los tokens `--header-offset` y `--header-offset-mobile` son el **alto total** de
la cabecera (la barra **más** su hairline inferior), no sólo el alto de la
barra. Antes se usaba el alto de la barra y la barra de sección se colaba un
píxel por debajo del borde del menú, y en móvil (`top: 0`) **tapaba el menú
entero** de forma permanente.

Regla: **el z-index de un elemento pegajoso va por debajo del de la cabecera**
(20). Así, aunque el navegador recalcule el `sticky` a mitad de un scroll
—con el scroll suave de Lenis eso pasa— o el elemento pase por su posición
natural, el menú gana siempre.

Regresión: `frontend/tools/check-shell.mjs` comprueba, a 1280 px y a 390 px,
que la barra de sección se ancla por debajo de la cabecera (`top` ≥ alto real)
y que su z-index es menor que el de la cabecera.

### 0.0.4 Tema: conmutador, aviso de primera visita y transición

- **Área clicable = la celda entera.** El padding va en el elemento
  interactivo, no en la celda: así no hay que apuntarle al icono, basta con
  tocar el recuadro. Los tres controles de la derecha (WhatsApp, tema y
  burger) comparten el mismo tratamiento, lo que además enlarge el área
  táctil en móvil.
- **El tema del dispositivo se respeta**: si no hay preferencia guardada, se
  usa `prefers-color-scheme`. `data-theme` se escribe SIEMPRE (aunque venga
  del sistema), para que el icono del conmutador refleje el tema real.
- **Aviso de primera visita**: un globo anclado al botón del tema
  ("CAMBIA EL TEMA AQUÍ") que aparece **una sola vez** —queda marcado en
  `localStorage` (`kuspide-theme-hint`)— y se retira solo a los 4,5 s. No se
  cierra al hacer scroll: al cargar hay scrolls programáticos (Lenis,
  ScrollTrigger) y el aviso se iba sin que nadie lo hubiera visto.
  El globo va anclado al **borde derecho** del botón (el botón está en el
  extremo de la barra: centrado se salía de la pantalla) y su flecha cae
  sobre el icono.
- **Transición suave**: al cambiar de tema se pone `html.theme-switching`,
  que fuerza una interpolación de 420 ms de los colores de todo el
  documento (fondo, bordes, texto, `fill`/`stroke`, sombras) en vez de un
  salto. La clase se retira al terminar. Con `prefers-reduced-motion` el
  cambio es instantáneo.
- Regresión: `frontend/tools/check-theme.mjs` (área clicable, aviso de
  primera visita, que no vuelva a salir, transición suave, respeto del tema
  del dispositivo y cortes de la barra a 1280 y 390 px).

### 0.0.5 Puerta del panel del juez

- El PIN **no viaja en el código**: `/admin/juez` pide el PIN y lo valida
  contra `GET /api/v1/stages/{id}/judge-auth` (200/403; **nunca devuelve el
  PIN**).
- La **fecha se resuelve sola**: `LIVE` → siguiente con inscripciones
  abiertas → última disputada.
- El PIN **se guarda en el dispositivo** (`localStorage`) para el resto del
  campeonato; hay un botón `[ SALIR ]` que lo borra.
- El sitio público **no enlaza** a `/admin/juez` (ni en la barra, ni en el
  panel móvil, ni en el pie).
- La cola offline usa IndexedDB **sin el índice `synced`**: un booleano no
  es una clave válida de IndexedDB y el índice quedaba vacío por
  construcción (`IDBKeyRange.only(false)` lanzaba `DataError`).

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
- **El backend debe reiniciarse tras cambiar los modelos.** Un `uvicorn` sin `--reload` sigue sirviendo la versión anterior del esquema: la página lee `undefined` en los campos nuevos y, si tiene un mock de respaldo, muestra datos falsos en lugar de fallar. En desarrollo, `start.sh` lanza el backend con `--reload` y espera a que `/api/v1/stages` responda antes de levantar el frontend.
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

> **Rediseño del 20 de Octubre de 2026: la marca y el hero.** Antes el rótulo
> grande del hero, la cabecera y el pie decían "KÚSPIDE", que en los pósters
> oficiales de `races/info/` es el **organizador** (Kuspide Xtreme Sports), no
> el campeonato. El lockup de los pósters es **LA COPA MACROSUR MTB · EDICIÓN
> 2026 · KUSPIDE**. A partir de aquí el campeonato se llama "Copa MacroSur
> MTB" y "Kúspide" queda como el nombre del organizador.

**Identidad (fuente única: `frontend/src/data/site.ts`)**

| Constante | Valor | Dónde se usa |
| :--- | :--- | :--- |
| `SITE_NAME` | `Copa MacroSur MTB` | `<title>` de todas las páginas y textos legales |
| `SITE_TAGLINE` | `Edición 2026 · Kuspide Xtreme Sports` | pie de página |
| `BRAND_WORDMARK` | `COPA MACROSUR` | rótulo grande del hero |
| `BRAND_EDITION` | `EDICIÓN 2026` | línea superior del hero |
| `BRAND_NAV` | `KÚSPIDE` | **marca del menú principal (cabecera)** |

- La **cabecera** conserva "KÚSPIDE" a propósito: es el logo del organizador,
  igual que en los pósters. La cabecera no es un lugar para el nombre del
  campeonato.
- El **pie** lleva "COPA MACROSUR MTB" y el copyright "© 2026 Copa MacroSur MTB".
- `craftApps` (las cuatro fechas escritas a mano en `site.ts`) se **eliminó**:
  duplicaban la BD y por eso se quedaron desfasadas (decían 55.4 km y +920 m
  para La Joya cuando la ruta oficial son 40.85 km y +384 m). Se conserva el
  TIPO `CraftApp`, que necesita el componente portado `AppCard.astro`.

**Hero**

| Elemento | Escritorio | Móvil (< 48em) |
| :--- | :--- | :--- |
| Eyebrow | `[ EDICIÓN 2026 ]` | igual |
| Rótulo | `COPA MACROSUR` (una línea) | dos líneas (`COPA` / `MACROSUR`) |
| Titular | `Circuito oficial *de MTB.*` | igual |
| Bajada | 3 renglones | **1 renglón**: la segunda frase (cronometraje, clasificaciones, Copa de Equipos) se oculta; ya está en el pie |
| Índice de fechas | 4 nombres cortos en una línea | igual |

- El rótulo son **dos palabras**: `HeroWordmark` agrupa las letras por palabra
  (`wordmark__word`) y el espacio va en el `column-gap`. Con un `<span>` más
  para el espacio, el colapso de espacios en línea lo borraría y se leería
  "COPAMACROSUR".
- La bajada dice **Copa de Equipos**, no "Copa de Clubes": es como lo llama el
  resto del sitio y la BD.

**Banda de la próxima fecha (`hero__next`)**

- El nombre que se muestra es el **real** (`Stage.name` sin el prefijo
  "Fecha N:"), no el corto: "El Retorno a los Poblados 2", no "Poblados".
- La distancia y el desnivel son **POR VUELTA** en la BD (specs/01 §1.4): la
  banda multiplica por `Stage.laps` y, si hay varias vueltas, lo dice
  ("11.83 KM × 3 VUELTAS = 35.49 KM").
- **Móvil**: la banda se queda con lo esencial — la fecha, el nombre real, el
  cronómetro y los botones. Se ocultan el rótulo "[ PRÓXIMA FECHA ]"
  (`.next__label`) y la línea de datos (`.next__specs`), que a 390 px ocupaba
  dos renglones de monoespaciada.
- **Escritorio (≥ 68.75em)**: la fecha se apila ARRIBA del nombre, en la misma
  columna (`grid-template-areas`). Con la fecha en su propia columna el nombre
  real se partía en dos renglones y los datos en otros dos: cuatro renglones de
  ruido en una línea.

**Línea de tiempo (`TimelineEvents`)**

- Es un arreglo **literal** (a diferencia de las páginas de fecha, que leen
  todo de la API). Por eso sus cifras se contrastan con la BD:
  - **Fecha 1 (La Joya Extreme): 40.85 KM / +384 M.** Decía 55.4 KM y +920 M,
    que contradecían la BD, la ruta GPX y la propia ficha de la fecha.
  - **Fecha 2 (Kúspide Z Xtreme III):** 11.83 KM × 3 vueltas, +840 M (280 m por
    vuelta × 3).
  - **Clásica Arequipa-Mollendo:** 08:00 AM y "2 Etapas en Ruta" (los valores
    de `extra_events`; el póster no da hora ni kilómetros). Decía 07:30 AM y
    "125+ KM", que no aparecen en ningún sitio.
- El enlace de resultados de la Fecha 1 ya no lleva `categoria=ELI`: el
  parámetro se quitó de la ficha de fecha y el enlace iba desalineado.

**Grilla de las 4 Fechas:** 4 tarjetas Bento modulares mostrando el cartel oficial (generado con Nanobanana y alojado en Cloudflare R2), fecha, distancia (`km`), desnivel (`+m`) y estado (`Finalizada`, `Inscripciones Abiertas`, `Próximamente`).
- **Resumen del Ranking Acumulado:** Top 5 de cada categoría individual con enlace directo a `/ranking-general`.
- **Showcase Copa de Equipos:** Tarjeta Bento destacada con el **Team Líder del Campeonato** (logo, puntos y victorias) y podio de los 3 mejores equipos.
- **Showcase de Premios Especiales:** Cajas destacadas para premios de marca (ej. *Premio Especial Coca*, *Rey de la Montaña*).

### 1.1.1 La banda de la derecha: regulador + índice de secciones

> **Añadido el 20 de Octubre de 2026.** El borde derecho lo usan DOS elementos
> fijos: el regulador de scroll (`PageRuler`, 3.75rem) y las etiquetas del
> índice de secciones (`PageIndex`, alineadas a 5.5rem del borde y con ~7rem de
> ancho). Con solo 4.5rem de reserva en el `.container`, el contenido se metía
> debajo de las etiquetas: a 1280 px, "CLASIFICACIÓN" se montaba sobre el
> botón "Ficha de ruta" de la banda de la próxima fecha.

- Las páginas con índice de secciones llevan la clase `has-pageindex` en
  `<html>` (la pone `Showcase.astro` cuando hay `sections`).
- Con ella, entre 48em y 96em, el `.container` reserva `12.5rem` a la
  derecha. Por encima de 96em los 80rem del contenedor ya quedan centrados
  con margen de sobra y reservarlo sería tirar espacio.

### 1.2 Página de Fecha Individual (`/fechas/[slug]`)
> Ruta **dinámica en SSR**: el `slug` se resuelve contra la API en cada request. Si la fecha no existe, la respuesta es `404`; si el backend no responde, `503`. **La página no contiene ningún dato literal**: todo viene de `GET /api/v1/stages/{slug}/summary` (ver §1.4).
>
> **Rediseño del 19 de Octubre de 2026.** Antes la página tenía un espejo hardcodeado de las cuatro fechas (`stagesDb`) que servía de red de seguridad cuando el API fallaba. Eso ocultaba la caída del API (el `uvicorn` llevaba horas sirviendo un modelo viejo sin `title`/`short_name`/`start_location`, la página leía `undefined` y caía al mock) y mostraba cifras distintas de las de la BD (40.9 km en vez de 40.85). El mock se eliminó.

1. **Hero con datos reales:** póster oficial, nombre de la fecha sin el prefijo `Fecha N:`, fecha, punto de partida y hora, **distancia y desnivel por vuelta Y total** (`Stage.distance_km` y `Stage.elevation_gain_m` son **por vuelta**; el total es `× Stage.laps`), estado y sinopsis derivada de los datos. Botones a la tabla de resultados, al ranking acumulado y a la ruta de Strava.
2. **Navegación de campeonato ARRIBA del hero:** fecha anterior y siguiente (`navigation` del resumen) en dos bloques con flecha grande y nombre de la fecha; el hover desplaza la flecha 2 px. La cuenta regresiva aparece en las fechas con inscripción abierta y el badge `[ EN VIVO ]` cuando `Stage.status == LIVE`. La hora de largada se interpreta con su meridiem (`"02:30 PM"` son las 14:30, no las 02:30) mediante `frontend/src/lib/datetime.ts`.
3. **Cifras de la jornada** (`StageStatsRow`): inscritos, finalizados, no finalizados, puntos, velocidad del ganador (km/h) y número de categorías. Una fecha no disputada **no muestra ceros**: dice que las cifras están disponibles al cerrar la fecha. Los "no finalizados" son solo los abandonos de una fecha **ya disputada**: en una fecha con inscripción abierta, `REGISTERED` significa "aún no compite" y se rotula así.
4. **Leaderboard de podio por categoría** (`StageLeaderboard`): una fila por categoría con **solo el título de la categoría** (sin recuadro de código corto) y los tres ganadores con su club. **Sin dorsal, sin tiempo y sin puntos**: el detalle completo está en el ranking, en modo FECHA (`/ranking-general?modo=fecha&tabla=PRO&fecha={n}`). El título **no va en blanco como el resto del texto**: usa la tipografía display en mayúsculas y el acento de su grupo (`PRO` / `NORMAL` / `E-MTB`, tokens `.scope-*` de `tokens.css`), de modo que se lee de un vistazo a qué categoría pertenece cada bloque; al pasar el ratón el título toma el color vivo del grupo. El puesto es `StageEntry.category_rank`, ya calculado por el motor de scoring: **el PDF oficial manda** (specs/01 §1.5.2).
   - **El puesto se dibuja con una MEDALLA, no con un número.** Es la insignia de leaderboard de Strava (`icon-at-pr-01/02/03`), reproducida con su geometría exacta: silueta de "bolsillo" con la cinta y el puesto **calado al vacío** dentro del disco (`fill-rule="evenodd"`). La pieza vive en `src/assets/medals/medal-N.svg` (canónica, `currentColor`) y en `public/icons/medals/medal-N.svg` (plana, para reutilizar fuera de Astro); la genera `frontend/tools/build-medals.mjs`. El "2" y el "3" son los trazados literales de Strava; el "1" está dibujado con la misma construcción. Los tonos (`--medal-1/2/3`) son el oro, la plata y el bronce exactos de Strava. El componente `MedalIcon.astro` la inserta **en línea** (no como `<img>`) para que herede el color del tema y para que el número calado deje ver el fondo real de la página.
5. **Podio de clubes de la fecha** (`StageTeamCard`): adaptación de la `AppCard` de `copiaartcraft` — recuadro de iniciales, **medalla del lugar** (en lugar del índice numérico), nombre, línea de contexto, estado con los puntos, etiquetas de medallas (oros, platas, bronces) y enlace a la ficha del club. El acento lo da el lugar en el podio (oro, plata, bronce). Los puntos son los **sumados en esa jornada**, no el acumulado del campeonato. Un club partido por salto de línea en el PDF se fusiona en uno solo (INTEGRIDAD-DATOS.md §2.2, caso 3).
6. **Estadísticas extremas de la fecha:** tarjeta **Scratch** (tiempo mínimo) y tarjeta **Farolito** (tiempo máximo). Cada una se renderiza con su propia guardia: una fecha puede tener un extremo y no el otro.
7. **Perfil de etapa** (`StageProfile.astro` + `backend/scripts/build_stage_profile.py`):
   - El perfil **no se dibuja en el navegador**: lo genera un script de Python
     como SVG con la tipografía del sistema (Geist Mono para las cifras, Archivo
     para los rótulos) y se sirve desde `/profiles/{slug}.svg`. Lleva la
     silueta real de `Stage.route_geojson`, la retícula de altitudes en msnm, los
     **puertos** con su categoría (HC/1/2/3/4) y su nombre, los **checkpoints**
     etiquetados y la banda de kilometraje.
   - **La escala vertical se DECLARA** (`ESCALA VERTICAL ×19`): un perfil de
     etapa estira la vertical, y un lector de mapas necesita saber cuánto. Se
     calcula de la geometría, no se elige a ojo.
   - El **desnivel** que se muestra es el **acumulado real** (359 m en La Joya),
     no la diferencia entre el máximo y el mínimo (648 m): un vaivén no es un
     desnivel.
   - Las pendientes se miden sobre la altitud **suavizada** (media móvil de 3
     puntos): la geometría se guarda simplificada a 500 puntos y esa
     simplificación inflaba un tramo de 70 m hasta el 53% de pendiente.
   - Si la geometría es de **una vuelta** de un circuito por vueltas, se avisa
     debajo del gráfico.
   - Al lado van las cifras de la jornada y la lista de puertos e hitos.
8. **Segmentos Strava de la fecha:** los segmentos de la **ruta oficial** de Strava (25 en total entre las tres fechas), con tres reglas de selección (`backend/app/services/strava_selection.py`):
   1. **Filtro por fecha de medición.** Strava lista en un mismo segmento los intentos de muchas fechas (2019, 2023, 2024 y el de la carrera). Solo cuenta el intento medido en la fecha de la carrera (±1 día). La fecha del intento se guarda en `strava_efforts.measured_on`.
   2. **Cruce con los pilotos.** Solo cuenta el intento de un corredor inscrito en esa fecha. El cruce usa `strava_athlete_id` (fiable) y, como respaldo, el nombre normalizado.
   3. **Selección.** Se descarta el segmento que cubre ≥80% de la etapa —**es la ruta, no un tramo**— y se muestran los **cinco** más relevantes: primero las subidas y bajadas más empinadas, luego los más largos.

   Cada segmento muestra su distancia, pendiente, lugar, altitud y **Top 5** de tiempos, más el enlace al segmento en Strava. Encima, dos tarjetas: el **King of the Mountain** (la subida más empinada) y la **Queen of the Mountain** (la bajada más empinada), con el corredor más rápido de cada tramo.
9. **La E-MTB no compite por el título de la fecha.** El E-BIKE OPEN conserva su propio leaderboard de categoría, pero un e-bike no puede ser el scratch ni el KOM/QOM de la jornada.
10. **El ganador es el de mayor VELOCIDAD**, no el de menor tiempo: en un circuito por vueltas no todos completan lo mismo, y el tiempo más bajo puede ser el de quien dio menos vueltas. En Z Xtreme el scratch pasa de SERGIO PINEDA (2 vueltas, 23.7 km/h) a RONALD LUZA (3 vueltas, 26.7 km/h).
11. **Premios de la jornada:** título, patrocinador, descripción del premio y **ganador** resuelto desde `SpecialAward.winner_rider_id`. El logotipo del patrocinador sale de `sponsor_logo_url`.
12. **Numeración de secciones:** consecutiva y sin huecos. Los bloques que no aplican a una fecha (sin podio, sin equipos, sin Strava, sin premios) se omiten enteros.

**Fuera de alcance (documentado, no implementado):** la galería fotográfica de Cloudflare R2 con lightbox queda pendiente: `Stage.gallery_r2_prefix` es `NULL` en las cuatro fechas y no hay endpoint que la sirva. Requiere primero sembrar las fotos en el bucket.

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
3. **Selector de CATEGORÍA (el único dropdown "casi escondido"):** dentro de la
   pestaña activa ofrece **TODOS** (agrupa las categorías de esa pestaña) o una
   categoría concreta, que aísla su clasificación. Es el **mismo componente**
   (`ScopeControl.svelte`) en toda la tabla: lista desplazable, mono 11px en
   mayúsculas y el elemento activo invertido en el color del grupo. El panel va
   con `z-index: 50` y sombra profunda para leerse por encima de los badges de
   la tabla, y su **foco usa el color del grupo activo** (`--scope-ink`), nunca
   el azul por defecto del navegador.
   **La fecha NO se elige con un dropdown**: la elige el navegador de fechas del
   Tour (item 13). El dropdown `ACUMULADO HASTA` se eliminó por ser una línea
   interminable en la cabecera y por duplicar ese navegador.
4. **Barra de controles:** el buscador **ocupa el espacio disponible**
   (`flex: 1 1 14rem`, hasta `24rem`) junto a los selectores; no es una caja
   mínima. En móvil los dos selectores van en una fila de dos columnas
   (`1fr 1fr`) y el buscador al 100% debajo: ~80px menos de alto.
5. **Tabla:** Puesto · Δ · Ciclista · Categoría · En cat. · Equipo / Club ·
   Tiempo Acum. · Diferencia · Puntos. Todas las columnas numéricas declaran
   `font-variant-numeric: tabular-nums`.
6. **Color: uno por vista.** Solo el grupo activo tiene color (`.scope-*` →
   `--scope` / `--scope-ink`): la cinta, la celda activa de la pestaña, la ficha
   del podio y el velo del líder. Las etiquetas de categoría son monocromas.
7. **El Δ usa colores SEMÁNTICOS**, no el color del grupo: `▲` verde
   (`--status-up`), `▼` rojo (`--status-down`), `=` a α .45 (`--status-flat`),
   en tema claro y oscuro. Informa de ranking, no de estilo.
8. **Podio.** El podio se marca en la caja del puesto: **1 oro · 2 plata · 3 bronce**
   (`--podium-1/2/3`), **insignia SÓLIDA** con texto oscuro encima (`--podium-fg`):
   los tres primeros tienen que verse de un vistazo, también en móvil y con los
   tonos apagados de una tabla con mucha información. Además, borde izquierdo de
   `3px` en la fila (`inset box-shadow`) con el metal correspondiente.
   **Ninguna fila tiene estado persistente**: el 1º NO lleva velo (una fila
   teñida parecía una selección) y el único realce es el **hover** (velo del 5%
   del color del grupo). Nada de fichas con iniciales: eran ruido de plantilla
   y obligaban a reservar un hueco para alinear los nombres.
9. **Hover discreto:** velo del 5% del color del grupo al pasar el ratón. Es un
    paso de ratón, no un estado de la fila.
10. **Ejes de columna:** sin fichas ni huecos reservados, los nombres caen
    solos en el mismo eje X. El club es la columna que respira
    (`width: 30%; min-width: 180px`, sin recorte): "CLUB ORIGINAL BIKES…" ya no
    se corta cuando sobra espacio en pantalla.
11. **Diferencia:** la brecha de tiempo acumulado respecto al líder de la
    clasificación (ordenada por puntos). **Puede ser negativa** si un corredor
    con menos puntos acumula menos tiempo; la cabecera y esas celdas llevan un
    `title` que lo explica.
12. **Modos FECHA | ACUMULADO (pestaña SUPERIOR, fuera de la caja).**
    Es un control de **VISTA**, no un filtro: por eso no se parece al
    segmentado de pestañas de abajo (pastilla invertida) sino a una **barra de
    pestañas** al estilo Tour de Francia: rótulo **grande** (14px / 800 / 0.1em),
    el activo en tinta con una **raya de 3px del color del grupo**
    (`--scope-ink`) que se posa sobre el borde superior de la caja (la pestaña
    queda unida al panel) y el inactivo en apagado. Vive **encima de la caja**,
    entre el título y la cinta.
    - **ACUMULADO** (por defecto): la suma de todo lo disputado hasta el corte,
      con la columna **Δ**.
    - **FECHA**: **solo esa carrera** (sus puntos y su tiempo). Sin Δ (una carrera
      aislada no tiene clasificación previa con la que compararse) y con
      `TIEMPO` en vez de `TIEMPO ACUM.`.
    - El rótulo de la página cambia con el modo: *Ranking general acumulado* ⇄
      *Clasificación de la fecha* (la isla ajusta `data-mode-title` /
      `data-mode-word`). La cinta cambia: `2 FECHAS DISPUTADAS · 76.34 KM · CORTE
      23 AGO. 2026` ⇄ `FECHA 2 · 35.49 KM · 23 AGO. 2026`.
13. **Un solo selector de fecha, el del Tour.** Encima de las pestañas de modo
    está el **navegador de fechas** (`‹ FECHA 2 · 23 AGO. 2026 · KÚSPIDE Z
    XXTREME III ›`, flechas circulares), y **está siempre visible**: en
    `ACUMULADO` marca el corte (`HASTA FECHA 2`) y en `FECHA` la carrera que se
    está viendo (`FECHA 2`). El dropdown `ACUMULADO HASTA` **se eliminó**: dos
    selectores de fecha hacían lo mismo y el segundo era una línea interminable.
    Es el control más importante de la cabecera, así que va **grande**: la flecha
    en un círculo de `2.25rem` (que se llena con el color del grupo al pasar el
    ratón), el número de fecha a `18px/800` y la fecha y el nombre de la carrera
    a `12px`.
14. **Cifras de lo que se está viendo**, entre las pestañas de modo y la caja:
    `PARTICIPANTES` · `FINALIZARON` · `NO FINALIZARON` · `TIEMPO MEDIO`.
    - En **FECHA** son las de esa carrera; en **ACUMULADO**, las de la ventana
      completa y con **corredores distintos** (quien hizo dos fechas cuenta
      una vez).
    - Van por **ámbito**: al cambiar a NORMAL cambian, igual que la tabla.
    - El **tiempo medio** es la media de los tiempos de los que cerraron.
      **Mezcla categorías** (un ELITE a 1:08 y un MASTER D a 1:50): es un dato
      de contexto, no un récord, y el tooltip lo explica. El tiempo del ganador
      está en la tabla, en la primera fila.
15. **La cabecera de la vista no lleva enlaces.** Ni podio, ni exportar, ni
    nada más junto al selector de fechas: la cabecera dice qué se está viendo
    (el modo, la fecha y su descripción) y la tabla dice los datos. Los enlaces
    de la cabecera compiten con el título y con el nombre de la carrera y los
    hacía ilegibles.
16. **La tabla recibe argumentos.** `StandingsTable` acepta `initialMode`
    (`acumulado` | `fecha`), `initialScope`, `initialCategoryId`,
    `initialStageId` e `initialKind` (`individual` | `teams`).
    `/ranking-general` además lee los query params y los pasa como props:
    `?modo=acumulado|fecha` · `?tabla=PRO|NORMAL|E-MTB|EQUIPO` ·
    `?categoria=ELI` (short_code) · `?fecha=2` (número de fecha).
    Tras una interacción, la vista se escribe en la URL con `replaceState`
    (compartible, sin llenar el historial). Por defecto: **ACUMULADO + PRO + TODOS**.
17. **No hay página de resultados por evento.** `/fechas/[slug]/resultados` se
    eliminó: la clasificación oficial de una carrera **es el ranking en modo
    FECHA**. Todos los enlaces que apuntaban a ella (el botón de la ficha de la
    carrera, la timeline de eventos y el pie de página) apuntan ahora al ranking
    con los argumentos:
    `/ranking-general?modo=fecha&tabla=PRO&categoria=ELI&fecha=<n>`.
    En la ficha de la carrera hay **una sola** opción para ver los resultados
    (`Ver Resultados →`, que lleva a la fecha de esa carrera en el ranking): el
    botón *Ranking Acumulado* se quitó para no ofrecer dos puertas al mismo
    sitio.
18. **Móvil (<48em) — celda apilada de 3 columnas**
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
19. **Ancho:** la página usa un contenedor de `108rem` (no el de `80rem` de las
    demás): una clasificación es una tabla densa y debe aprovechar la pantalla.

**Endpoint:** `GET /api/v1/public/standings?mode=&stage=&scope=&category_id=&kind=`
devuelve `{rows, context}`; `context` lleva las fechas disponibles, los grupos
con sus categorías, el catálogo de categorías y los metadatos de cabecera.

- `mode=acumulado` (por defecto): `stage` es el **CORTE** (se suma todo lo
  disputado hasta ahí) y la DELTA compara contra la fecha anterior.
- `mode=fecha`: `stage` es la **CARRERA exacta**: solo cuentan sus puntos y su
  tiempo, y la DELTA va vacía (no hay clasificación previa). En la cinta,
  `stages_counted` es 1 y la distancia es la de esa carrera.
- `context.stats`: las cifras de lo que se está viendo (`participants`,
  `finishers`, `non_finishers`, `avg_time_ms`), calculadas en el mismo ámbito
  y con la misma categoría que la tabla.

Es el equivalente a GENERAL / CLASIFICACIÓN DE PASO del Tour de Francia.

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
4. **La estructura de la tabla solo cambia con los datos.** El `animate:flip`
   de las filas deja los elementos en `position: absolute` mientras dura; si una
   actualización lo interrumpe, las filas quedan **pegadas y amontonadas**
   (visible: dos filas superpuestas). Por eso el componente distingue el modo
   **pedido** (`mode`, el de la pestaña activa) del modo **dibujado**
   (`tableMode`): el segundo cambia en el mismo update que traen los datos, de
   modo que la estructura (columna Δ, navegador de fechas, cinta) y las filas
   cambian juntos y el `flip` nunca se interrumpe. Cualquier cambio de layout
   entre la petición y la respuesta es un bug esperando.

**Coste medido** (con `PerformanceObserver` de tareas largas y muestreo de `rAF`):
al cambiar de fecha en el ámbito PRO (102 filas) **no hay ninguna tarea larga** y
solo **un frame de 54 ms**; en NORMAL (137 filas), **un frame de 67 ms**. El
resto del tiempo se mantiene a 60 fps. Si el número de filas creciera mucho, el
`animate:flip` es lo primero que habría que acotar.

#### 1.3.2 Resultados por fecha (ranking en modo FECHA)

> La ruta `/fechas/[slug]/resultados` ya no existe (ver §1.3 regla 17): la
> clasificación oficial de una carrera es el **ranking en modo FECHA**
> (`/ranking-general?modo=fecha&tabla=PRO&fecha=<n>`), que es la misma isla
> con el corte por fecha en lugar del acumulado.

Isla Svelte 5 (`<StandingsTable client:visible />`):- **Selector de Pestaña Principal:**
  1. **Clasificación Individual:**
     - Selector de Categoría (`Elite`, `Master A`, `Damas`, etc.).
     - Buscador reactivo instantáneo por nombre, team o número de dorsal (`$derived`).
     - Columnas: `Puesto Actual`, `Cambio (▲ +N / ▼ -N / =)` con color semántico, `Ciclista`, `Team / Club` (o "Libre"), `Pts Fecha 1`, `Pts Fecha 2`, `Pts Fecha 3`, `Pts Fecha 4`, `Total Puntos` y `Tiempo Acumulado`.
  2. **Copa de Equipos (Clasificación por Teams):**
     - Buscador por nombre de Team.
     - Columnas: `Puesto`, `Cambio (▲ / ▼ / =)`, `Equipo`, `Puntos Acumulados`, `Oros (1°)` | `Platas (2°)` | `Bronces (3°)`, `Corredores Puntuadores` y `Tiempo Total`.
     - Clic en el nombre del Team navega a su ficha `/equipos/[slug]`.

### 1.4 Endpoint de presentación de una fecha (`GET /api/v1/stages/{slug}/summary`)

> **Añadido el 19 de Octubre de 2026.** La ficha de una fecha necesita muchos
> agregados que ningún endpoint cubría (cifras de jornada, podio por categoría,
> podio de equipos, checkpoints). Calcularlos en el servidor evita que la
> página los recalcule y garantiza que la ficha y la tabla de resultados
> muestran los mismos números.

**Servicio:** `backend/app/services/stage_summary_service.py` (seis funciones de
agregado, sin acceso a disco ni a la red) + `backend/app/routers/stages.py`.

| Función | Devuelve |
| :--- | :--- |
| `compute_stage_stats(session, stage_id)` | `StageStatsRead`: inscritos, finalizados, no finalizados, puntos, distancia y desnivel **por vuelta y total**, vueltas, tiempo y velocidad del ganador, nº de categorías. La velocidad usa las vueltas que el ganador **completó** (`StageEntry.laps`), no el máximo de la fecha: en un circuito por vueltas no todos dan el mismo número de vueltas. |
| `compute_category_podium(session, stage_id)` | `List[CategoryPodiumRead]`: top-3 por categoría con `PodiumEntryRead` (puesto, dorsal, nombre, slug, club, tiempo formateado, puntos). |
| `compute_stage_team_podium(session, stage_id)` | `List[TeamPodiumRead]`: los 3 equipos con más puntos **de esa jornada**, con corredores puntuadores (los que suman puntos) y mejor puesto. Un club partido por salto de línea se fusiona con su forma completa. |
| `compute_stage_strava(session, stage_id)` | `List[StravaSegmentSummaryRead]`: segmentos con distancia, pendiente, **top 10** de efforts, el `kom` y su `kind` (CLIMB / DESCENT / FLAT), su lugar y sus altitudes. El `kom` es `null` si ningún effort está marcado como tal: no se inventa un récord oficial. Los esfuerzos de todos los segmentos se cargan en una sola consulta. |
| `compute_stage_checkpoints(session, stage_id)` | `List[CheckpointRead]`: Partida, intermedios y Meta, en orden. |
| `compute_stage_awards(session, stage_id)` | `List[AwardSummaryRead]`: premios con patrocinador, descripción y ganador resuelto. |
| `compute_stage_route_profile(session, stage)` | `RouteProfileRead`: el perfil de altimetría con su traza punto a punto, el desnivel **acumulado** real, la pendiente media y máxima, y si la geometría cubre la etapa entera o solo una vuelta. `null` si la fecha no tiene geometría. |
| `compute_stage_summits(session, stage_id)` | `List[SummitRead]`: las cimas de la ruta (los "puertos" del perfil) con su nombre real, su categoría de puerto y sus cifras. |
| `compute_stage_mountain_titles(session, stage_id)` | El **King of the Mountain** (la subida más empinada) y la **Queen of the Mountain** (la bajada más empinada) de la fecha, con el corredor más rápido de cada tramo. `null` si la fecha no tiene segmentos. |

**Respuesta:** `{stage, stats, podium, teams, strava, checkpoints, awards, extremes, route_profile, summits, kom, qom, navigation}`.
`extremes` tiene siempre las claves `scratch` y `farolito`, que pueden ser `null`.
`route_profile` y `kom`/`qom` pueden ser `null` (fecha sin geometría o sin segmentos).
`navigation` trae `prev_slug`/`prev_name` y `next_slug`/`next_name`.
Si la fecha no existe: `404` con `{"detail": "Etapa no encontrada."}`.

**Datos de mapa y de puertos:**
- `StravaSegment` lleva `location`, `elevation_min_m`, `elevation_max_m`, `kind` y `category`. Los segmentos son los de la **ruta oficial** de Strava de cada fecha (25 en total entre las tres fechas) y se sincronizan con `backend/scripts/sync_all_strava_segments.py` (CDP sobre la sesión Strava del administrador; nunca en la nube).
- `StravaEffort` lleva **`measured_on`** (la fecha del intento) y **`strava_athlete_id`**. Sin la fecha no se puede distinguir un intento de la carrera de otro de 2019: Strava lista en un mismo segmento los de muchas fechas, todos juntos.
- `RouteSummit` guarda las cimas de la ruta con su nombre real. El nombre sale del **reverse-geocode de OpenStreetMap (Nominatim)** sobre la coordenada de la cima y se resuelve **al sembrar**, nunca en cada request: la red no está en el camino de una página.
- La categoría de puerto sigue las reglas del Tour: **HC** (≥1000 m y ≥8%), **1** (≥700 m y ≥6%), **2** (≥400 m y ≥4%), **3** (≥200 m y ≥3%), **4** (≥100 m y ≥2%).
- El perfil de etapa se **genera como imagen**: `backend/scripts/build_stage_profile.py` escribe `/profiles/{slug}.svg`. Se regenera cuando cambia la geometría o las cimas.

**Tests:** `backend/tests/test_route_profile.py` (8 tests) y `backend/tests/test_stage_summary.py` (32 tests) fijan las cifras
oficiales (225 inscripciones / 198 con tiempo / 667 puntos en La Joya), el
perfil real (359 m de desnivel acumulado, no 648 m de span; pendiente máxima
53% tras suavizar) y los casos límite: fecha no disputada, circuito por vueltas
(la velocidad usa las vueltas realmente completadas), extremos independientes,
club partido por salto de línea (se fusiona y suma sus puntos), colecciones
vacías, velocidad del ganador, abandono vs. "aún no compite", riders
puntuadores, medallas del club, ausencia de KOM marcado, perfil sin geometría
y cimas de categoría.

### 1.5 Perfil Público del Ciclista (`/corredor/[slug]`)
> Ruta **dinámica en SSR**: perfil resuelto contra `GET /api/v1/riders/{slug}`. Sin mock: si el corredor no existe, la respuesta es `404`.
Accesible al hacer clic en cualquier corredor (sin requerir registro ni login):
- Ficha del ciclista: Nombre, DNI enmascarado (`***4567`), Team actual (con enlace a su equipo o indicador "Corredor Libre"), Categoría y Puesto en el Ranking General.
- Historial en las 4 fechas: Puesto en cada carrera, tiempo oficial en meta y en puntos intermedios, dorsal utilizado en cada fecha y puntos sumados.
- Tiempos en Segmentos de Strava asociados al corredor.

### 1.6 Perfil Público del Equipo (`/equipos/[slug]`)
> Ruta **dinámica en SSR**: perfil resuelto contra `GET /api/v1/teams/{slug}`. Sin mock: si el equipo no existe, la respuesta es `404`.
- Cabecera del Team: Nombre oficial, logo (Cloudflare R2), descripción y puesto en la Copa de Equipos.
- Estadísticas del Team: Puntos acumulados, total de victorias de categoría (medallas), cantidad de corredores activos.
- Plantilla de Corredores: Listado de todos los ciclistas que corrieron representando al Team en cualquiera de las fechas, con su categoría y los puntos aportados al equipo.

### 1.7 Página de Premios (`/premios`)

- Página de presentación de los premios de la edición (premio de montaña,
  premios por etapa, distintivos de la organización).
- **Estado actual (20-Oct-2026): en blanco.** La estructura (título, bajada
  y rótulo de sección) está montada y lista para llenarse con los
  `SpecialAward` de la base de datos; el texto de "[ EN PREPARACIÓN ]"
  desaparece cuando se publiquen.

### 1.8 Inscripciones y Buzón de Reclamos (`/inscripciones` y `/reclamos`)
- **Pre-inscripciones (`/inscripciones`):**
  - Formulario público para la fecha activa:
    - `DNI`: Campo obligatorio con validación estricta (8 dígitos para DNI peruano o formato de extranjería).
    - Nombre completo, Género, Categoría, Team (autocompletado de equipos existentes o check "Corredor Libre / Sin Equipo").
  - Carga de Comprobante de Pago: Campo para adjuntar la captura/comprobante de Yape, Plin o transferencia bancaria, que se sube directamente a Cloudflare R2.
    > **20 de Octubre de 2026: se quitó el número de cuenta inventado.** La
    > página decía "Abonos al número oficial de la organización: 958 123 456
    > (Yape / Plin a nombre de Kúspide MTB)". Ese número **no está en los
    > pósters oficiales ni en la BD**: estaba escrito a mano. En una página de
    > pago, un dato inventado es el peor tipo de dato. Ahora el texto pide
    > confirmar la cuenta o celular que indique la organización y da los dos
    > WhatsApp oficiales: **994 382 248** y **980 081 335**.
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
