"""
Sincroniza los esfuerzos de Strava de los segmentos oficiales del campeonato
**con el género del atleta**.

Usa la sesión Strava ya abierta en Chrome (CDP) y la API protegida del backend.
Es una herramienta LOCAL del administrador: nunca se despliega.

Por cada segmento de cada fecha:
  1. abre la página del segmento;
  2. lee el leaderboard en cuatro pasadas, cambiando los dos filtros de la
     cabecera de la tabla: *fecha* (Todos los tiempos / Este año) y *género*
     (Hombres / Mujeres);
  3. envía cada pasada a `POST /api/v1/stages/{stage_id}/sync-strava-efforts`
     con `athlete_gender` y `replace=false` (salvo la primera, que reemplaza).

El filtro de género es lo único que permite separar el KOM del QOM: hay
corredoras inscritas que no están dadas de alta en `riders`, de modo que su
intento no se puede cruzar por nombre ni por identificador.

Los filtros son dos `react-select` que **no** se abren con eventos sintéticos
(React ignora los `click`/`mousedown` despachados a mano). Se llaman sus
`onChange` reales a través del fiber de React del nodo de control.
"""
import json
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request

API_BASE = "http://127.0.0.1:8000/api/v1"
ADMIN_KEY = "***REMOVED-ADMIN-API-KEY***"

MESES = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}

# (clave de fecha en el react-select, clave de género, ¿reemplaza?)
PASSES = [
    ("all_time", "male", True),
    ("all_time", "female", False),
    ("this_year", "male", False),
    ("this_year", "female", False),
]

WAIT_AFTER_FILTER = 2.6  # segundos que tarda la tabla en refrescarse


def api_get(path):
    request = urllib.request.Request(f"{API_BASE}{path}")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def api_post(path, payload, attempts=8):
    """POST al backend, tolerando que el servidor se reinicie a mitad de lote."""
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{API_BASE}{path}",
        data=data,
        headers={"Content-Type": "application/json", "X-Admin-Key": ADMIN_KEY},
    )
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError:
            raise
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            if attempt == attempts - 1:
                raise
            print(
                f"    ! backend caído, reintento {attempt + 2}/{attempts}…",
                file=sys.stderr,
            )
            time.sleep(5)


def set_filter(probe: str, target: str) -> str:
    """Mueve uno de los dos react-select de la cabecera del leaderboard.

    `probe` identifica el selector (una opción que solo él tiene) y `target` es
    la opción a elegir. Se llama el `onChange` real del componente a través del
    fiber de React: los eventos sintéticos no abren estos menús.

    Hay que moverlos de uno en uno: si se llaman los dos `onChange` en el mismo
    tick, React descarta el primero.
    """
    return js(
        """
    (() => {
      const getProps = (ctrl) => {
        const key = Object.keys(ctrl).find(k => k.startsWith('__reactFiber$'));
        let fiber = ctrl[key];
        for (let i = 0; i < 25 && fiber; i++) {
          const props = fiber.memoizedProps;
          if (props && props.options && props.onChange) return props;
          fiber = fiber.return;
        }
        return null;
      };

      const controls = [...document.querySelectorAll('div[class*="css-lruqgf-control"]')];
      const props = controls.map(getProps).find(p => p && p.options.some(o => o.value === '%(probe)s'));
      if (!props) return 'sin filtro';
      props.onChange(props.options.find(o => o.value === '%(target)s'));
      return 'ok';
    })()
    """
        % {"probe": probe, "target": target}
    )


def filter_state() -> str:
    return js(
        """[...document.querySelectorAll('div[class*="singleValue"]')].map(e => e.textContent.trim()).join(' / ')"""
    )


