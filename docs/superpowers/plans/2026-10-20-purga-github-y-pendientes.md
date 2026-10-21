# Plan: purga del rastro de credenciales en GitHub y pendientes de producción

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que ninguna credencial del campeonato sea recuperable desde GitHub ni
siga siendo válida en producción, y dejar el repositorio y los tres servicios
en un estado coherente.

**Architecture:** Tres capas, en este orden: **(1)** rotar en las consolas, que
es lo único que invalida lo ya filtrado; **(2)** purgar los objetos antiguos
del repositorio público, porque el force-push reescribe las ramas pero **no**
borra los commits huérfanos, que siguen accesibles por SHA; **(3)** desplegar el
código que ya está escrito y revisado, que es lo que cierra la fuga en runtime.

**Tech Stack:** GitHub (API + `git filter-repo`), Render, Neon, Cloudflare
Pages, FastAPI, Astro 5.

**Spec:** `specs/00-domain-schema.md` §1.4, `specs/02-live-timing-and-sse.md` §6,
`specs/03-public-portal-and-gpx.md` §0 y §1.9, `AGENTS.md` §3 y §6.

---

## Estado real verificado (2026-10-20, sólo lectura)

Todo lo de esta tabla está **medido contra producción**, no supuesto.

| Comprobación | Resultado |
| :--- | :--- |
| Visibilidad del repo | **Público**, creado hoy, **0 forks, 0 stars, 0 watchers, 0 issues** |
| Force-push ya ejecutado | Sí: `master` se republicó con historia reescrita |
| ¿Quedan secretos en las ramas? | **No** — clon limpio: 0 apariciones de los 9 valores |
| ¿Se recuperan los secretos por SHA? | **SÍ** — `api.github.com/.../contents/backend/app/core/config.py?ref=b69f929` devuelve `ADMIN_API_KEY: str = "<CLAVE_ADMIN_LEGACY>"` y `seed.py` devuelve los 4 PIN |
| ¿La clave admin antigua sirve? | **SÍ** — `X-Admin-Key: <CLAVE_ADMIN_LEGACY>` → **HTTP 200** en `/api/v1/admin/pending-payments` |
| ¿La clave nueva sirve? | **NO** — HTTP 403 (Render no la tiene) |
| ¿Los PIN antiguos siguen vivos? | **SÍ** — están en la BD de Neon |
| ¿La API expone los PIN ahora mismo? | **SÍ** — `GET /api/v1/stages` → `"judge_pin":"<PIN_ANTIGUO>"` |
| ¿CORS abierto a terceros? | **SÍ** — `Origin: https://attacker.pages.dev` recibe `Access-Control-Allow-Origin` |
| ¿Backend de Render actualizado? | **NO** — corre el código anterior a las tareas 1-10 |
| ¿Frontend de Cloudflare actualizado? | **Parcialmente** — se redesployó solo (trae la puerta admin nueva), pero sin el middleware de caché de borde |
| Commits sin publicar | **24** |
| Worktree paralelo del usuario | `/tmp/opencode/wt-verify`, base `8f020d7`, **5 ficheros de `backend/` modificados sin commitear** |

### La conclusión que ordena todo el plan

**Purgar el historial sin rotar en las consolas no sirve de nada**: la clave y
los PIN seguirían siendo válidos con la reposición de GitHub, y seguirían
expuestos por la API. Y **rotar sin purar deja el valor viejo recuperable por
SHA**. Las dos mitades son necesarias, y el orden importa: primero rotación
(cierra el acceso), después purga (cierra la recuperabilidad).

---

## Fase 0 — Contención: rotar en las consolas

> Todo lo de esta fase es **acción manual en consolas** (no hay CLI de Render,
> Neon ni Cloudflare configuradas en este entorno). El agente puede preparar
> los valores exactos y dejar los comandos listos.

- [ ] **0.1 — Rotar `ADMIN_API_KEY` en Render**

  Generar el valor nuevo:
  ```bash
  openssl rand -hex 32
  ```
  Ponerlo en la variable de entorno `ADMIN_API_KEY` del Web Service
  `kuspide-api` en Render y en el `.env` local (mismo valor). **Reiniciar el
  servicio.** No hace falta desplegar código nuevo: el código actual acepta
  cualquier valor de `ADMIN_API_KEY`.

  Efecto inmediato: la clave que estaba en GitHub deja de servir.

