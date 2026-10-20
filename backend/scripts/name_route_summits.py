"""
Restaura los nombres reales de las cimas de la ruta.

El nombre sale del reverse-geocode de OpenStreetMap (Nominatim) sobre la
coordenada de la cima. El seed crea las cimas con un nombre derivado de la
geometria ("CIMA 2168 MSNM"); este script lo sustituye por el nombre real del
lugar y lo deja fijo en la BD, para que el seed siga siendo idempotente.

Se ejecuta una vez, al sembrar. La red NO se consulta en cada request.
"""
import json
import os
import sqlite3
import sys
import time
import urllib.request

DB = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "kuspide_mtb.db",
)
UA = "kuspide-mtb/1.0 (https://kuspide.pe)"
NOMINATIM = "https://nominatim.openstreetmap.org/reverse"


def reverse(lat: float, lon: float):
    """Nombre del lugar de una coordenada, vía Nominatim."""
    url = f"{NOMINATIM}?format=jsonv2&zoom=14&lat={lat}&lon={lon}&addressdetails=1"
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        print(f"    ! no se pudo geocodificar ({exc})", file=sys.stderr)
        return None

    address = data.get("address") or {}
    name = (
        data.get("name")
        or address.get("road")
        or address.get("neighbourhood")
        or address.get("suburb")
        or address.get("village")
        or address.get("town")
        or address.get("city")
        or address.get("hamlet")
    )
    if not name:
        display = data.get("display_name") or ""
        name = display.split(",")[0].strip() or None
    return name


def main() -> int:
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT id, name, lat, lon FROM route_summits WHERE name_source='geo' "
        "AND lat IS NOT NULL ORDER BY id"
    ).fetchall()
    print(f"{len(rows)} cimas sin nombre real", file=sys.stderr)

    for summit_id, current, lat, lon in rows:
        name = reverse(lat, lon)
        if not name:
            continue
        con.execute(
            "UPDATE route_summits SET name=?, name_source='osm' WHERE id=?",
            (name, summit_id),
        )
        print(f"  {current} -> {name}", file=sys.stderr)
        con.commit()
        # Nominatim pide no pedir más de 1 vez por segundo.
        time.sleep(1.1)

    con.commit()
    print("\n--- cimas finales ---")
    for row in con.execute(
        """SELECT s.slug, r.name, r.category, r.distance_km, r.elevation_m
           FROM route_summits r JOIN stages s ON s.id=r.stage_id
           ORDER BY s.stage_number, r.distance_km"""
    ):
        print(f"  {row[0]:22} {row[1][:28]:30} cat {row[2] or '-':2} km {row[3]:6.2f} {row[4]:5}m")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