def segment_rows() -> dict:
    """Metadatos del segmento y las filas visibles del leaderboard."""
    return json.loads(
        js(
            """
    (() => {
      if (!document.body) return JSON.stringify({name: null, distance: null, grade: null, rows: []});
      const lines = document.body.innerText.split('\\n').map(s => s.trim());
      const grab = (label) => { const i = lines.indexOf(label); return i >= 0 ? (lines[i+1] || null) : null; };

      const rows = [...document.querySelectorAll('table tbody tr')].map(tr => {
        const cells = [...tr.querySelectorAll('td')].map(td => td.innerText.trim().replace(/\\s+/g, ' '));
        const link = tr.querySelector('a[href*="/athletes/"]');
        return {
          cells: cells,
          athleteId: link ? (link.getAttribute('href').match(/\\/athletes\\/(\\d+)/) || [])[1] : null,
        };
      });

      return JSON.stringify({
        name: (document.querySelector('h1') || {}).innerText || null,
        distance: grab('Distance'),
        grade: grab('Avg Grade'),
        rows: rows,
      });
    })()
    """
        )
    )


def parse_distance(text):
    if not text:
        return 0.0
    return float(text.replace(" km", "").replace(",", ".").strip())


def parse_grade(text):
    if not text:
        return 0.0
    return float(text.replace("%", "").replace(",", ".").strip())


def parse_time(text):
    """'1:07:39' o '14:33' -> segundos."""
    if not text:
        return None
    parts = text.strip().split(":")
    try:
        parts = [int(p) for p in parts]
    except ValueError:
        return None
    seconds = 0
    for part in parts:
        seconds = seconds * 60 + part
    return seconds


def parse_date(text):
    """'17 may 2026' -> '2026-05-17'."""
    if not text:
        return None
    match = re.match(r"(\d{1,2})\s+([a-zA-Zñ]{3,})\s+(\d{4})", text.strip())
    if not match:
        return None
    day, month_name, year = match.groups()
    month = MESES.get(month_name[:3].lower())
    if not month:
        return None
    return f"{year}-{month:02d}-{int(day):02d}"


def build_efforts(info: dict, gender: str) -> list:
    efforts = []
    for index, row in enumerate(info.get("rows", [])):
        cells = row.get("cells", [])
        if len(cells) < 2:
            continue
        athlete = cells[1]
        seconds = parse_time(cells[-1])
        if seconds is None:
            continue
        measured_on = None
        for cell in cells:
            measured_on = parse_date(cell) or measured_on
        efforts.append(
            {
                "athlete_name_raw": athlete,
                "elapsed_time_sec": seconds,
                "measured_on": measured_on,
                "strava_athlete_id": row.get("athleteId"),
                "athlete_gender": gender,
                # Solo la primera fila de la pasada "Todos los tiempos /
                # Hombres" es el récord absoluto del tramo.
                "is_kom_qom": index == 0 and gender == "M",
            }
        )
    return efforts


def segments_of_stage(stage_id: int) -> list:
    """Todos los segmentos de la fecha, leídos de la BD local.

    El resumen público expone solo los más relevantes; los títulos de montaña
    se calculan sobre **todos**, así que sincronizar solo los del resumen
    dejaría el KOM o el descenso sin género.
    """
    db_path = os.environ.get("KUSPIDE_DB", "kuspide_mtb.db")
    with sqlite3.connect(db_path) as con:
        rows = con.execute(
            "SELECT strava_segment_id, name FROM strava_segments "
            "WHERE stage_id = ? ORDER BY id",
            (stage_id,),
        ).fetchall()
    return [{"strava_segment_id": str(seg_id), "name": name} for seg_id, name in rows]


def already_synced(segment_id: str) -> bool:
    """¿El segmento ya tiene intentos de ambos géneros? Sirve para reanudar."""
    db_path = os.environ.get("KUSPIDE_DB", "kuspide_mtb.db")
    with sqlite3.connect(db_path) as con:
        row = con.execute(
            """
            SELECT
              SUM(CASE WHEN e.athlete_gender = 'M' THEN 1 ELSE 0 END),
              SUM(CASE WHEN e.athlete_gender = 'F' THEN 1 ELSE 0 END)
            FROM strava_efforts e
            JOIN strava_segments s ON s.id = e.segment_id
            WHERE s.strava_segment_id = ?
            """,
            (segment_id,),
        ).fetchone()
    return bool(row and row[0] and row[1])