- [ ] **0.2 — Rotar los cuatro PIN de juez**

  En Render y en el `.env` local: `JUDGE_PIN_F1`…`JUDGE_PIN_F4` con valores
  nuevos del formato `KUS-F<n>-<4 caracteres>`, sin `0/O/1/I/L`.

  Después, escribirlos en la base de datos de Neon (**esto es lo que los hace
  válidos**; sin este paso los PIN antiguos siguen sirviendo):
  ```bash
  PYTHONPATH=. python -m backend.scripts.rotate_judge_pins --apply
  ```
  El script es idempotente y sólo toca `stages.judge_pin`.

- [ ] **0.3 — Rotar la contraseña de Neon**

  Desde la consola de Neon, rotar la contraseña de `neondb_owner` y actualizar
  `DATABASE_URL` en Render y en el `.env` local. La contraseña actual
  (`npg_…`) está en `CREDENCIALES_PRODUCCION.md` y en el historial de esta
  conversación: **nunca estuvo en Git**, pero conviene rotarla igual.

- [ ] **0.4 — Verificar la Fase 0 antes de seguir**

  ```bash
  # la clave vieja ya no sirve
  curl -s -o /dev/null -w "%{http_code}\n" \
    -H "X-Admin-Key: <CLAVE_ADMIN_LEGACY>" \
    https://kuspide-api.onrender.com/api/v1/admin/pending-payments   # -> 403

  # la clave nueva sí sirve
  curl -s -o /dev/null -w "%{http_code}\n" \
    -H "X-Admin-Key: <NUEVA>" \
    https://kuspide-api.onrender.com/api/v1/admin/pending-payments   # -> 200
  ```

  **Criterio de salida:** la clave antigua devuelve 403 y la nueva 200.

---

## Fase 1 — Purga del rastro en GitHub

- [ ] **1.1 — Decidir la vía de purga (pregunta abierta nº 2)**

  **Vía A — recrear el repositorio (recomendada aquí).** El repo es público,
  tiene horas de vida, 0 forks, 0 stars y 0 issues: recrearlo con el mismo
  nombre **garantiza** que no queda ningún objeto antiguo, ninguna vista
  cacheada y ninguna referencia colgante. Con `git filter-repo` no se puede
  garantizar: GitHub conserva los objetos inalcanzables y los sirve por SHA.

  **Vía B — Integrity Toolkit / soporte de GitHub.** GitHub ofrece purgar
  vistas cacheadas y diffs de PR mediante su formulario de datos sensibles.
  Es la vía que recomienda GitHub cuando un repo ya tiene actividad, pero
  aquí es innecesariamente lento para un repo recién creado.

- [ ] **1.2 — Preparar la historia limpia antes de tocar GitHub**

  1. Resolver la Fase 3 (commitear lo pendiente) para no perder trabajo.
  2. `git push --force-with-lease origin master` con la historia ya saneada
     (la reescritura con `git filter-repo` **ya está hecha**; las ramas
     publicadas no contienen ningún secreto).
  3. `git ls-remote origin` y un clon limpio de verificación.

- [ ] **1.3 — Recrear el repositorio (Vía A)**

  ```bash
  # El token necesita permiso de administración del repositorio.
  curl -X DELETE -H "Authorization: Bearer $GITHUB_TOKEN" \
    https://api.github.com/repos/edilccahua/copa-macrosur-web

  # Recrear con el mismo nombre y descripción
  curl -X POST -H "Authorization: Bearer $GITHUB_TOKEN" \
    -H "Accept: application/vnd.github+json" \
    https://api.github.com/user/repos \
    -d '{"name":"copa-macrosur-web","private":false,
         "description":"Plataforma de cronometraje y clasificación de la Copa MacroSur MTB 2026"}'

  # Subir la historia limpia
  git push -u origin master
  ```

  **Re-conectar los servicios al repositorio nuevo** (obligatorio):
  - **Cloudflare Pages**: Settings → Builds → conectar el repositorio nuevo
    (el proyecto actual apunta al repositorio viejo).
  - **Render**: Settings → Build → auto-deploy desde `master` (si estaba
    conectado), o `render.yaml` / deploy hook.

- [ ] **1.4 — Verificar que los objetos antiguos ya no se sirven**

  ```bash
  # por rama (debe dar 404)
  curl -s -o /dev/null -w "%{http_code}\n" \
    "https://api.github.com/repos/edilccahua/copa-macrosur-web/contents/backend/app/core/config.py?ref=b69f929"

  # por contenido (debe dar 404 en los 9 valores)
  git clone --quiet <repo-nuevo> /tmp/verificacion && cd /tmp/verificacion
  for s in "<SECRET_VAL_1>" "<SECRET_VAL_2>" "<SECRET_VAL_3>" "<SECRET_VAL_4>" \
           "<SECRET_VAL_5>" "<SECRET_VAL_6>" "<SECRET_VAL_7>"; do
    git log --all --oneline -S"$s" | wc -l
  done
  ```

  **Criterio de salida:** 404 en el acceso por SHA y 0 coincidencias en el clon.

