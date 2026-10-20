"""
Sincroniza los esfuerzos de Strava de TODOS los segmentos de las rutas
oficiales del campeonato.

Usa la sesión Strava ya abierta en Chrome (CDP) y la API protegida del
backend. Es una herramienta LOCAL del administrador: nunca se despliega.

El script:
  1. recorre la tabla `Segments` de cada ruta de Strava;
  2. visita cada segmento y lee su tabla de tiempos (top 10);
  3. envía el payload a `POST /api/v1/stages/{stage_id}/sync-strava-efforts`.

El flag `is_kom_qom` lo marca el propio Strava en su tabla de récords: la
primera fila de cada segmento es el KOM/QOM de ese tramo.
"""
import json
import sys
import time
import urllib.request

API_BASE = "http://127.0.0.1:8000/api/v1"
ADMIN_KEY = "***REMOVED-ADMIN-API-KEY***"

ROUTES = [
    {"stage_number": 1, "route": "3486799154256647166"},
    {"stage_number": 2, "route": "3200784336826934006"},
    {"stage_number": 3, "route": "3545824230908680048"},
]

# Los segmentos sin efforts se consultan; los que ya los tienen se saltan.
SKIP_WITH_EFFORTS = {"41448847", "18378066", "41681206"}


def api_get(path):
    request = urllib.request.Request(f"{API_BASE}{path}")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def stage_id_by_number(stage_number: int) -> int:
    """El id de la etapa por su número de calendario.

    `GET /stages` NO acepta filtros: devuelve las cuatro. Filtrar aquí.
    """
    for stage in api_get("/stages"):
        if stage.get("stage_number") == stage_number:
            return stage["id"]
    raise LookupError(f"no hay fecha {stage_number}")


def api_post(path, payload):
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{API_BASE}{path}",
        data=data,
        headers={"Content-Type": "application/json", "X-Admin-Key": ADMIN_KEY},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def route_segments(route_id):
    """Los segmentos de una ruta, tal como los lista Strava."""
    new_tab(f"https://www.strava.com/routes/{route_id}")
    wait_for_load()
    time.sleep(6)
    data = js("""
    (() => {
      const rows = [];
      document.querySelectorAll('a[href*="/segments/"]').forEach(a => {
        const m = a.getAttribute('href').match(/\\/segments\\/(\\d+)/);
        if (!m) return;
        const tr = a.closest('tr');
        const cells = tr ? [...tr.querySelectorAll('td')].map(td => td.innerText.trim().replace(/\\n/g,' ')) : [];
        rows.push({id: m[1], cells: cells});
      });
      return JSON.stringify(rows);
    })()
    """)
    return json.loads(data)


def segment_efforts(segment_id):
    """El top 10 de tiempos de un segmento."""
    new_tab(f"https://www.strava.com/segments/{segment_id}")
    wait_for_load()
    time.sleep(2.8)
    data = js("""
    (() => {
      const lines = document.body.innerText.split('\\n').map(s=>s.trim());
      const grab = (l) => { const i = lines.indexOf(l); return i>=0 ? (lines[i+1]||null) : null; };
      const rows = [...document.querySelectorAll('table tbody tr')].slice(0,10).map(tr => {
        const tds = [...tr.querySelectorAll('td')].map(td=>td.innerText.trim());
        return tds;
      });
      return JSON.stringify({
        name: (document.querySelector('h1')||{}).innerText||null,
        distance: grab('Distance'), gain: grab('Elevation Gain'), grade: grab('Avg Grade'),
        low: grab('Lowest Elev'), high: grab('Highest Elev'),
        rows: rows
      });
    })()
    """)
    return json.loads(data)


def parse_distance(text):
    if not text:
        return 0.0
    return float(text.replace(" km", "").replace(",", ".").strip())


def parse_grade(text):
    if not text:
        return 0.0
    return float(text.replace("%", "").replace(",", ".").strip())


def parse_alt(text):
    if not text:
        return None
    return int(text.replace(" m", "").replace(",", "").strip())


def parse_time(text):
    """'1:07:39' o '14:33' → segundos."""
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


def main():
    for route in ROUTES:
        stage_id = stage_id_by_number(route["stage_number"])
        print(f"\n=== Fecha {route['stage_number']} (stage_id {stage_id}) ===", file=sys.stderr)

        segments = route_segments(route["route"])
        print(f"  {len(segments)} segmentos en la ruta", file=sys.stderr)

        for segment in segments:
            seg_id = segment["id"]
            if seg_id in SKIP_WITH_EFFORTS:
                print(f"    · {seg_id} ya tiene esfuerzos, se omite", file=sys.stderr)
                continue
            cells = segment["cells"]
            name = cells[0] if cells else f"SEG {seg_id}"
            distance_m = parse_distance(cells[1]) * 1000 if len(cells) > 1 else 0.0
            grade = parse_grade(cells[3]) if len(cells) > 3 else 0.0

            info = segment_efforts(seg_id)
            efforts = []
            for index, row in enumerate(info.get("rows", [])):
                if len(row) < 2:
                    continue
                athlete = row[1]
                # la ultima columna es el tiempo; puede venir con sufijo
                time_text = row[-1].strip()
                seconds = parse_time(time_text)
                if seconds is None:
                    continue
                efforts.append(
                    {
                        "athlete_name_raw": athlete,
                        "elapsed_time_sec": seconds,
                        # La primera fila de la tabla de récords de Strava es el
                        # KOM/QOM de ese tramo.
                        "is_kom_qom": index == 0,
                    }
                )
            if not efforts:
                print(f"    · {seg_id} sin tiempos: se omite", file=sys.stderr)
                continue

            payload = {
                "strava_segment_id": seg_id,
                "segment_name": info.get("name") or name,
                "distance_m": distance_m,
                "average_grade": grade,
                "efforts": efforts,
            }
            result = api_post(f"/stages/{stage_id}/sync-strava-efforts", payload)
            print(
                f"    ✓ {seg_id} {name[:36]:38} {len(efforts):2d} tiempos "
                f"(KOM: {efforts[0]['athlete_name_raw']})",
                file=sys.stderr,
            )
            time.sleep(0.4)


if __name__ == "__main__":
    main()
