# Spec 03: Portal Público (Estilo GetArtCraft), Mapas GPX, Perfiles y Reclamos

## 1. Mapa de Rutas Públicas (Astro Frontend)

### 1.1 Portada del Campeonato (`/`)
Diseño Bento Grid modular oscuro (estilo GetArtCraft consumiendo los estilos y layout de referencia):
- **Hero Box:** Cuenta regresiva para la próxima fecha (o indicador rojo parpadeante `EN VIVO AHORA` con enlace directo a `/en-vivo` si `Stage.status == LIVE`), más botón destacado de Pre-Inscripción.
- **Grilla de las 4 Fechas:** 4 tarjetas Bento modulares mostrando el cartel oficial (generado con Nanobanana y alojado en Cloudflare R2), fecha, distancia (`km`), desnivel (`+m`) y estado (`Finalizada`, `Inscripciones Abiertas`, `Próximamente`).
- **Resumen del Ranking Acumulado:** Top 5 de cada categoría individual con enlace directo a `/ranking-general`.
- **Showcase Copa de Equipos:** Tarjeta Bento destacada con el **Team Líder del Campeonato** (logo, puntos y victorias) y podio de los 3 mejores equipos.
- **Showcase de Premios Especiales:** Cajas destacadas para premios de marca (ej. *Premio Especial Coca*, *Rey de la Montaña*).

### 1.2 Página de Fecha Individual (`/fechas/[slug]`)
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
Isla Svelte 5 (`<StandingsTable client:visible />`):
- **Selector de Pestaña Principal:**
  1. **Clasificación Individual:**
     - Selector de Categoría (`Elite`, `Master A`, `Damas`, etc.).
     - Buscador reactivo instantáneo por nombre, team o número de dorsal (`$derived`).
     - Columnas: `Puesto Actual`, `Cambio (▲ +N / ▼ -N / =)` con color semántico, `Ciclista`, `Team / Club` (o "Libre"), `Pts Fecha 1`, `Pts Fecha 2`, `Pts Fecha 3`, `Pts Fecha 4`, `Total Puntos` y `Tiempo Acumulado`.
  2. **Copa de Equipos (Clasificación por Teams):**
     - Buscador por nombre de Team.
     - Columnas: `Puesto`, `Cambio (▲ / ▼ / =)`, `Equipo`, `Puntos Acumulados`, `Oros (1°)` | `Platas (2°)` | `Bronces (3°)`, `Corredores Puntuadores` y `Tiempo Total`.
     - Clic en el nombre del Team navega a su ficha `/equipos/[slug]`.

### 1.4 Perfil Público del Ciclista (`/corredor/[slug]`)
Accesible al hacer clic en cualquier corredor (sin requerir registro ni login):
- Ficha del ciclista: Nombre, DNI enmascarado (`***4567`), Team actual (con enlace a su equipo o indicador "Corredor Libre"), Categoría y Puesto en el Ranking General.
- Historial en las 4 fechas: Puesto en cada carrera, tiempo oficial en meta y en puntos intermedios, dorsal utilizado en cada fecha y puntos sumados.
- Tiempos en Segmentos de Strava asociados al corredor.

### 1.5 Perfil Público del Equipo (`/equipos/[slug]`)
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
