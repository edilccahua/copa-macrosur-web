# Spec 00: Esquema de Dominio y Reglas de Campeonato (PostgreSQL + SQLModel)

> **Estado:** COMPLETADO ✅  
> **Fecha de Verificación:** 19 de Octubre de 2026  
> **Evidencia:** 15 entidades SQLModel en `backend/app/models/entities.py`, migración Alembic `head` (`b5d638d28e84` y `9f1a2b3c4d5e`), seed con 220 ciclistas, 230 inscripciones y reglas de negocio validadas al 100%.

## 1. Entidades Principales y Relaciones (ER)

### 1.1 `Team` (Clubes / Equipos de Ciclismo)
Representa a los equipos participantes en el campeonato.
- `id`: Serial (PK)
- `name`: String (Unique, Index, ej. `TEAM COLCA BIKE`, `CLUB ORIGINAL BIKES AREQUIPA-PERÚ`)
- `slug`: String (Unique, para URL pública `/equipos/colca-bike`)
- `logo_url`: String (Nullable, alojado en Cloudflare R2)
- `description`: String (Nullable)
- `is_active`: Boolean (Default `true`)
- *Nota:* Los ciclistas independientes o marcados como `LIBRE` no forman un equipo; en las relaciones su clave foránea será `NULL`.

### 1.2 `Rider` (Perfil Público del Ciclista)
Representa a la persona física a lo largo de todo el campeonato (sin login obligatorio en v1).
- `id`: UUID / Serial (PK)
- `dni`: String (Unique, Index, Obligatorio — Clave primaria de identidad deportiva entre fechas)
- `full_name`: String (Index)
- `slug`: String (Unique, para URL pública `/corredor/juan-perez-12`)
- `team_id`: FK -> `Team.id` (Nullable — `NULL` si corre como `LIBRE` / sin equipo)
- `birth_date`: Date (Nullable)
- `gender`: Enum (`M`, `F`)
- `strava_athlete_id`: String (Unique, Nullable — para cruce por OAuth o scraping local)
- `avatar_url`: String (Nullable, alojado en Cloudflare R2)

### 1.3 `Category` (Categorías Oficiales)
- `id`: Serial (PK)
- `name`: String (ej. `Elite Varones`, `Master A`, `Damas Open`, `E-Bike`)
- `short_code`: String (ej. `ELI-M`, `MSA`)
- `min_age`: Integer (Nullable), `max_age`: Integer (Nullable)
- `aliases`: JSONB (Default `[]` — lista de nombres alternativos para importación tolerante de Excel, ej. `["MASTER A", "MASTER A (30-39 AÑOS)", "MSA"]`)

### 1.4 `Stage` (Las 4 Fechas del Campeonato)
- `id`: Serial (PK)
- `stage_number`: Integer (1, 2, 3, 4 — Unique)
- `name`: String (ej. `Fecha 1: Rally Chachani`)
- `slug`: String (Unique)
- `date`: Date
- `status`: Enum (`UPCOMING`, `REGISTRATION_OPEN`, `LIVE`, `FINISHED`)
- `poster_url`: String (URL en Cloudflare R2)
- `gpx_file_url`: String (URL de descarga en R2)
- `route_geojson`: JSONB (Polilínea y perfil de elevación precalculado con `gpxpy` para pintar el mapa rápido sin recalcular)
- `distance_km`: Float
- `elevation_gain_m`: Integer
- `laps`: Integer (Default `1`). Vueltas del circuito. En circuitos por vueltas (ej. *Z Xtreme*) `distance_km` y `elevation_gain_m` son **POR VUELTA** y `laps` es el máximo (ej. 11.83 km/vuelta × 3 vueltas). En fechas de trayecto lineal `laps = 1`.
- `strava_route_url`: String (Nullable — enlace público a la ruta de Strava de la fecha)
- `gallery_r2_prefix`: String (Carpeta de fotos de la fecha en R2)
- `judge_pin`: String (Código o token de acceso rápido para los jueces de la fecha, ej. `KUS-F1-8421`). **Es una credencial interna y NUNCA se serializa en ninguna respuesta**: los endpoints de lectura devuelven `StagePublicRead`, que no declara este campo, y la garantía es el `response_model` de cada ruta (no un filtro a mano). Los PIN se siembran en la base de datos desde el entorno (`JUDGE_PIN_F1`…`JUDGE_PIN_F4`), **nunca desde el repositorio**. Ver `specs/03` §1.9.5.
- `live_closed_at`: DateTime (Nullable — cierre MANUAL de la transmisión de llegadas; `NULL` = abierta o nunca cerrada. La apertura es automática a las 08:00 de Lima el día de la carrera, ver `specs/02` §6)

