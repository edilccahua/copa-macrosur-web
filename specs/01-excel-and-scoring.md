# Spec 01: Motor de Excel Masivo, Parseo GPX y Cálculo de Rankings

> **Estado:** COMPLETADO ✅  
> **Fecha de Verificación:** 20 de Octubre de 2026  
> **Evidencia:** Tests unitarios `test_excel.py`, `test_pdf.py`, `test_scoring.py`, `test_seed_integrity.py` y `test_gpx.py` al 100% en verde (29 passed); soporte de importación con dry-run rollback 422, adapter legacy para históricos, exportación en 3 hojas, desempates UCI y olímpico de equipos.  
> **Corrección de integridad de datos (20-Oct-2026):** el parser de PDF descartaba silenciosamente el **26% de los resultados oficiales** de La Joya (52 de 198) por partirse en varias líneas. Ver §1.5.1 y §1.5.6.

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

### 1.5 Adapter Legacy para Formatos Históricos (`races/`)
Para procesar archivos históricos sin columnas DNI o género (Excel `LISTA` por bloques de categoría + PDF de resultados). Implementado en `excel_service.py`, `pdf_service.py` y `seed.py`.

1. **Detección de bloques:** la columna 1 `DORSAL` en la cabecera indica el bloque; la categoría activa va en la columna 4 (o en la cabecera del bloque). Filas con dorsal pero sin nombre se ignoran.
2. **Identidad Determinística:** `dni = SHA-256(normalize_name(nombre))[:8]` numérico. `normalize_name` quita diacríticos (`PEÑA→PENA`), puntuación y colapsa espacios, para que las variantes del mismo nombre compartan identidad entre fechas. `gender = F` si la categoría contiene `DAMAS`, si no `M`.
3. **Normalización de Equipos:** `"LIBRE"`, `"INDEPENDIENTE"`, `"TEAM"`, `"-"`, vacíos y `"NINGUNO"` → `team_id = NULL`.
4. **Parser de resultados PDF (`pdf_service.py`) tolerante a dos formatos del organizador:**
   - *La Joya* (columnas separadas por espacios) y *Z Xtreme* (celdas "pegadas": `3DIEGO…`, `…VARONES1:08:5210 1`). El renglón se reconoce con un patrón de dorsal + texto + tiempo `H:MM:SS`/`HH:MM:SS` + puntos + puesto, con la hora acotada a `00–23`.
   - **Reconstrucción de renglones partidos en varias líneas (obligatorio).** `pypdf` corta el renglón cuando el nombre o el club son largos y lo continúa en las líneas siguientes. El parser DEBE rearmar el renglón: `ROW_START_RE` localiza el dorsal que abre la fila y se concatenan las líneas siguientes hasta encontrar la cola `ROW_TAIL_RE` (tiempo + puntos + puesto) que lo cierra. Sin esta reconstrucción se perdían 52 de 198 resultados en La Joya (26%) y 155 puntos.
   - **Duplicados:** si un dorsal aparece más de una vez en el PDF, se conserva el **mejor tiempo** (menor `elapsed_ms`). Ej.: La Joya dorsal 161 → `01:31:15` (no `01:43:23`).
5. **Cruce Excel ↔ PDF consciente de nombre y categoría:** cuando el dorsal del Excel y del PDF están desalineados, el cruce prioriza: (1) dorsal con nombre y categoría coincidentes; (2) nombre más largo contenido en la fila del PDF y categoría coincidente; (3) inscrito **sin resultado** cuyo nombre coincide, adoptando la categoría del PDF (autoridad de resultados); (4) fallback por dorsal **solo si la categoría también coincide**. Ese cuarto paso cubre el caso `CHARLES GONZALES` (PDF) = `ANDRE GONZALES` (Excel) en el dorsal 11: mismo dorsal y misma categoría (ELITE), nombre con variante en el PDF oficial. Sin la condición de categoría, un resultado se traspasaría a un corredor de otra categoría (p.ej. dorsal 147 en Z Xtreme: `WENDY NINA CHIRE` / OPEN DAMAS en el PDF contra `ELMER EFRAIN MAMANI MAQUERA` / TURISMO OPEN en la lista de inscritos).
6. **Reconciliación PDF-only:** resultados cuyo dorsal no existe en la lista de inscritos (filas vacías en origen) se reconstruyen desde el PDF (nombre/equipo/categoría inferidos) para no perder tiempos. Si el corredor **ya tenía inscripción** en esa fecha con otro dorsal, se reutiliza esa inscripción (no se duplica) y se actualiza con los datos oficiales.
7. **Fusión de identidad por fecha:** un mismo `Rider` con varios `StageEntry` en una fecha se reduce a uno conservando el mejor tiempo (`merge_duplicate_entries`).
8. **Vueltas:** en circuitos por vueltas (Z Xtreme) cada `StageEntry.laps` se fija por categoría: `MASTER A/B/C, ELITE, E-BIKE = 3`; el resto `= 2`.

### 1.5.1 Autoridad del PDF Oficial y Reasignación de Dorsales

