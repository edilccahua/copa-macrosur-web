# Spec 01: Motor de Excel Masivo, Parseo GPX y Cálculo de Rankings

## 1. Importación y Exportación de Participantes/Resultados (Excel)

### 1.1 Estructura Requerida de Columnas (`.xlsx`)
El endpoint de importación procesa archivos `.xlsx` leyendo la primera hoja o la hoja `Inscritos` / `LISTA`:

- **Columnas Requeridas:**
  `DNI` | `NOMBRE_COMPLETO` (o `NOMBRE`) | `GENERO` | `TEAM` (o `CLUB`) | `CATEGORIA` | `DORSAL` | `TIEMPO_OFICIAL` (opcional si es pre-carrera) | `ESTADO_PAGO` (opcional)

- **Regla Estricta de DNI:**
  - El campo `DNI` es **obligatorio** en cada fila para garantizar la identidad única del ciclista entre las 4 fechas.
  - Si una fila tiene `DNI` vacío o no numérico/inválido, el proceso aborta con error HTTP `422`.
  - *Nota para datasets históricos de prueba (como `races/`):* Se provee un script auxiliar de migración/enriquecimiento que inyecta DNIs sintéticos basados en hash determinístico del nombre para poblar los datos de desarrollo.

### 1.2 Normalización de Equipos y Categorías
- **Normalización de Team:**
  - Si el campo `TEAM` contiene `"LIBRE"`, `"INDEPENDIENTE"`, `"-"`, o está vacío, se asigna `team_id = NULL`.
  - Si contiene un nombre (ej. `"TEAM COLCA BIKE"`, `"CLUB ORIGINAL BIKES AREQUIPA-PERÚ"`), se busca por coincidencia exacta o slug; si no existe, se crea automáticamente en la tabla `Team`.
- **Mapeo de Categoría:**
  - El sistema resuelve la categoría comparando el texto contra `Category.name`, `Category.short_code` y la lista de `Category.aliases` (ej. `"MASTER A (30-39 AÑOS)"` mapea a `MASTER A`).

### 1.3 Endpoint de Importación: `POST /api/v1/stages/{stage_id}/import-excel`
- **Comportamiento Transaccional (Dry-Run implícito):**
  1. Lee el archivo en memoria con `openpyxl` (`data_only=True`).
  2. Valida todas las filas:
     - `DNI` presente y válido.
     - Que no haya `DORSAL` duplicado dentro de la misma fecha.
     - Que la categoría sea resoluble.
  3. **Si hay al menos 1 error crítico:** Rollback total sin escribir en BD; devuelve HTTP `422` con array de `{row, field, error, raw_value}` para que el organizador lo corrija.
  4. **Si hay 0 errores:**
     - `UPSERT` en `Rider` usando el `dni` como clave única.
     - Actualiza `Rider.team_id` y crea el registro `StageEntry` vinculado a `stage_id` con su `bib_number` y `team_id` de esa fecha.
     - Si la fila incluye tiempo (`TIEMPO_OFICIAL` o `T. TOTAL`), se convierte a milisegundos enteros (`finish_elapsed_ms`), se marca `race_status = FINISHED` y se dispara el recálculo de rankings individual y por equipos.

### 1.4 Endpoint de Exportación: `GET /api/v1/stages/{stage_id}/export-excel`
Genera en memoria (`io.BytesIO`) un libro `.xlsx` con 3 hojas:
1. `Resultados_Fecha`: Corredores ordenados por categoría y puesto, con tiempo (`HH:MM:SS.mmm`), Team y puntos ganados.
2. `Ranking_Acumulado_Individual`: Tabla general de todas las categorías con puntos acumulados de las 4 fechas y columna `DELTA` (`▲ +2`, `▼ -1`, `=`).
3. `Ranking_Equipos`: Clasificación acumulada de la Copa de Equipos con puntos, victorias (oros/platas/bronces) y total de ciclistas participantes.

---

