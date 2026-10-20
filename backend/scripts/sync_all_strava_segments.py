"""
Sincroniza los esfuerzos de Strava de las rutas oficiales del campeonato.

Usa la sesion Strava ya abierta en Chrome (CDP) y la API protegida del
backend. Es una herramienta LOCAL del administrador: nunca se despliega.

Por cada segmento de la tabla `Segments` de cada ruta:
  1. lee la tabla de tiempos (top 10) con la FECHA de cada intento y el
     identificador del atleta en Strava;
  2. envia el payload a `POST /api/v1/stages/{stage_id}/sync-strava-efforts`.

La fecha es lo que permite distinguir los intentos de la carrera de los de
años atrás: Strava lista en un mismo segmento los de 2019, 2023, 2024 y los
del día de la carrera, todos en la misma tabla.
"""
import json
import re
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

MESES = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}


def api_get(path):
    request = urllib.request.Request(f"{API_BASE}{path}")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def api_post(path, payload):
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{API_BASE}{path}",
        data=data,
        headers={"Content-Type": "application/json", "X-Admin-Key": ADMIN_KEY},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def stage_id_by_number(stage_number: int) -> int:
    """El id de la etapa por su numero de calendario.

    `GET /stages` NO acepta filtros: devuelve las cuatro. Filtrar aqui.
    """
    for stage in api_get("/stages"):
        if stage.get("stage_number") == stage_number:
            return stage["id"]
    raise LookupError(f"no hay fecha {stage_number}")


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
        const cells = tr ? [...tr.querySelectorAll('td')].map(td => td.innerText.trim().replace(/\\n/g, ' ')) : [];
        rows.push({id: m[1], cells: cells});
      });
      return JSON.stringify(rows);
    })()
    """)
    return json.loads(data)


def segment_efforts(segment_id):
    """El top 10 de tiempos de un segmento, con fecha y atleta de Strava."""
    new_tab(f"https://www.strava.com/segments/{segment_id}")
    wait_for_load()
    # La tabla de tiempos tarda en aparecer: se espera a que tenga filas.
    for _ in range(20):
        time.sleep(0.6)
        try:
            count = js("document.querySelectorAll('table tbody tr').length")
        except Exception:
            continue
        if count and count > 0:
            break
    time.sleep(1.2)
    data = js("""
    (() => {
      const lines = document.body.innerText.split('\\n').map(s => s.trim());
      const grab = (l) => { const i = lines.indexOf(l); return i >= 0 ? (lines[i+1] || null) : null; };
      const rows = [...document.querySelectorAll('table tbody tr')].slice(0, 10).map(tr => {
        const tds = [...tr.querySelectorAll('td')].map(td => td.innerText.trim());
        // el identificador del atleta sale del enlace a su perfil
        const link = tr.querySelector('a[href*="/athletes/"]');
        const athleteId = link ? (link.getAttribute('href').match(/\\/athletes\\/(\\d+)/) || [])[1] : null;
        return {cells: tds, athleteId: athleteId};
      });
      return JSON.stringify({
        name: (document.querySelector('h1') || {}).innerText || null,
        distance: grab('Distance'), gain: grab('Elevation Gain'),
        grade: grab('Avg Grade'), low: grab('Lowest Elev'), high: grab('Highest Elev'),
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


def main():
    for route in ROUTES:
        stage_id = stage_id_by_number(route["stage_number"])
        print(f"\n=== Fecha {route['stage_number']} (stage_id {stage_id}) ===", file=sys.stderr)

        segments = route_segments(route["route"])
        print(f"  {len(segments)} segmentos en la ruta", file=sys.stderr)

        for segment in segments:
            seg_id = segment["id"]
            cells = segment["cells"]
            name = cells[0] if cells else f"SEG {seg_id}"
            distance_m = parse_distance(cells[1]) * 1000 if len(cells) > 1 else 0.0
            grade = parse_grade(cells[3]) if len(cells) > 3 else 0.0

            info = segment_efforts(seg_id)
            efforts = []
            for index, row in enumerate(info.get("rows", [])):
                cells_row = row.get("cells", [])
                if len(cells_row) < 2:
                    continue
                athlete = cells_row[1]
                seconds = parse_time(cells_row[-1].strip())
                if seconds is None:
                    continue
                # la fecha es la penultima columna con formato "17 may 2026"
                measured_on = None
                for cell in cells_row:
                    measured_on = parse_date(cell) or measured_on
                efforts.append(
                    {
                        "athlete_name_raw": athlete,
                        "elapsed_time_sec": seconds,
                        "measured_on": measured_on,
                        "strava_athlete_id": row.get("athleteId"),
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
            api_post(f"/stages/{stage_id}/sync-strava-efforts", payload)
            con_fecha = sum(1 for e in efforts if e["measured_on"])
            print(
                f"    ✓ {seg_id} {name[:34]:36} {len(efforts):2d} tiempos "
                f"({con_fecha} con fecha, {sum(1 for e in efforts if e['strava_athlete_id'])} con id)",
                file=sys.stderr,
            )
            time.sleep(0.4)


if __name__ == "__main__":
    main()
