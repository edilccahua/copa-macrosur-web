# Auditoría de Integridad de Datos — Campeonato MTB Kúspide

> **Fecha:** 20 de Octubre de 2026
> **Alcance:** resultados e inscripciones de las fechas disputadas (Fecha 1 *La Joya Extreme* y Fecha 2 *Z Xtreme 2026*) frente a los PDF oficiales de `races/`.
> **Estado:** ✅ **CORREGIDO Y VERIFICADO**
> **Especificaciones afectadas:** `specs/01-excel-and-scoring.md` (§1.5, §1.5.1, §1.5.2, §1.5.3, §3.1, §3.2), `specs/03-public-portal-and-gpx.md` (§0), `PLAN.md` (§1.1, §1.2, Gate 2, Gate 6, Gate 8).

---

## 1. Motivo

El usuario éché un contraste entre los PDF oficiales de `races/` y los resultados publicados en el portal: **no coincidían**. Este documento deja constancia del hallazgo, de la causa, de la corrección y de la verificación.

---

## 2. Diagnóstico

### 2.1 Causa raíz principal — el parser de PDF descartaba renglones partidos

`backend/app/services/pdf_service.py` reconocía el renglón con un regex anclado a **una sola línea**:

```
^(\d{1,4})\s*(.*?)\s*(H:MM:SS)\s*(\d{1,3})\s+(\d{1,3})\s*$
```

`pypdf` extrae el PDF de La Joya **partiendo el renglón** cuando el nombre o el club son largos:

```
11 CHARLES GONZALES CLUB ORIGINAL BIKES AREQUIPA-
PERÚ ELITE 01:10:43 9 2
```

La segunda línea no matchea el ancla `^…$`, así que el renglón se descartaba con un `continue` **sin log ni aviso**.

| Métrica | Antes | Correcto | Pérdida |
| :--- | :--- | :--- | :--- |
| Resultados La Joya cargados | 146 | **198** | **52 (26%)** |
| Puntos La Joya | 594 | **667** | **155** |
| Resultados Z Xtreme cargados | 112 | 112 | 0 |

La pérdida de 155 puntos se concentraba en `CLUB ORIGINAL BIKES AREQUIPA-PERÚ` (−69) y `TEAM COLCA BIKE` (−22), es decir, **la Copa de Equipos estaba mal** además del ranking individual.

### 2.2 Causas secundarias

| # | Hallazgo | Consecuencia |
|---|---|---|
| 1 | El dorsal del PDF oficial no se aplicaba a la inscripción (la lista de inscritos manda) | 4 dorsales de Z Xtreme mostraban el número de la lista en vez del oficial (`140` en vez de `166`, etc.). Además el PDF **permuta** dorsales, así que un cambio secuencial choca con el `UniqueConstraint(stage_id, bib_number)`. |
| 2 | El fallback "por dorsal" no exigía categoría coincidente | El resultado de `WENDY NINA CHIRE` (dorsal 147, OPEN DAMAS) se traspasaba a `ELMER EFRAIN MAMANI MAQUERA` (dorsal 147, TURISMO OPEN) y el 6º lugar real de OPEN DAMAS desaparecía. |
| 3 | Club partido por el salto de línea (`AREQUIPA-` / `PERÚ`) | Se creaba un **equipo duplicado** del homónimo limpio y sus puntos se partían en dos equipos. |
| 4 | `reconcile_pdf_only_results` creaba una inscripción nueva en vez de reutilizar la existente | La fusión posterior de identidades eliminaba la inscripción con el dorsal oficial. |
| 5 | `recalculate_championship_standings` solo actualizaba, nunca eliminaba | Filas de clasificaciones de corredores que ya no competían (250 filas para 248 pares reales). |
| 6 | `/fechas/[slug]/resultados` era **prerenderizada** con un `fetch` de build-time dentro de un `try/catch` vacío | Si el backend no estaba arriba al buildear, la página se horneaba **vacía sin aviso**. Los `getStaticPaths` tenían slugs hardcodeados y los perfiles servían mocks con nombres reales y DNI ficticio. |

---

## 3. Correcciones

### 3.1 Backend

| Archivo | Cambio |
|---|---|
| `backend/app/services/pdf_service.py` | Parser de dos fases: `ROW_START_RE` abre el renglón con el dorsal, se concatenan las líneas siguientes y `ROW_TAIL_RE` (tiempo + puntos + puesto, hora acotada a 00–23) lo cierra. Añadido `collapse_team_hyphen()` para el club partido. |
| `backend/app/seed.py` | `cross_pdf_results` devuelve además los dorsales oficiales aplicados y reasigna en dos fases (liberar con valor temporal → aplicar). `reconcile_pdf_only_results` reutiliza la inscripción existente y libera el dorsal oficial si lo tenía otra inscripción sin resultado (esa queda `DNS` con dorsal reservado). Nueva función `reconcile_official_ranks` que imprime el contraste contra el `PUESTO` del PDF. |
| `backend/app/services/excel_service.py` | `resolve_or_create_team` normaliza el guion partido antes de buscar o crear el club. |
| `backend/app/services/scoring.py` | Limpieza de `ChampionshipStanding` obsoletos al recalcular. |

