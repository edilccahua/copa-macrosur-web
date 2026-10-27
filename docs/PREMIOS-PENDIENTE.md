# Premios — la escala de la edición 2026

> **Fecha:** 26 de octubre de 2026
> **Estado:** la escala está **en la BD** (`prize_tiers`, con su `group_key`)
> y la API la publica en `GET /api/v1/public/prizes`.
> **Alcance:** portada (`/#premios`) y página `/premios`

---

## 1. Regla de la edición 2026

| Ámbito | Agrupación | Puestos | Monto / Tipo | Se paga a |
| :--- | :--- | :--- | :--- | :--- |
| **Acumulado del campeonato** | `PRO` | 1º / 2º / 3º | **USD 300 / 200 / 100** | El podio de la agrupación **PRO** |
| **Acumulado del campeonato** | `NORMAL` | 1º / 2º / 3º | **USD 300 / 200 / 100** | El podio de la agrupación **NORMAL** |
| **Acumulado de equipos** | `EQUIPOS` | 1º / 2º / 3º | **USD 500 / 400 / 300** | El podio de la **Copa de Equipos** acumulada |
| **Cada fecha (ELITE)** | `ELITE` | 1º / 2º / 3º | **USD 70** / **Regalo/Presente** / **Regalo/Presente** | Podio de la categoría **ELITE** en cada fecha |
| **Cada fecha (Demás categorías)** | — | 1º / 2º / 3º | **USD 50** / **Regalo/Presente** / **Regalo/Presente** | Podio de **cada una de las demás categorías** en cada fecha |

Aclaraciones que la UI deja explícitas:

- El acumulado **no es por categoría**: es al que más puntos suma dentro de PRO y dentro de NORMAL.
- El premio por fecha **no es una bolsa común de NORMAL**: hay un podio por categoría (11 por fecha).
- En cada fecha, el 1er lugar cobra en efectivo (**USD 70** en Elite y **USD 50** en las demás categorías), mientras que el 2do y 3er puesto reciben regalos / presentes para el ciclista o bicicleta.
- El premio de equipos es **su propia escala** (500 / 400 / 300): el podio de clubes se paga con un presupuesto propio, no reparte el de los corredores.

---

## 2. Cómo está en la BD

`prize_tiers` tiene **15 filas** y una columna `group_key` que dice a qué
agrupación pertenece cada una:

| scope | group_key | position | amount_usd | label |
| :--- | :--- | :--- | :--- | :--- |
| `FECHA` | `ELITE` | 1 | 70 | 1er puesto Elite |
| `FECHA` | `ELITE` | 2 | 0 | 2do puesto Elite (Regalo / Presente) |
| `FECHA` | `ELITE` | 3 | 0 | 3er puesto Elite (Regalo / Presente) |
| `FECHA` | `NULL` | 1 | 50 | 1er puesto de cada categoría |
| `FECHA` | `NULL` | 2 | 0 | 2do puesto de cada categoría (Regalo / Presente) |
| `FECHA` | `NULL` | 3 | 0 | 3er puesto de cada categoría (Regalo / Presente) |
| `ACUMULADO` | `PRO` | 1 | 300 | Campeón del acumulado PRO |
| `ACUMULADO` | `PRO` | 2 | 200 | Subcampeón del acumulado PRO |
| `ACUMULADO` | `PRO` | 3 | 100 | Tercer puesto del acumulado PRO |
| `ACUMULADO` | `NORMAL` | 1 | 300 | Campeón del acumulado NORMAL |
| `ACUMULADO` | `NORMAL` | 2 | 200 | Subcampeón del acumulado NORMAL |
| `ACUMULADO` | `NORMAL` | 3 | 100 | Tercer puesto del acumulado NORMAL |
| `ACUMULADO` | `EQUIPOS` | 1 | 500 | Campeón de la Copa de Equipos |
| `ACUMULADO` | `EQUIPOS` | 2 | 400 | Subcampeón de la Copa de Equipos |
| `ACUMULADO` | `EQUIPOS` | 3 | 300 | Tercer puesto de la Copa de Equipos |

La clave de una fila es `(scope, group_key, position)`.

---

## 3. El seed es un UPSERT

`seed_prize_tiers` **no se va** si la tabla ya tiene filas: hace upsert por
`(scope, group_key, position)` y borra las filas que ya no están en la
escala. Antes (y durante varias ediciones) la escala cambió y la BD se
quedaba con la vieja para siempre, porque el seed se iba en cuanto
encontraba una fila.

Consecuencia práctica: cambiar un monto es cambiar una línea de la
`escala` en `backend/app/seed.py` y volver a sembrar. No hay migraciones
de datos que escribir a mano.

`backend/tests/test_prize_scale.py` blinda que:

1. la escala sembrada es la de la edición 2026,
2. repetir el seed no duplica nada,
3. una escala vieja (70/50/30 y el acumulado por categoría) se corrige,
4. la API publica el `group_key`.

---

## 4. El frontend todavía tiene su copia

`frontend/src/data/prizes.ts` es la copia de lectura del frontend: la
página `/premios` y la portada leen de ahí, no escriben cifras sueltas en el
marcado. **Las dos copias tienen que decir lo mismo** (la de la BD y la del
frontend). Cuando la página lo lea todo de la API, este módulo se borra.

---

## 5. Lo que se decidió y no está en el código

Nada pendiente de monto: la escala vigente es la de §1 y está en la BD.

Queda una cosa de **texto**: el rótulo de cada fila (`label`) es lo que
publica la API. Si el organizador prefiere otra redacción, se cambia en
`backend/app/seed.py` y se vuelve a sembrar.
