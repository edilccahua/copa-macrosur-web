"""
Sincronización LOCAL de esfuerzos de Strava por CDP (Chrome DevTools Protocol).

REGLA DE SEGURIDAD (skill `strava-playwright`):
 - NUNCA se ejecuta en servidores/cloud (las IPs de datacenter son bloqueadas por Strava).
 - Se conecta a un Chrome REAL abierto con `--remote-debugging-port=9222` donde el
   administrador ya inició sesión con su cuenta Strava.

Uso:
  1. Abrir Chrome con depuración y sesión de Strava:
       google-chrome --remote-debugging-port=9222
  2. Levantar el backend (X-Admin-Key = ADMIN_API_KEY).
  3. Ejecutar:
       python -m backend.scripts.sync_strava_local --stage 1 \
           --segment 3491115554159610124 --segment-name "Segmento oficial La Joya" \
           --date today

  Para descubrir los segmentos de una actividad de la carrera y subirlos todos:
       python -m backend.scripts.sync_strava_local --stage 2 \
           --activity https://www.strava.com/activities/19868121820 --date today

Requiere: `pip install playwright` (usa una instalación de Chrome ya existente, no descarga).
"""
from __future__ import annotations

import argparse
import os
import datetime
import re
import sys
from typing import Dict, List, Optional

import httpx


API_BASE_DEFAULT = "http://localhost:8000/api/v1"


def parse_elapsed_to_seconds(text: str) -> Optional[int]:
    """Convierte '10:42', '1:02:33' o '2h 3m 4s' a segundos enteros."""
    text = (text or "").strip().lower()
    if not text:
        return None
    if ":" in text:
        parts = [int(p) for p in re.findall(r"\d+", text)]
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
        return None
    m = re.match(r"(?:(\d+)h)?\s*(?:(\d+)m)?\s*(?:(\d+)s)?$", text)
    if m and any(m.groups()):
        h, mm, s = (int(g) if g else 0 for g in m.groups())
        return h * 3600 + mm * 60 + s
    return None


def _connect():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("ERROR: falta 'playwright'. Instala con: pip install playwright", file=sys.stderr)
        raise SystemExit(2)
    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp("http://localhost:9222")
    except Exception as exc:  # noqa: BLE001
        pw.stop()
        print(
            "ERROR: no se pudo conectar a Chrome en :9222. Abre Chrome con\n"
            "  google-chrome --remote-debugging-port=9222   y con sesión de Strava iniciada.\n"
            f"Detalle: {exc}",
            file=sys.stderr,
        )
        raise SystemExit(3)
    context = browser.contexts[0] if browser.contexts else browser.new_context()
    return pw, browser, context


def discover_segments_from_activity(page, activity_url: str) -> List[Dict[str, str]]:
    """Abre una actividad y devuelve [{strava_segment_id, name}] de sus segmentos."""
    page.goto(activity_url, wait_until="networkidle", timeout=60000)
    links = page.eval_on_selector_all(
        "a[href*='/segments/']",
        "els => els.map(a => ({href: a.href, text: a.textContent.trim()}))",
    )
    seen: Dict[str, str] = {}
    for link in links:
        m = re.search(r"/segments/(\d+)", link["href"])
        if m:
            seen.setdefault(m.group(1), link["text"] or f"Segmento {m.group(1)}")
    return [{"strava_segment_id": sid, "name": name} for sid, name in seen.items()]


