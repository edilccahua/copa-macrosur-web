# Premios — esquema objetivo y deuda de BD

> **Fecha:** 20 de octubre de 2026
> **Estado:** UI implementada · **BD sin modificar (pendiente por decisión del organizador)**
> **Alcance:** portada (`/#premios`) y página `/premios`

---

## 1. Regla de la edición 2026

| Ámbito | Puestos | Monto | Se paga a |
| :--- | :--- | :--- | :--- |
| **Acumulado del campeonato** | 1º / 2º / 3º | **USD 300 / 200 / 100** | Podio de la agrupación **PRO** y podio de la agrupación **NORMAL** |
| **Cada fecha** | 1º / 2º / 3º | **USD 100 / 50 / 30** | Podio de **cada una de las 11 categorías**, en cada una de las 4 fechas |

Aclaraciones que la UI deja explícitas:

- El acumulado **no es por categoría**: es al que más puntos suma dentro de PRO y dentro de NORMAL.
- El premio por fecha **no es una bolsa común de NORMAL**: hay un podio por categoría (11 por fecha).

---

## 2. Qué hay hoy en la base de datos

`prize_tiers` (6 filas):

| scope | position | amount_usd | label |
| :--- | :--- | :--- | :--- |
| `FECHA` | 1 | 70 | 1er puesto de cada categoría |
| `FECHA` | 2 | 50 | 2do puesto de cada categoría |
| `FECHA` | 3 | 30 | 3er puesto de cada categoría |
| `ACUMULADO` | 1 | 300 | Campeón de cada categoría |
| `ACUMULADO` | 2 | 200 | Subcampeón de cada categoría |
| `ACUMULADO` | 3 | 100 | Tercer puesto de cada categoría |

Discrepancias con el esquema objetivo:

1. **Por fecha:** la BD dice 70 USD para el 1º; el organizador fijó **100 USD**.
2. **Acumulado:** la BD lo define **por categoría**; el organizador lo definió **por agrupación** (PRO y NORMAL). Hacen falta 6 filas (2 agrupaciones × 3 puestos), no 3.

---

## 3. Mientras la BD no se toque

La escala vive en **`frontend/src/data/prizes.ts`** y es la única fuente para la portada y `/premios`:

- `ACCUMULATED_PRIZES` → PRO y NORMAL, 300/200/100.
- `PER_DATE_PRIZES` → 100/50/30.
- `PRIZE_CATEGORIES` → las 11 categorías oficiales.

No se agregaron montos literales en el marcado de las páginas.

---

## 3.1 Premio CLARO y títulos de montaña (20-Oct-2026)

Esto **sí se actualizó en la BD** (no es la escala de `prize_tiers`):

- `special_awards` ya no tiene el Premio Coca ni el KOM de USD 150.
- La fila de prueba es **Premio CLARO** (`USD 100`), con el logo de Claro en
  `frontend/public/images/sponsors/claro.svg` y el ganador provisional en
  `winner_rider_id`. Es un premio **ACUMULADO**: `stage_id = NULL`, se entrega
  al cerrar las cuatro fechas y **no aparece en la ficha de una fecha**.
- El criterio es la **remontada**: haber terminado todas las fechas y subir
  más puestos en su categoría entre la primera y la última. Se recalcula en
  `GET /api/v1/public/remontada` y se guarda una instantánea en la BD.
- KOM, QOM, El Kamikaze y La Kamikaze se muestran en la ficha de cada fecha y
  en `/premios` a **USD 15 cada uno**, con un solo ganador por título. Sus
  ganadores salen de Strava (`compute_stage_mountain_titles`), no de
  `special_awards`.

El logo de Claro es un recurso **de prueba**: para publicarlo hace falta la
autorización del patrocinador y, si corresponde, sustituirlo por el manual de
marca oficial.

---

## 4. Migración propuesta (cuando se autorice)

### 4.1 Modelo

Añadir a `PrizeTier` una columna nullable `group_key` (`PRO` / `NORMAL`; `NULL` en `FECHA`):

```python
group_key: Optional[str] = Field(default=None, index=True)
```

Permite distinguir los dos podios acumulados sin duplicar `position` de forma ambigua.

### 4.2 Datos

| scope | group_key | position | amount_usd |
| :--- | :--- | :--- | :--- |
| `FECHA` | `NULL` | 1 | 100 |
| `FECHA` | `NULL` | 2 | 50 |
| `FECHA` | `NULL` | 3 | 30 |
| `ACUMULADO` | `PRO` | 1 | 300 |
| `ACUMULADO` | `PRO` | 2 | 200 |
| `ACUMULADO` | `PRO` | 3 | 100 |
| `ACUMULADO` | `NORMAL` | 1 | 300 |
| `ACUMULADO` | `NORMAL` | 2 | 200 |
| `ACUMULADO` | `NORMAL` | 3 | 100 |

### 4.3 Seed idempotente

`backend/app/seed.py::seed_prize_tiers` hoy retorna si encuentra **cualquier** fila, así que no actualiza una BD existente. Debe pasar a **upsert** por `(scope, group_key, position)` y eliminar las filas obsoletas.

### 4.4 API y frontend

- `PrizeTierRead` y `GET /api/v1/public/prizes` exponen `group_key`.
- `frontend/src/lib/api.ts` añade `group_key` al tipo `PrizeTier`.
- `frontend/src/data/prizes.ts` se sustituye por la lectura de la API (misma forma de datos).
- `/premios` y la portada no cambian de estructura: solo la fuente.

### 4.5 Especificaciones

- `specs/00-domain-schema.md`: documentar `PrizeTier.group_key`.
- `specs/03-public-portal-and-gpx.md` §1.7: ya refleja el esquema objetivo; al migrar, quitar la nota de “BD pendiente”.

---

## 5. Verificación al migrar

1. `alembic upgrade head`.
2. `python -m backend.app.seed` dos veces (idempotencia).
3. `GET /api/v1/public/prizes` devuelve 9 filas con `group_key` correcto.
4. `pytest backend/tests -q`.
5. Comparar la escala visible en `/` y `/premios` contra la tabla de §1.