El PDF oficial de resultados es la **fuente de verdad** de cada fecha disputada:

| Dato | Autoridad | Regla |
| :--- | :--- | :--- |
| Tiempo en meta | PDF oficial | `finish_elapsed_ms` se toma literalmente del PDF. |
| Dorsal | PDF oficial | Si el dorsal publicado no coincide con el de la lista de inscritos, **manda el del PDF**. La reasignación se hace en dos fases (se liberan primero los dorsales de las inscripciones que se mueven con un valor temporal único y luego se aplican los nuevos) porque el PDF puede **permutar** dorsales: en Z Xtreme `JHOAN PAYHUA 40→140`, `ROLANDO PALOMO 140→166`, `ALESSANDRO VALDIVIA 11→167` y `JOSE CARLOS MAQUE MASCA 156→86`. |
| Categoría | PDF oficial | Si el PDF asigna otra categoría, se adopta la del PDF (p.ej. `ALESSANDRO VALDIVIA` figuraba como ELITE en el Excel y como TURISMO OPEN VARONES en el PDF). |
| Puesto | Recalculado | Ver §3.1: el puesto se recalcula por tiempo, no se copia del PDF. |
| Puntos | Recalculado | Ver §3.1: escala de 10 puntos sobre el puesto recalculado. |

**Dorsal liberado:** si el dorsal oficial de un corredor del PDF estaba asignado en la lista de inscritos a **otra persona sin resultado oficial**, el dorsal oficial se queda con su titular y la inscripción desplazada queda `DNS` con dorsal reservado (`0`, `-1`, …) para no perder la fila ni romper el `UniqueConstraint(stage_id, bib_number)`.

**Normalización de clubes partidos:** el PDF parte algunos clubes entre dos líneas (`CLUB ORIGINAL BIKES AREQUIPA-` / `PERÚ`). Sin normalizar, ese club se crearía **duplicado** del homónimo limpio y sus puntos se partirían en dos equipos. `collapse_team_hyphen()` colapsa el espacio alrededor del guion **solo cuando sigue una letra**, de modo que la categoría `JUVENILES 15 - 17` (guion seguido de dígito) no se ve afectada. `resolve_or_create_team()` aplica la misma normalización.

### 1.5.2 Reporte de Reconciliación de Puestos (obligatorio en el seed)

El PDF oficial del organizador tiene erratas punctuales en su columna `PUESTO` (puestos repetidos, saltados y un `1` en el lugar del 14º). Como el reglamento (ver §3.1) ordena por tiempo, el motor recalcula el puesto y el seed **imprime el contraste** para revisión del organizador:

- **La Joya Extreme:** 24 de 198 filas con `PUESTO` oficial distinto al recalculado (el PDF salta el puesto 39 en MASTER B, asigna `1` al 14º de TURISMO MASTER y sitúa al dorsal 144 en el 13º con un tiempo que lo situaría en el 3º).
- **Z Xtreme 2026:** 12 de 112 filas (el PDF repite el puesto 10 y salta el 21 en TURISMO OPEN, y salta el 6 en OPEN DAMAS).

La suma de puntos recalculada coincide con la del PDF oficial: **667 pts** en La Joya y **555 vs 554** en Z Xtreme (el +1 corresponde al puesto saltado en OPEN DAMAS). Si en el futuro la suma recalculada se desvía de la oficial, el seed lo delata.

### 1.5.3 Cifras Oficiales Verificadas (regresión)

Las cifras de abajo se verificaron con **dos oráculos independientes** (extracción por coordenadas con `pdfplumber` y `pdftotext -raw`) y están fijadas como aserciones en `backend/tests/test_pdf.py` y `backend/tests/test_seed_integrity.py`:

| PDF | Resultados oficiales | Puntos oficiales | Dorsales sólo en PDF |
| :--- | :--- | :--- | :--- |
| `1. LA JOYA EXTREME 2026  RESULTADOS.pdf` | **198** | **667** | 184, 185, 269, 270, 283 |
| `LA Z XTREME 2026 - RESULTADOS.-1.pdf` | **112** | **554** | 8, 106, 147 |

La carga final en la BD debe dejar **198** y **112** resultados con tiempo, **0** dorsales del PDF sin resultado, **0** resultados sin respaldo en el PDF, **0** tiempos discrepantes y **0** equipos duplicados.

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

> **El puesto se recalcula, no se copia del PDF.** La columna `PUESTO` del PDF oficial tiene erratas punctuales (puestos repetidos, saltados y un `1` en el 14º lugar). Copiarla tal cual rompería la continuidad de los puestos y la escala de puntos. El tiempo del PDF sí es la autoridad; el puesto es su consecuencia ordenando por tiempo. El contraste entre ambos queda documentado en el reporte del seed (§1.5.2).

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
5. **Limpieza de filas obsoletas:** tras recalcular, se eliminan las filas `ChampionshipStanding` de los pares `(rider_id, category_id)` que ya no tienen ningún resultado. Sin esta limpieza la tabla conserva corredores que dejaron de competir y el conteo de clasificaciones no cuadra con los resultados reales.

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