### 1.5 `StartWave` (Mangas de Largada por Fecha)
Permite largadas escalonadas por grupos de categorías o individuales.
- `id`: Serial (PK)
- `stage_id`: FK -> `Stage.id`
- `name`: String (ej. `Manga 1: Elite + Master A`, `Manga 2: Turismo + Damas`, `Contrarreloj Individual`)
- `category_ids`: JSONB (Lista de IDs de categorías que largan en esta manga)
- `started_at_ms`: BigInt (Nullable — Timestamp epoch en ms cuando el juez da la largada)
- `is_individual`: Boolean (Default `false` — si es true, los corredores largan por separado)

### 1.6 `Checkpoint` (Puntos de Control por Fecha)
Define si una fecha tiene solo Partida/Meta o también puntos intermedios.
- `id`: Serial (PK)
- `stage_id`: FK -> `Stage.id`
- `name`: String (ej. `Partida`, `Control Intermedio Cumbre KM 14`, `Meta`)
- `order_index`: Integer (0 = Partida, 1..N = Intermedios, 99 = Meta)
- `distance_from_start_km`: Float
- `is_finish_line`: Boolean

### 1.7 `StageEntry` (Inscripción del Ciclista en una Fecha)
Une a un `Rider` con una `Stage` específica y su placa asignada en esa carrera.
- `id`: Serial (PK)
- `stage_id`: FK -> `Stage.id`
- `rider_id`: FK -> `Rider.id`
- `category_id`: FK -> `Category.id`
- `team_id`: FK -> `Team.id` (Nullable — equipo con el que corre esta fecha específica; `NULL` si es libre)
- `bib_number`: Integer (Número de placa en esa fecha; Unique por `[stage_id, bib_number]`)
- `payment_status`: Enum (`PENDING`, `PAID`, `FREE_GUEST`)
- `payment_voucher_url`: String (Nullable — imagen del comprobante Yape/Plin en Cloudflare R2)
- `race_status`: Enum (`REGISTERED`, `STARTED`, `FINISHED`, `DNF`, `DSQ`, `DNS`)
- `start_time_ms`: BigInt (Timestamp epoch en ms de la largada asignada por su StartWave o individual)
- `finish_elapsed_ms`: BigInt (Nullable — Tiempo neto oficial desde largada hasta meta en milisegundos)
- `category_rank`: Integer (Nullable — Puesto en su categoría en esta fecha)
- `overall_rank`: Integer (Nullable — Puesto en la general absoluta de esta fecha)
- `points_earned`: Integer (Default 0 — Puntos individuales ganados para el campeonato en esta fecha)
- `laps`: Integer (Default 1 — vueltas efectivamente completadas en fechas de circuito; p.ej. 3 en categorías fuertes, 2 en turismo/damas de *Z Xtreme*)
- **Restricción `UNIQUE(stage_id, bib_number)`:** el dorsal es único por fecha. La identidad del ciclista se garantiza por `Rider.dni`; si un mismo ciclista aparece con dos dorsales en la misma fecha (dato sucio de origen) se fusiona conservando el **mejor tiempo** (ver `specs/01 §1.5`).

### 1.8 `TimingEvent` (Marcaciones en Vivo del Juez)
Cada marcación del juez en su celular genera un registro aquí.
- `id`: UUID (PK — Generado en el cliente/celular en IndexedDB para evitar duplicados al sincronizar offline)
- `stage_entry_id`: FK -> `StageEntry.id`
- `checkpoint_id`: FK -> `Checkpoint.id`
- `recorded_at_ms`: BigInt (Timestamp calibrado del reloj del juez en ms)
- `elapsed_from_start_ms`: BigInt (Calculado: `recorded_at_ms - StageEntry.start_time_ms`)
- `recorded_by_admin`: String
- `is_verified`: Boolean (Default `true`)

### 1.9 `ChampionshipStanding` (Tabla Acumulada Individual por Categoría)
Almacena el estado del ranking individual acumulado. Clave compuesta por `[rider_id, category_id]` para garantizar que si un corredor es reclasificado de categoría, sus puntos no se mezclen.
- `id`: Serial (PK)
- `rider_id`: FK -> `Rider.id`
- `category_id`: FK -> `Category.id`
- `total_points`: Integer (Suma de `points_earned` de las fechas disputadas en esta categoría)
- `first_places_count`: Integer (Total de victorias de categoría acumuladas)
- `last_stage_rank`: Integer (Puesto obtenido en la última fecha disputada, usado para desempate)
- `total_elapsed_ms`: BigInt (Suma de tiempos netos de fechas completadas, usado para desempate final)
- `stages_completed`: Integer
- `current_rank`: Integer (Posición actual en el acumulado)
- `previous_rank`: Integer (Nullable — Posición antes de la última fecha disputada)
- `rank_delta`: Integer (Calculado: `previous_rank - current_rank`. Positivo = subió ▲, Negativo = bajó ▼, 0 = igual)