def main():
    # `SYNC_STAGES=slug1,slug2` sincroniza solo esas fechas (útil para probar
    # o re-sincronizar una sola jornada); vacío = todas.
    only = {
        part.strip()
        for part in os.environ.get("SYNC_STAGES", "").split(",")
        if part.strip()
    }
    stages = api_get("/stages")
    for stage in stages:
        slug = stage.get("slug")
        stage_id = stage.get("id")
        if not slug or not stage_id:
            continue
        if only and slug not in only:
            continue
        segments = segments_of_stage(stage_id)
        if not segments:
            print(f"\n=== {slug}: sin segmentos ===", file=sys.stderr)
            continue

        print(f"\n=== {slug} (stage_id {stage_id}) · {len(segments)} segmentos ===", file=sys.stderr)

        # `SYNC_LIMIT=1` procesa solo el primer segmento: prueba de humo.
        limit = int(os.environ.get("SYNC_LIMIT", "0") or 0)
        if limit:
            segments = segments[:limit]

        for segment in segments:
            seg_id = str(segment.get("strava_segment_id") or "")
            if not seg_id:
                continue
            # `SYNC_RESUME=1` salta los segmentos ya sincronizados con género.
            if os.environ.get("SYNC_RESUME") and already_synced(seg_id):
                print(f"  · {seg_id} ya sincronizado: se salta", file=sys.stderr)
                continue
            name = segment.get("name") or f"SEG {seg_id}"

            new_tab(f"https://www.strava.com/segments/{seg_id}")
            wait_for_load()
            # La tabla de tiempos tarda en aparecer. Se reintenta la carga una
            # vez si la página quedó en blanco (pasa con pestañas recicladas).
            info = {"rows": []}
            for attempt in range(2):
                for _ in range(25):
                    time.sleep(0.6)
                    try:
                        if js("document.querySelectorAll('table tbody tr').length"):
                            break
                    except Exception:
                        continue
                time.sleep(1.0)
                info = segment_rows()
                if info.get("rows"):
                    break
                new_tab(f"https://www.strava.com/segments/{seg_id}")
                wait_for_load()
            distance_m = parse_distance(info.get("distance")) * 1000
            grade = parse_grade(info.get("grade"))
            if not info.get("rows"):
                print(f"  ✗ {seg_id} sin tabla de tiempos: se omite", file=sys.stderr)
                continue

            total = 0
            for date_key, gender_key, replace in PASSES:
                set_filter("this_year", date_key)
                time.sleep(WAIT_AFTER_FILTER)
                set_filter("female", gender_key)
                time.sleep(WAIT_AFTER_FILTER)
                state = filter_state()
                pass_info = segment_rows()
                gender = "M" if gender_key == "male" else "F"
                efforts = build_efforts(pass_info, gender)
                if not efforts:
                    continue
                payload = {
                    "strava_segment_id": seg_id,
                    "segment_name": info.get("name") or name,
                    "distance_m": distance_m,
                    "average_grade": grade,
                    "efforts": efforts,
                    "replace": replace,
                }
                api_post(f"/stages/{stage_id}/sync-strava-efforts", payload)
                total += len(efforts)
                print(
                    f"    · {seg_id} {date_key:9} {gender} {len(efforts):2d} "
                    f"(filtros: {state})",
                    file=sys.stderr,
                )

            print(f"  ✓ {seg_id} {name[:36]:38} {total:3d} intentos", file=sys.stderr)


if __name__ in ("__main__", "browser_harness.run"):
    # El harness de browser-use ejecuta el archivo con `exec`, así que
    # `__name__` es "browser_harness.run" y no "__main__".
    main()