## 2. Procesamiento Automático de Ruta GPX: `POST /api/v1/stages/{stage_id}/upload-gpx`
Al subir el archivo `.gpx`:
1. Sube el archivo original a Cloudflare R2 para descarga pública directa (`gpx_file_url`).
2. Procesa en memoria con `gpxpy` y calcula:
   - `distance_km`: Distancia 3D/2D total en kilómetros (redondeado a 2 decimales).
   - `elevation_gain_m`: Desnivel positivo acumulado en metros.
   - `route_geojson`: Muestreo simplificado a un máximo de 500 puntos `[lat, lon, ele, dist_km]` para renderizado instantáneo en móviles (mapa y gráfico de altimetría).

---

## 3. Motor Matemático de Puntuación y Rankings

### 3.1 Escala Oficial de Puntos Individuales (10 Puntos)
Al procesar resultados de una categoría en una fecha:
1. Se ordenan los ciclistas con `race_status == FINISHED` por `finish_elapsed_ms ASC`.
2. Asignación de puntos según la escala oficial del campeonato:
   - **1° lugar:** `10 pts`
   - **2° lugar:** `9 pts`
   - **3° lugar:** `8 pts`
   - **4° lugar:** `7 pts`
   - **5° lugar:** `6 pts`
   - **6° lugar:** `5 pts`
   - **7° lugar:** `4 pts`
   - **8° lugar:** `3 pts`
   - **9° lugar:** `2 pts`
   - **10° lugar:** `1 pt`
   - **11° en adelante:** `1 pt` (Premio a la persistencia por completar la prueba).
   - Corredores con estado `DNF` (No terminó), `DNS` (No largó) o `DSQ` (Descalificado): `0 pts`.

### 3.2 Recálculo del Ranking Acumulado Individual (`ChampionshipStanding`)
1. **Snapshots:** Copia `current_rank` previo en `previous_rank`.
2. **Suma:** Suma `points_earned` y `finish_elapsed_ms` de todas las fechas corridas en esa categoría.
3. **Criterios de Desempate Individual (Reglamento UCI):**
   1. Mayor cantidad de puntos acumulados (`total_points DESC`).
   2. Mayor cantidad de 1ros puestos / victorias de categoría (`first_places_count DESC`).
   3. Mejor puesto obtenido en la **última fecha disputada** (`last_stage_rank ASC`).
   4. Menor tiempo acumulado en las fechas completadas (`total_elapsed_ms ASC`).
4. **Flechas de Posición (`rank_delta`):**
   - Si no tenía ranking anterior (debutante o Fecha 1): `rank_delta = 0`.
   - Si ya figuraba: `rank_delta = previous_rank - current_rank`.

### 3.3 Recálculo de la Clasificación por Equipos (`TeamChampionshipStanding`)
1. **Puntaje por Fecha (`TeamStageStanding`):**
   - Por cada `Team` con ciclistas en carrera: suma **todos los puntos individuales** obtenidos por sus corredores en todas las categorías en esa fecha (`points_earned`).
   - Ciclistas `LIBRE` o sin club no aportan a ningún equipo.
2. **Copa de Equipos Acumulada (`TeamChampionshipStanding`):**
   - Suma los puntos de las 4 fechas.
   - Cuenta el total de primeros puestos (medallas de oro), segundos puestos (platas) y terceros puestos (bronces) obtenidos por corredores del equipo.
3. **Criterio de Desempate Olímpico de Equipos:**
   1. Mayor cantidad de puntos totales del equipo (`total_points DESC`).
   2. Mayor cantidad de 1ros lugares / victorias de categoría (`first_places_count DESC`).
   3. Mayor cantidad de 2dos lugares (`second_places_count DESC`).
   4. Mayor cantidad de 3ros lugares (`third_places_count DESC`).
   5. Mayor cantidad total de ciclistas participantes que puntuaron (`total_riders_participations DESC`).
   6. Menor tiempo neto acumulado de sus corredores (`total_elapsed_ms ASC`).