def scrape_segment_leaderboard(page, segment_id: str, date_filter: str) -> Dict[str, object]:
    """Extrae la tabla de posiciones del segmento (atletas + tiempos) filtrada por fecha."""
    url = f"https://www.strava.com/segments/{segment_id}"
    page.goto(url, wait_until="networkidle", timeout=60000)

    name = ""
    title = page.query_selector("h1")
    if title:
        name = title.inner_text().strip()

    # El filtro de fecha de Strava se aplica con el parámetro ?date_range=<period>
    if date_filter and date_filter not in ("all", ""):
        page.goto(f"{url}?date_range={date_filter}", wait_until="networkidle", timeout=60000)

    rows = page.eval_on_selector_all(
        "table.table-leaderboard tr, .leaderboard tr",
        "els => els.map(tr => Array.from(tr.querySelectorAll('td,a')).map(c => "
        "(c.getAttribute && c.getAttribute('href')) || c.textContent.trim()))",
    )

    efforts = []
    for cells in rows:
        athlete_name, athlete_id, secs = None, None, None
        for cell in cells:
            if isinstance(cell, str) and cell.startswith("/athletes/"):
                athlete_id = re.search(r"/athletes/(\d+)", cell)
                athlete_id = athlete_id.group(1) if athlete_id else None
            elif isinstance(cell, str) and re.match(r"^\d{1,2}:\d{2}(:\d{2})?$", cell):
                secs = parse_elapsed_to_seconds(cell)
            elif isinstance(cell, str) and len(cell) > 2 and not cell.isdigit():
                athlete_name = athlete_name or cell
        if athlete_name and secs:
            efforts.append({
                "strava_athlete_id": athlete_id,
                "athlete_name_raw": athlete_name,
                "elapsed_time_sec": secs,
                "is_kom_qom": False,
            })

    return {"segment_name": name or f"Segmento {segment_id}", "efforts": efforts}


def post_sync(
    api_base: str, admin_key: str, stage_id: int, segment_id: str, payload: Dict[str, object]
) -> None:
    body = {
        "strava_segment_id": segment_id,
        "segment_name": payload.get("segment_name", f"Segmento {segment_id}"),
        "distance_m": payload.get("distance_m", 0.0),
        "average_grade": payload.get("average_grade", 0.0),
        "efforts": payload.get("efforts", []),
    }
    res = httpx.post(
        f"{api_base}/stages/{stage_id}/sync-strava-efforts",
        json=body,
        headers={"X-Admin-Key": admin_key},
        timeout=60,
    )
    res.raise_for_status()
    print(f"  stage {stage_id} · segmento {segment_id}: {res.json()}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Scraping local de Strava por CDP")
    parser.add_argument("--stage", type=int, required=True, help="stage_id destino")
    parser.add_argument("--segment", action="append", default=[], help="strava_segment_id (repetible)")
    parser.add_argument("--segment-name", default=None)
    parser.add_argument("--activity", default=None, help="URL de actividad para descubrir segmentos")
    parser.add_argument("--date", default="today", help="today | this_month | all ...")
    parser.add_argument("--api-base", default=API_BASE_DEFAULT)
    # La clave sale del entorno: nunca esta en el repositorio.
    parser.add_argument(
        "--admin-key",
        default=os.environ.get("ADMIN_API_KEY", "").strip(),
        help="Clave de administrador (por defecto, la variable de entorno ADMIN_API_KEY).",
    )
    args = parser.parse_args()

    pw, _browser, context = _connect()
    page = context.new_page()
    try:
        segment_specs: List[Dict[str, str]] = []
        if args.activity:
            print(f"Descubriendo segmentos de la actividad {args.activity}...")
            segment_specs.extend(discover_segments_from_activity(page, args.activity))
        for sid in args.segment:
            segment_specs.append({"strava_segment_id": sid, "name": args.segment_name or f"Segmento {sid}"})

        if not segment_specs:
            print("Nada que hacer: indica --segment o --activity.", file=sys.stderr)
            raise SystemExit(1)

        for spec in segment_specs:
            print(f"Scrapeando segmento {spec['strava_segment_id']} ({spec['name']})...")
            data = scrape_segment_leaderboard(page, spec["strava_segment_id"], args.date)
            data["segment_name"] = spec["name"] or data["segment_name"]
            post_sync(args.api_base, args.admin_key, args.stage, spec["strava_segment_id"], data)
    finally:
        page.close()
        pw.stop()


if __name__ == "__main__":
    main()