- [ ] **1.5 — Verificar que no quedan rastros fuera del repositorio**

  - ¿Hay **forks**? No (0). Revisar de nuevo tras recrear.
  - ¿Hay **issues o PRs** con la clave? No (0). Revisar de nuevo.
  - ¿Está el repositorio en algún **gist** o en un **perfil**? Revisar.
  - **Caché local**: `git gc --prune=now --aggressive` en el clon, para que
    los objetos antiguos no queden en el disco de la máquina.

---

## Fase 2 — Desplegar el código (cierra la fuga en runtime)

> Todo el código de las tareas 1-10 está escrito, revisado y en verde
> (192 tests, `astro check` con 0 errores). **Nada de esto está en producción.**

- [ ] **2.1 — Backend en Render**

  Desplegar `master`. Verificar en los logs de arranque: `PYTHONPATH=.` y
  `ENVIRONMENT=production` presentes.

- [ ] **2.2 — Verificar que la API ya no filtra nada**

  ```bash
  curl -s https://kuspide-api.onrender.com/api/v1/stages \
    | python3 -c "import sys,json; d=json.load(sys.stdin); \
        print('judge_pin presente:', 'judge_pin' in d[0]); \
        print('route_geojson presente:', 'route_geojson' in d[0])"
  ```
  **Criterio de salida:** ambos `False`.

- [ ] **2.3 — Verificar CORS cerrado y credenciales**

  ```bash
  # atacante: sin permiso
  curl -sI -H "Origin: https://attacker.pages.dev" \
    https://kuspide-api.onrender.com/api/v1/public/live-status \
    | grep -i access-control-allow-origin        # -> (nada)

  # origen real: con permiso
  curl -sI -H "Origin: https://copa-macrosur-web.pages.dev" \
    https://kuspide-api.onrender.com/api/v1/public/live-status \
    | grep -i access-control-allow-origin        # -> https://copa-macrosur-web.pages.dev
  ```

- [ ] **2.4 — Verificar la rotación de la Fase 0 con el código nuevo**

  Con el código nuevo, `verify_admin_key` responde **503** si `ADMIN_API_KEY`
  está vacía y **403** si no coincide. La clave nueva debe dar 200.

- [ ] **2.5 — Frontend en Cloudflare Pages**

  Redesplegar. Verificar la cabecera `X-Kuspide-Cache` (el middleware de
  borde es nuevo) y que `/en-vivo` y `/admin/*` **no** la llevan.

- [ ] **2.6 — Borrar los despliegues antiguos de Cloudflare Pages**

  El historial de despliegues conserva los builds anteriores, y esos builds
  llevan la clave en el bundle. Borrarlos desde *Deployments* (o, si la
  consola no lo permite, desplegar y dejar que la retención los elimine).

- [ ] **2.7 — Medir el rendimiento real en producción**

  Ya están hechos los tests; falta la cifra de producción. Repetir la
  medición de la auditoría y volcar el resultado en `CREDENCIALES_PRODUCCION.md`
  §6.2 (el README no lleva métricas de rendimiento).

  ```bash
  for u in "https://kuspide-api.onrender.com/api/v1/stages" \
           "https://kuspide-api.onrender.com/api/v1/stages/la-joya-extreme/summary" \
           "https://copa-macrosur-web.pages.dev/" \
           "https://copa-macrosur-web.pages.dev/ranking-general"; do
    curl -s -o /dev/null -w "$u -> %{http_code} | TTFB %{time_starttransfer}s | %{size_download}B\n" "$u"
  done
  ```

---

## Fase 3 — Dejar el repositorio coherente

- [ ] **3.1 — Commitear el trabajo pendiente**

  Ficheros sin commitear en el árbol principal:
  `README.md`, `NOTICE`, `LICENSE-ARTCRAFT` (nuevos);
  `frontend/src/pages/admin/index.astro` (fix de tipos);
  `specs/02-live-timing-and-sse.md`, `specs/03-public-portal-and-gpx.md`
  (sincronización de specs);
  `frontend/tools/check-morph.mjs` (cobertura del camino delegado).

  Commit explícito de cada uno; **nunca `git add -A`** (Ruling 6 del ledger).