### 3.2 Frontend — migración a SSR

- `output: 'server'` + adaptador `@astrojs/node` (`standalone`).
- Se eliminan los `getStaticPaths()` de `/fechas/[slug]`, `/fechas/[slug]/resultados`, `/corredor/[slug]` y `/equipos/[slug]`.
- Se eliminan los mocks (`riderMock`, `teamMock`, `stagesDb` como fuente de verdad).
- Una API que responde `404` produce una página `404` propia; una API caída produce `503`. Nunca datos ficticios.
- `start.sh` acepta `dev` (por defecto) y `prod` (build + `node dist/server/entry.mjs`).
- Motivo y reglas completas en `specs/03` §0.

### 3.3 Tests

| Archivo | Cobertura |
|---|---|
| `backend/tests/test_pdf.py` | 198 resultados / 667 pts en La Joya; 112 / 554 en Z Xtreme; renglones partidos (dorsales 11, 14, 42, 186); duplicado 161. |
| `backend/tests/test_seed_integrity.py` | Cobertura end-to-end del seed: los 198/112 resultados con su tiempo oficial, ranking continuo por categoría, escala de 10 puntos, cero equipos duplicados, dorsal oficial aplicado, `CHARLES`/`ANDRES` por dorsal, riders sólo-en-PDF, liberación del dorsal 147 y limpieza de clasificaciones obsoletas. |

---

## 4. Verificación final

| Comprobación | La Joya Extreme | Z Xtreme 2026 |
| :--- | :--- | :--- |
| Resultados en el PDF oficial | 198 | 112 |
| Resultados cargados en la BD | **198** ✅ | **112** ✅ |
| Dorsales del PDF sin resultado | **0** ✅ | **0** ✅ |
| Resultados en BD sin respaldo en el PDF | **0** ✅ | **0** ✅ |
| Tiempos discrepantes vs PDF | **0** ✅ | **0** ✅ |
| Puntos (BD vs PDF oficial) | **667 = 667** ✅ | **555 vs 554** ✅ (ver §5) |
| Ranking continuo por categoría (1..N sin huecos) | ✅ | ✅ |
| Equipos duplicados | **0** ✅ | **0** ✅ |
| Clasificaciones obsoletas | **0** ✅ (248 = 248 pares reales) | ✅ |

Cifras oficiales verificadas con **dos oráculos independientes**: extracción por coordenadas con `pdfplumber` y `pdftotext -raw`. Ambas coinciden al 100% con el parser corregido.

- `pytest backend/tests` → **29 passed**.
- `npm run build` (SSR) → OK · `npx astro check` → **0 errores, 0 warnings, 0 hints** (33 archivos).
- Smoke test del servidor SSR: `/fechas/la-joya-extreme/resultados` → 200 con 198 resultados con tiempo; `/fechas/z-xtreme-2026/resultados` → 200 con 112; `/fechas/no-existe` → 404; `/corredor/no-existe` → 404.

---

## 5. Erratas conocidas del PDF oficial (documentadas, no corregidas en el origen)

El PDF del organizador tiene erratas en su columna `PUESTO`. El reglamento (`specs/01` §3.1) ordena por **tiempo**, así que el motor recalcula el puesto (copiar el `PUESTO` literal rompería la continuidad y la escala de puntos) y el seed imprime el contraste para revisión del organizador:

- **La Joya:** 24 de 198 filas.
  - MASTER B: el PDF salta el puesto 39 (el 39º real figura como 40º).
  - TURISMO MASTER VARONES: el dorsal 224 aparece con `PUESTO 1` cuando su tiempo lo sitúa en el 14º.
  - TURISMO OPEN VARONES: el dorsal 144 figura en el 13º con un tiempo (`01:20:00`) que lo situaría en el 3º.
- **Z Xtreme:** 12 de 112 filas.
  - TURISMO OPEN VARONES: el PDF repite el puesto 10 (dorsales 140 y 146) y salta el 21.
  - OPEN DAMAS: el PDF salta el puesto 6 (el dorsal 202 queda como 7º siendo el 6º por tiempo). De ahí el +1 punto de la BD respecto al PDF (555 vs 554).

---

## 6. Decisiones del organizador

1. **`CHARLES GONZALES` (PDF, dorsal 11) = `ANDRE GONZALES` (Excel, dorsal 11).** Mismo dorsal y misma categoría (ELITE): el fallback por dorsal con categoría coincidente le asigna el resultado oficial (`01:10:43`, 9 pts, 2º lugar de ELITE). El nombre conservado es el de la lista de inscritos.
2. **Migración a SSR.** Motivo: la web debe reflejar siempre el estado real de la BD; con prerenderizado, un build con la BD desactualizada publicaba datos viejos de forma silenciosa.
