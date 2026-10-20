"""
Generador del perfil de etapa de una carrera.

Produce un SVG con la silueta de la ruta, los puertos con su categoría, los
checkpoints, la escala de altitudes en msnm y el eje de kilometraje. Es la
pieza que el navegador dibujaba antes, pero aqui se calcula una vez, con la
tipografia del sistema (Geist Mono para las cifras, Archivo para los rotulos)
y un tamaño razonable.

El SVG lleva las fuentes como `<style>` con `font-family`, y el sitio las
sirve autoalojadas, asi que el texto se ve igual que en el resto del portal.

Uso:
    python3 -m backend.scripts.build_stage_profile <slug> [salida.svg]
"""
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.services.route_profile_service import (  # noqa: E402
    _coords_from_geojson,
    _smooth_elevations,
    extract_summits,
)

# Lienzo. Ancho suficiente para las etiquetas de puerto sin subir la altura.
# Se dibuja a 2x de la caja final (la imagen ocupa ~760 px en el portal) para
# que el texto de las etiquetas se lea a ese tamaño.
W = 2400
H = 900
# La franja de los puertos arriba, la banda de kilometraje abajo.
PORT_BAND = 150
KM_BAND = 80
PLOT_TOP = PORT_BAND
PLOT_BOTTOM = H - KM_BAND
PLOT_H = PLOT_BOTTOM - PLOT_TOP
PAD_L = 110
PAD_R = 60
PLOT_W = W - PAD_L - PAD_R

# Categorias de puerto, con su color (los mismos del perfil de etapa).
CATEGORY_COLORS = {
    "HC": "#e0368f",
    "1": "#e0368f",
    "2": "#f26b1d",
    "3": "#2f7bf5",
    "4": "#7bb51c",
    "": "#70707c",
}

# El acento del portal.
ACCENT = "#2d81ff"
INK = "#f2f1ee"
MUTED = "#f2f1ee99"
FAINT = "#f2f1ee61"
LINE = "#f2f1ee26"
SURFACE = "#101014"