### 1.10 `TeamStageStanding` (Puntaje por Equipos en una Fecha)
- `id`: Serial (PK)
- `stage_id`: FK -> `Stage.id`
- `team_id`: FK -> `Team.id`
- `points_earned`: Integer (Suma de los puntos individuales aportados por todos los ciclistas del team en esa fecha)
- `first_places_count`: Integer (Cantidad de victorias de categoría del team en la fecha)
- `second_places_count`: Integer
- `riders_scored_count`: Integer (Total de ciclistas del team que sumaron puntos)
- `rank`: Integer (Puesto del equipo en la fecha)

### 1.11 `TeamChampionshipStanding` (Copa de Equipos Acumulada)
- `id`: Serial (PK)
- `team_id`: FK -> `Team.id`
- `total_points`: Integer (Suma de puntos acumulados en las 4 fechas)
- `first_places_count`: Integer (Total de oros acumulados)
- `second_places_count`: Integer (Total de platas acumuladas)
- `third_places_count`: Integer (Total de bronces acumulados)
- `total_riders_participations`: Integer (Total de corredores participantes del team)
- `total_elapsed_ms`: BigInt (Suma de tiempos netos para desempate final)
- `current_rank`: Integer (Posición actual en la Copa de Equipos)
- `previous_rank`: Integer (Nullable)
- `rank_delta`: Integer (`previous_rank - current_rank`)

### 1.12 `StravaSegment` y `StravaEffort` (Datos de Scraping Local CDP)
- **`StravaSegment`:** `id` (PK), `stage_id` (FK), `strava_segment_id` (String), `name`, `distance_m`, `average_grade`, `elevation_profile_json`.
- **`StravaEffort`:** `id` (PK), `segment_id` (FK), `rider_id` (FK, Nullable), `athlete_name_raw` (String extraído de Strava), `elapsed_time_sec` (Integer), `is_kom_qom` (Boolean).

### 1.13 `SpecialAward` (Premio Coca, Premio Montaña, Premios por Fecha)
- `id`: Serial (PK)
- `stage_id`: FK -> `Stage.id` (Nullable si es premio de todo el campeonato)
- `title`: String (ej. `Premio Especial Coca`, `Rey de la Montaña`, `Farolito / Más Persistente`)
- `sponsor_name`: String (Nullable)
- `sponsor_logo_url`: String (Nullable)
- `prize_description`: String (ej. `S/ 200 + Pack Hidratación`)
- `winner_rider_id`: FK -> `Rider.id` (Nullable hasta que se asigne)
- `metric_value`: String (ej. `14m 22s en Segmento Cumbre`)

### 1.14 `FeedbackTicket` (Sugerencias, Reclamos de Tiempos y Mejoras)
- `id`: Serial (PK)
- `stage_id`: FK -> `Stage.id` (Nullable)
- `type`: Enum (`TIMING_CLAIM`, `RACE_SUGGESTION`, `WEB_BUG`, `OTHER`)
- `submitted_by_name`: String
- `contact_whatsapp_or_email`: String
- `bib_number_ref`: Integer (Nullable)
- `message`: Text
- `status`: Enum (`OPEN`, `REVIEWED`, `RESOLVED`)
- `created_at`: DateTime

---

## 2. Reglas de Negocio y Consistencia

1. **Identidad Deportiva Inmutable:** El `Rider.dni` es el identificador único obligatorio. Los ciclistas se unifican entre fechas exclusivamente por su DNI.
2. **Unicidad de Dorsal por Fecha:** Los dorsales pertenecen a la carrera (`[stage_id, bib_number]`), NO al ciclista de por vida. En la Fecha 1 un corredor puede ser #15 y en la Fecha 2 ser #17.
3. **Aislamiento de Categoría:** Si un ciclista cambia de categoría entre fechas, sus puntos no se trasladan a la nueva categoría; se crea un registro `ChampionshipStanding` independiente para cada categoría disputada.
4. **Ciclistas Libres vs Teams:** La columna `TEAM` con valores `LIBRE`, `INDEPENDIENTE`, `-`, o celda vacía se mapea como `team_id = NULL`. Los puntos de corredores libres se contabilizan en el ranking individual pero no suman a ningún Team.
5. **Estadísticas de Extremos por Fecha:** Calculadas dinámicamente sobre `StageEntry` con `race_status == FINISHED`:
   - `fastest_overall`: `MIN(finish_elapsed_ms)`
   - `slowest_finisher`: `MAX(finish_elapsed_ms)`
6. **Idempotencia Offline-First:** El endpoint de marcaciones realiza `UPSERT` basado en el `UUID` generado en IndexedDB del teléfono; reenvíos automáticos por señal intermitente nunca duplican registros.