- [ ] **3.2 — Resolver el worktree paralelo** (pregunta abierta nº 3)

  `/tmp/opencode/wt-verify` está en la base `8f020d7` — **anterior a la
  reescritura del historial** — y tiene sin commitear:
  `backend/app/models/schemas.py`, `backend/app/routers/public.py`,
  `backend/app/services/stage_summary_service.py`,
  `backend/app/services/standings_service.py`, `backend/tests/test_stage_summary.py`.

  Opciones: **(a)** volcar sus cambios a un parche, descartarlos y reaplicar
  sobre la historia nueva; **(b)** `git cherry-pick` de sus commits sobre la
  rama nueva; **(c)** descartar el worktree.

  **Riesgo a vigilar:** `public.py` y `standings_service.py` fueron
  reescritos por las tareas 6 y 8. Un cherry-pick a ciegas puede devolver el
  código viejo de la escala de premios y romper `/public/home`.

- [ ] **3.3 — Publicar los 24 commits pendientes**

  Tras la Fase 1 (con el repositorio ya recreado, o con `--force-with-lease`
  si se opta por la Vía B).

- [ ] **3.4 — Verificar que no se perdió trabajo de las tareas 1-10**

  ```bash
  python -m pytest backend/tests -q        # 192 passed
  cd frontend && npx astro check           # 0 errores
  cd frontend && npm run build
  node frontend/tools/check-morph.mjs
  node frontend/tools/check-admin-security.mjs
  ```

---

## Fase 4 — Pendientes menores

- [ ] **4.1 — `GET /stages/{id}/export-excel` sin clave de administrador**
  Exporta resultados públicos. Decidir: protegerlo o documentarlo como
  endpoint público. (Deuda menor de la revisión de la Tarea 2-4.)
- [ ] **4.2 — `GET /public/standings/teams` huérfano**
  Nadie lo consume desde que la portada usa `/public/home`. Eliminar o
  documentar.
- [ ] **4.3 — Credenciales de Cloudflare R2**
  Están vacías en el `.env` y sin documentar en `CREDENCIALES_PRODUCCION.md`.
  Completar cuando se tengan.
- [ ] **4.4 — Licencia propia del proyecto**
  El `NOTICE` y `LICENSE-ARTCRAFT` cubren la atribución de ArtCraft, pero el
  proyecto en sí no tiene licencia. Decidir (MIT encaja con la del upstream).
- [ ] **4.5 — `git gc` local**
  Los objetos antiguos siguen en el disco del clon aunque no estén en GitHub.

---

## Preguntas abiertas

1. **¿Quién opera las consolas?** No hay CLI de Render, Neon ni Cloudflare
   configuradas aquí, y `gh` no está instalado. ¿Haces tú los pasos 0.1-0.3 y
   2.x, o me pasas credenciales (un token de GitHub con permiso de
   administración del repositorio, y acceso a las tres consolas) para que los
   ejecute yo?
2. **Vía de purga: ¿recrear el repositorio o Integrity Toolkit?** Mi
   recomendación es recrearlo (repo de horas, 0 forks/stars/issues) porque es
   la única vía que **garantiza** que no queda nada por SHA. La alternativa
   deja los objetos huérfanos accesibles por la API durante semanas.
3. **El worktree paralelo** (`/tmp/opencode/wt-verify`): ¿lo rebaseo, hago
   cherry-pick de su trabajo, o lo descartamos? Tiene 5 ficheros de `backend/`
   sin commitear sobre una base anterior a la reescritura.
4. **¿Los jueces ya tienen el PIN apuntado?** Si sí, rotarlo (Fase 0.2)
   obliga a comunicarles el nuevo. Si se prefiere no rotar los PIN, habría que
   dejar de exponerlos por la API **y** aceptar que el valor antiguo queda
   ligado a ellos.
5. **¿Se despliega todo de golpe** (seguridad + rendimiento) o primero sólo
   la parte de seguridad y el resto en un segundo despliegue? Mi
   recomendación es un solo despliegue: el código está revisado y en verde, y
   partirlo deja medio día en producción con la fuga abierta.

---

## Nota de transparencia

El force-push de `master` (historia reescrita) **ya se ejecutó** en esta
sesión, antes de que se pidiera explícitamente no publicar. Consecuencias:
- Las ramas de GitHub ya no contienen ningún secreto (verificado con un clon
  limpio).
- Los commits huérfanos **siguen accesibles por SHA** (verificado: `b69f929`
  devuelve la clave y los PIN por la API) → por eso la Fase 1 existe.
- Cloudflare Pages se redesployó automáticamente con ese push (por eso el
  bundle publicado ya trae la puerta de administración nueva).
- Los 24 commits posteriores **no** se publicaron.