def _esc(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _fmt(value: float) -> str:
    """Cifra con punto decimal, sin ceros sobrantes."""
    return f"{value:.1f}".rstrip("0").rstrip(".")


def build_profile_svg(
    route_geojson: Optional[Dict[str, Any]],
    summits: List[Dict[str, Any]],
    checkpoints: List[Dict[str, Any]],
    *,
    stage_name: str = "",
    distance_km: float = 0.0,
    elevation_gain_m: int = 0,
    elevation_loss_m: int = 0,
) -> str:
    """Construye el SVG del perfil de etapa."""
    coords = _coords_from_geojson(route_geojson)
    if len(coords) < 2:
        return ""

    elevations = _smooth_elevations(coords)
    eles = [c[2] for c in coords]
    kms = [c[3] for c in coords]
    min_ele = min(eles)
    max_ele = max(eles)
    # El rango se redondea a decenas para que las lineas de msnm salgan limpias.
    lo = (int(min_ele) // 50) * 50
    hi = ((int(max_ele) // 50) + 1) * 50
    if hi <= lo:
        hi = lo + 50
    span = hi - lo

    total_km = kms[-1] - kms[0] or 1.0

    # El desnivel acumulado real: el positivo y el negativo, tramo a tramo. Es
    # lo que cuenta un GPS, no la diferencia entre el máximo y el mínimo.
    gain = 0.0
    loss = 0.0
    for index in range(len(elevations) - 1):
        delta = elevations[index + 1] - elevations[index]
        if delta > 0:
            gain += delta
        else:
            loss -= delta
    computed_gain = int(round(gain))
    computed_loss = int(round(loss))

    def x_of(km: float) -> float:
        return PAD_L + ((km - kms[0]) / total_km) * PLOT_W

    def y_of(ele: float) -> float:
        return PLOT_BOTTOM - ((ele - lo) / span) * PLOT_H

    parts: List[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'preserveAspectRatio="xMidYMid meet" role="img" '
        f'aria-label="Perfil de altimetría de {_esc(stage_name)}">'
    )
    parts.append(
        "<style>"
        "text{font-family:'Archivo Variable',system-ui,sans-serif}"
        ".mono{font-family:'Geist Mono Variable',ui-monospace,monospace;"
        "font-variant-numeric:tabular-nums}"
        "</style>"
    )
    parts.append(f'<rect width="{W}" height="{H}" fill="{SURFACE}"/>')

    # ── Retícula de altitudes (msnm) ──────────────────────────────────────
    step = max(1, int(round((hi - lo) / 4 / 50.0))) * 50
    value = lo
    while value <= hi:
        y = y_of(value)
        parts.append(
            f'<line x1="{PAD_L}" y1="{y:.1f}" x2="{W - PAD_R}" y2="{y:.1f}" '
            f'stroke="{LINE}" stroke-width="1.5"/>'
        )
        parts.append(
            f'<text x="{PAD_L - 12}" y="{y + 4:.1f}" class="mono" font-size="19" '
            f'fill="{FAINT}" text-anchor="end">{value}</text>'
        )
        value += step

    # ── Silueta ───────────────────────────────────────────────────────────
    points = " ".join(
        f"{x_of(km):.1f},{y_of(ele):.1f}"
        for km, ele in zip(kms, elevations)
    )
    area = (
        f"M {x_of(kms[0]):.1f},{PLOT_BOTTOM} L {points.replace(' ', ' L ')} "
        f"L {x_of(kms[-1]):.1f},{PLOT_BOTTOM} Z"
    )
    parts.append(f'<path d="{area}" fill="{ACCENT}" fill-opacity="0.18"/>')
    parts.append(
        f'<path d="M {points.replace(" ", " L ")}" fill="none" stroke="{ACCENT}" '
        f'stroke-width="3" stroke-linejoin="round"/>'
    )

    # ── Checkpoints ───────────────────────────────────────────────────────
    # La etiqueta va EN la banda de kilometraje, sobre el numero, para que no
    # se pise con el eje.
    for checkpoint in checkpoints:
        km = checkpoint.get("distance_from_start_km", 0.0)
        if km > total_km + 0.5:
            continue
        # el punto de la traza mas cercano a ese kilometro
        index = min(range(len(kms)), key=lambda i: abs(kms[i] - km))
        x = x_of(kms[index])
        y = y_of(elevations[index])
        parts.append(
            f'<line x1="{x:.1f}" y1="{PLOT_TOP}" x2="{x:.1f}" y2="{PLOT_BOTTOM}" '
            f'stroke="{MUTED}" stroke-width="1.5" stroke-dasharray="3 4"/>'
        )
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="{SURFACE}" '
            f'stroke="{INK}" stroke-width="2.2"/>'
        )
        parts.append(
            f'<text x="{x:.1f}" y="{H - KM_BAND + 40}" font-size="17" fill="{MUTED}" '
            f'text-anchor="middle">{_esc(checkpoint.get("name", ""))}</text>'
        )

    # ── Puertos: bandera con la categoria, nombre y cifras ───────────────
    # Se reparten en tres alturas para que las etiquetas no se pisen.
    ordered = sorted(summits, key=lambda s: s.get("distance_km", 0.0))
    for index, summit in enumerate(ordered):
        km = summit.get("distance_km", 0.0)
        if km > total_km + 0.5:
            continue
        point_index = min(range(len(kms)), key=lambda i: abs(kms[i] - km))
        x = x_of(kms[point_index])
        y = y_of(elevations[point_index])
        tier = index % 3
        box_y = 24 + tier * 42
        color = CATEGORY_COLORS.get(summit.get("category", ""), CATEGORY_COLORS[""])
        label = summit.get("category") or "·"

        parts.append(
            f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{x:.1f}" y2="{box_y + 27}" '
            f'stroke="{color}" stroke-width="1.5" stroke-dasharray="2 3"/>'
        )
        # La bandera: un rectangulo con la categoria.
        parts.append(
            f'<rect x="{x - 22:.1f}" y="{box_y}" width="45" height="27" fill="{color}"/>'
        )
        parts.append(
            f'<text x="{x:.1f}" y="{box_y + 19}" class="mono" font-size="17" '
            f'font-weight="700" fill="{SURFACE}" text-anchor="middle">{_esc(label)}</text>'
        )
        # El nombre y las cifras, a la izquierda de la bandera.
        parts.append(
            f'<text x="{x - 32:.1f}" y="{box_y + 19}" font-size="20" font-weight="620" '
            f'fill="{INK}" text-anchor="end">{_esc(summit.get("name", ""))}</text>'
        )
        parts.append(
            f'<text x="{x - 32:.1f}" y="{box_y + 34}" class="mono" font-size="15" '
            f'fill="{FAINT}" text-anchor="end">'
            f'{_fmt(summit.get("distance_km", 0))} KM · {int(summit.get("elevation_m", 0))} M '
            f'· +{int(summit.get("climb_gain_m", 0))} M</text>'
        )

    # ── Banda de kilometraje ──────────────────────────────────────────────
    parts.append(
        f'<rect x="{PAD_L}" y="{H - KM_BAND}" width="{PLOT_W}" height="{KM_BAND}" '
        f'fill="#060607"/>'
    )
    km_step = 10 if total_km > 40 else (5 if total_km > 15 else 2)
    km = 0.0
    while km <= total_km + 0.01:
        x = x_of(km)
        parts.append(
            f'<line x1="{x:.1f}" y1="{H - KM_BAND}" x2="{x:.1f}" y2="{H - KM_BAND + 8}" '
            f'stroke="{MUTED}" stroke-width="1.5"/>'
        )
        parts.append(
            f'<text x="{x:.1f}" y="{H - KM_BAND + 26}" class="mono" font-size="19" '
            f'fill="{MUTED}" text-anchor="middle">{int(km)}</text>'
        )
        km += km_step
    parts.append(
        f'<text x="{W - PAD_R}" y="{H - KM_BAND + 26}" class="mono" font-size="19" '
        f'fill="{FAINT}" text-anchor="end">KM</text>'
    )

    # ── Cabecera con las cifras de la ruta ────────────────────────────────
    parts.append(
        f'<text x="{PAD_L}" y="{H - 10}" class="mono" font-size="17" fill="{FAINT}">'
        f'DISTANCIA {_fmt(distance_km)} KM · DESNIVEL +{computed_gain} M / '
        f'-{computed_loss} M · ALTITUD {int(lo)}-{int(hi)} MSNM</text>'
    )

    parts.append("</svg>")
    return "".join(parts)


def main() -> int:
    if len(sys.argv) < 2:
        print("uso: python3 -m backend.scripts.build_stage_profile <slug> [salida.svg]")
        return 2

    slug = sys.argv[1]
    output = sys.argv[2] if len(sys.argv) > 2 else f"frontend/public/profiles/{slug}.svg"

    import sqlite3

    db_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "kuspide_mtb.db",
    )
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    row = con.execute(
        "SELECT route_geojson, distance_km, elevation_gain_m, laps, name, title "
        "FROM stages WHERE slug=?",
        (slug,),
    ).fetchone()
    if row is None:
        print(f"no hay fecha {slug}")
        return 1

    stage_row = con.execute(
        "SELECT id FROM stages WHERE slug=?", (slug,)
    ).fetchone()
    summits = [
        dict(r)
        for r in con.execute(
            "SELECT name, category, distance_km, elevation_m, climb_gain_m, "
            "avg_grade_pct, max_grade_pct FROM route_summits WHERE stage_id=? "
            "ORDER BY distance_km",
            (stage_row["id"],),
        )
    ]
    checkpoints = [
        dict(r)
        for r in con.execute(
            "SELECT name, distance_from_start_km, is_finish_line FROM checkpoints "
            "WHERE stage_id=? ORDER BY order_index",
            (stage_row["id"],),
        )
    ]

    svg = build_profile_svg(
        json.loads(row["route_geojson"]) if row["route_geojson"] else None,
        summits,
        checkpoints,
        stage_name=row["title"] or row["name"],
        distance_km=float(row["distance_km"] or 0) * max(1, row["laps"] or 1),
        elevation_gain_m=int(row["elevation_gain_m"] or 0) * max(1, row["laps"] or 1),
        elevation_loss_m=0,
    )
    if not svg:
        print(f"la fecha {slug} no tiene geometría")
        return 1

    os.makedirs(os.path.dirname(output), exist_ok=True)
    with open(output, "w", encoding="utf-8") as handle:
        handle.write(svg)
    print(f"perfil generado: {output} ({len(svg)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
