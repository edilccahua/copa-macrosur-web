"""
Generador del perfil de etapa de una carrera (Estilo Tour de France).

Produce un SVG de alta definición, responsive y de alto contraste con:
  · Canvas de escala óptima (1100 x 440 px) para nitidez en pantallas de escritorio y móviles.
  · Soporte dinámico para modo CLARO y modo OSCURO mediante tokens nativos (--bg, --ink, --line, --accent).
  · Tipografía oficial: Archivo Variable para títulos/etiquetas y Geist Mono Variable con números tabulares.
  · Silueta montañosa con gradiente sutil y cresta nítida.
  · Trazado resaltado de puertos directamente sobre la pendiente de la montaña (de inicio a cumbre).
  · Líneas guía estrictamente verticales (x1 = x2) sin cruces diagonales ni superposiciones.
  · Iconografía vectorial SVG limpia para Salida, Llegada y Puertos (cero emojis).
  · Geometría angular estricta (--radius: 0) coherente con el sistema de diseño del proyecto.

Uso:
    python3 -m backend.scripts.build_stage_profile <slug> [salida.svg]
"""
import json
import os
import sys
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.services.route_profile_service import (  # noqa: E402
    _coords_from_geojson,
    _smooth_elevations,
)

# Dimensiones del lienzo (relación ~2.5:1, proporción ideal para contenedores web y móviles)
W = 1100
H = 440

PAD_L = 64
PAD_R = 64
PLOT_TOP = 84
KM_BAND = 44
PLOT_BOTTOM = H - KM_BAND
PLOT_H = PLOT_BOTTOM - PLOT_TOP
PLOT_W = W - PAD_L - PAD_R

# Colores de categoría al estilo del ciclismo profesional
CATEGORY_COLORS = {
    "HC": "#e11d48",  # Carmesí
    "1": "#e11d48",
    "2": "#ea580c",   # Naranja
    "3": "#2d81ff",   # Azul Kúspide / Accent
    "4": "#059669",   # Verde Esmeralda
    "": "#f59e0b",    # Ámbar dorado
}


def _esc(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _fmt(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".")


def build_profile_svg(
    route_geojson: Optional[Dict[str, Any]],
    summits: List[Dict[str, Any]],
    checkpoints: Optional[List[Dict[str, Any]]] = None,
    *,
    stage_name: str = "",
    start_location: str = "",
    finish_location: str = "",
    distance_km: float = 0.0,
    elevation_gain_m: int = 0,
    elevation_loss_m: int = 0,
) -> str:
    """Construye el SVG del perfil de etapa responsive y con tokens de diseño del sitio."""
    coords = _coords_from_geojson(route_geojson)
    if len(coords) < 2:
        return ""

    elevations = _smooth_elevations(coords, window=5)
    kms = [c[3] for c in coords]
    min_ele = min(elevations)
    max_ele = max(elevations)

    # Redondeo de escala vertical a múltiplos de 100 o 50
    lo = (int(min_ele) // 100) * 100
    hi = ((int(max_ele) // 100) + 1) * 100
    if hi - lo < 200:
        lo = max(0, lo - 50)
        hi += 100
    span = hi - lo

    total_km = kms[-1] - kms[0] or 1.0

    # Desnivel acumulado
    gain = 0.0
    loss = 0.0
    for idx in range(len(elevations) - 1):
        diff = elevations[idx + 1] - elevations[idx]
        if diff > 0:
            gain += diff
        else:
            loss -= diff
    computed_gain = int(round(gain))
    computed_loss = int(round(loss))
    if elevation_gain_m > 0:
        computed_gain = elevation_gain_m
    if elevation_loss_m > 0:
        computed_loss = elevation_loss_m

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
        "<defs>"
        "<linearGradient id='profileGrad' x1='0%' y1='0%' x2='0%' y2='100%'>"
        "<stop offset='0%' stop-color='var(--grad-top)' stop-opacity='var(--grad-top-op)'/>"
        "<stop offset='50%' stop-color='var(--grad-mid)' stop-opacity='var(--grad-mid-op)'/>"
        "<stop offset='100%' stop-color='var(--grad-bot)' stop-opacity='var(--grad-bot-op)'/>"
        "</linearGradient>"
        "<style>"
        ":root {"
        "  --bg: #121316;"
        "  --bg-raised: #101014;"
        "  --bg-sunken: #060607;"
        "  --line: rgba(242, 241, 238, 0.14);"
        "  --ink: #f2f1ee;"
        "  --ink-strong: #ffffff;"
        "  --muted: rgba(242, 241, 238, 0.60);"
        "  --faint: rgba(242, 241, 238, 0.40);"
        "  --accent: #2d81ff;"
        "  --crest: #2d81ff;"
        "  --crest-hi: #60a5fa;"
        "  --climb-accent: #f59e0b;"
        "  --axis-bg: #090a0f;"
        "  --axis-text: #f2f1ee;"
        "  --grad-top: #2d81ff;"
        "  --grad-top-op: 0.35;"
        "  --grad-mid: #1d4ed8;"
        "  --grad-mid-op: 0.16;"
        "  --grad-bot: #060607;"
        "  --grad-bot-op: 0.05;"
        "  --badge-bg: #101014;"
        "}"
        "@media (prefers-color-scheme: light) {"
        "  :root {"
        "    --bg: #f2f1ee;"
        "    --bg-raised: #faf9f7;"
        "    --bg-sunken: #e9e8e4;"
        "    --line: rgba(16, 16, 20, 0.16);"
        "    --ink: #101014;"
        "    --ink-strong: #000000;"
        "    --muted: rgba(16, 16, 20, 0.62);"
        "    --faint: rgba(16, 16, 20, 0.42);"
        "    --accent: #2d81ff;"
        "    --crest: #2563eb;"
        "    --crest-hi: #1d4ed8;"
        "    --climb-accent: #d97706;"
        "    --axis-bg: #e2e0da;"
        "    --axis-text: #101014;"
        "    --grad-top: #3b82f6;"
        "    --grad-top-op: 0.22;"
        "    --grad-mid: #93c5fd;"
        "    --grad-mid-op: 0.08;"
        "    --grad-bot: #f2f1ee;"
        "    --grad-bot-op: 0.02;"
        "    --badge-bg: #ffffff;"
        "  }"
        "}"
        "text{font-family:'Archivo Variable','Archivo',system-ui,-apple-system,sans-serif}"
        ".mono{font-family:'Geist Mono Variable','Geist Mono',ui-monospace,monospace;font-variant-numeric:tabular-nums}"
        "</style>"
        "</defs>"
    )

    # Fondo general
    parts.append(f'<rect width="{W}" height="{H}" fill="var(--bg)"/>')

    # ── Retícula horizontal de altitudes (MSNM) ───────────────────────────
    step = 200 if span >= 800 else (100 if span >= 300 else 50)
    current_ele = lo
    while current_ele <= hi:
        y = y_of(current_ele)
        parts.append(
            f'<line x1="{PAD_L}" y1="{y:.1f}" x2="{W - PAD_R}" y2="{y:.1f}" '
            f'stroke="var(--line)" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{PAD_L - 10}" y="{y + 4:.1f}" class="mono" font-size="11" '
            f'font-weight="600" fill="var(--muted)" text-anchor="end">{current_ele}</text>'
        )
        current_ele += step

    parts.append(
        f'<text x="{PAD_L - 10}" y="{PLOT_TOP - 8}" class="mono" font-size="9" '
        f'font-weight="700" fill="var(--faint)" text-anchor="end">MSNM</text>'
    )

    # ── Silueta montañosa (Estilo profesional) ────────────────────────────
    pts_str = " ".join(f"{x_of(km):.1f},{y_of(ele):.1f}" for km, ele in zip(kms, elevations))
    area_path = (
        f"M {x_of(kms[0]):.1f},{PLOT_BOTTOM} L {pts_str.replace(' ', ' L ')} "
        f"L {x_of(kms[-1]):.1f},{PLOT_BOTTOM} Z"
    )
    parts.append(f'<path d="{area_path}" fill="url(#profileGrad)"/>')
    parts.append(
        f'<path d="M {pts_str.replace(" ", " L ")}" fill="none" stroke="var(--crest)" '
        f'stroke-width="3" stroke-linejoin="round" stroke-linecap="square"/>'
    )
    parts.append(
        f'<path d="M {pts_str.replace(" ", " L ")}" fill="none" stroke="var(--crest-hi)" '
        f'stroke-width="1" stroke-linejoin="round" stroke-linecap="square"/>'
    )

    # ── Puertos de Montaña: Tramo resaltado en pendiente y Guía Vertical ──
    for idx, summit in enumerate(summits):
        s_km = summit.get("distance_km", 0.0)
        if s_km > total_km + 0.5:
            continue
        p_idx = min(range(len(kms)), key=lambda i: abs(kms[i] - s_km))
        sx = x_of(kms[p_idx])
        sy = y_of(elevations[p_idx])
        cat = str(summit.get("category", "") or "").strip()
        color = CATEGORY_COLORS.get(cat, CATEGORY_COLORS[""])

        # Longitud e inicio del puerto
        dist_climb = summit.get("climb_length_km")
        if not dist_climb:
            gain_m = summit.get("climb_gain_m", 0)
            avg_g = summit.get("avg_grade_pct", 0)
            dist_climb = round(gain_m / (avg_g * 10), 1) if avg_g > 0 else 0.0
        start_km = summit.get("start_km")
        if start_km is None:
            start_km = max(kms[0], round(s_km - dist_climb, 2))

        # 1. Resaltado del tramo de subida sobre la montaña (de inicio a cumbre)
        start_p_idx = min(range(len(kms)), key=lambda i: abs(kms[i] - start_km))
        if start_p_idx < p_idx:
            climb_segment_coords = [
                f"{x_of(kms[k]):.1f},{y_of(elevations[k]):.1f}"
                for k in range(start_p_idx, p_idx + 1)
            ]
            parts.append(
                f'<path d="M {" L ".join(climb_segment_coords)}" fill="none" '
                f'stroke="{color}" stroke-width="4.5" stroke-linecap="square" stroke-linejoin="round"/>'
            )
            start_x = x_of(kms[start_p_idx])
            start_y = y_of(elevations[start_p_idx])
            parts.append(
                f'<circle cx="{start_x:.1f}" cy="{start_y:.1f}" r="3" fill="{color}"/>'
            )

        # 2. Guía estrictamente vertical (x1 = x2) hacia la ficha superior
        tier = idx % 2
        flag_y = 18 + tier * 34
        line_top = flag_y + 24

        parts.append(
            f'<line x1="{sx:.1f}" y1="{sy:.1f}" x2="{sx:.1f}" y2="{line_top}" '
            f'stroke="{color}" stroke-width="1.5" stroke-dasharray="2 2"/>'
        )
        parts.append(
            f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="4" fill="#ffffff" '
            f'stroke="{color}" stroke-width="2"/>'
        )

        # Ficha técnica: Nombre, Altitud, Distancia y Pendiente media
        name_text = _esc(summit.get("name", "Puerto de Montaña"))
        ele_text = f"{int(summit.get('elevation_m', 0))} m"
        grade_text = f"{_fmt(dist_climb)} km al {_fmt(summit.get('avg_grade_pct', 0))}%"

        # Alineación para evitar que el texto se corte en bordes laterales
        align_right = sx > (W * 0.65)
        text_anchor = "end" if align_right else "start"
        badge_x = sx - 28 if align_right else sx + 6
        text_x = sx - 34 if align_right else sx + 36

        # Badge con categoría o icono vectorial de bandera
        parts.append(
            f'<rect x="{badge_x:.1f}" y="{flag_y}" width="22" height="18" '
            f'fill="{color}"/>'
        )
        if cat:
            parts.append(
                f'<text x="{badge_x + 11:.1f}" y="{flag_y + 13}" class="mono" font-size="10" '
                f'font-weight="800" fill="#ffffff" text-anchor="middle">{cat}</text>'
            )
        else:
            # Icono vectorial de bandera (puro SVG, cero emojis)
            parts.append(
                f'<path d="M {badge_x + 6} {flag_y + 4} L {badge_x + 6} {flag_y + 14} '
                f'M {badge_x + 6} {flag_y + 4} L {badge_x + 16} {flag_y + 7.5} L {badge_x + 6} {flag_y + 11} Z" '
                f'fill="#ffffff" stroke="#ffffff" stroke-width="0.8" stroke-linejoin="round"/>'
            )

        # Nombre del puerto y altitud en Archivo + Geist Mono
        parts.append(
            f'<text x="{text_x:.1f}" y="{flag_y + 11}" font-size="13" font-weight="700" '
            f'fill="var(--ink-strong)" text-anchor="{text_anchor}">'
            f'{name_text} <tspan class="mono" font-weight="800" fill="{color}">· {ele_text}</tspan></text>'
        )
        # Especificación de longitud y pendiente
        parts.append(
            f'<text x="{text_x:.1f}" y="{flag_y + 23}" class="mono" font-size="11" '
            f'font-weight="600" fill="var(--muted)" text-anchor="{text_anchor}">'
            f'{grade_text}</text>'
        )

    # ── Punto de Partida (Extremo Izquierdo) ──────────────────────────────
    start_x = x_of(kms[0])
    start_y = y_of(elevations[0])
    start_name = _esc(start_location or "Partida")
    start_ele_str = f"{int(round(elevations[0]))} m"

    parts.append(
        f'<line x1="{start_x:.1f}" y1="{start_y:.1f}" x2="{start_x:.1f}" y2="52" '
        f'stroke="var(--accent)" stroke-width="1.5" stroke-dasharray="2 2"/>'
    )
    parts.append(
        f'<circle cx="{start_x:.1f}" cy="{start_y:.1f}" r="4" fill="#ffffff" '
        f'stroke="var(--accent)" stroke-width="2"/>'
    )
    parts.append(
        f'<rect x="{start_x:.1f}" y="18" width="160" height="34" '
        f'fill="var(--badge-bg)" stroke="var(--accent)" stroke-width="1"/>'
    )
    # Icono vectorial de salida (triángulo / play)
    parts.append(
        f'<polygon points="{start_x + 10},{25} {start_x + 16},{29} {start_x + 10},{33}" '
        f'fill="var(--accent)"/>'
    )
    parts.append(
        f'<text x="{start_x + 22:.1f}" y="30" font-size="10" font-weight="800" '
        f'fill="var(--accent)">SALIDA · <tspan class="mono">{start_ele_str}</tspan></text>'
    )
    parts.append(
        f'<text x="{start_x + 10:.1f}" y="44" font-size="11" font-weight="700" '
        f'fill="var(--ink-strong)">{start_name}</text>'
    )

    # ── Punto de Meta (Extremo Derecho) ───────────────────────────────────
    finish_x = x_of(kms[-1])
    finish_y = y_of(elevations[-1])
    finish_name = _esc(finish_location or "Meta")
    finish_ele_str = f"{int(round(elevations[-1]))} m"

    parts.append(
        f'<line x1="{finish_x:.1f}" y1="{finish_y:.1f}" x2="{finish_x:.1f}" y2="52" '
        f'stroke="var(--climb-accent)" stroke-width="1.5" stroke-dasharray="2 2"/>'
    )
    parts.append(
        f'<circle cx="{finish_x:.1f}" cy="{finish_y:.1f}" r="4" fill="#ffffff" '
        f'stroke="var(--climb-accent)" stroke-width="2"/>'
    )
    parts.append(
        f'<rect x="{finish_x - 160:.1f}" y="18" width="160" height="34" '
        f'fill="var(--badge-bg)" stroke="var(--climb-accent)" stroke-width="1"/>'
    )
    # Icono vectorial de llegada a cuadros (cero emojis)
    parts.append(
        f'<g transform="translate({finish_x - 152}, 23)">'
        f'<rect width="4" height="4" fill="var(--climb-accent)"/>'
        f'<rect x="4" y="4" width="4" height="4" fill="var(--climb-accent)"/>'
        f'<rect x="4" width="4" height="4" fill="var(--ink-strong)"/>'
        f'<rect y="4" width="4" height="4" fill="var(--ink-strong)"/>'
        f'</g>'
    )
    parts.append(
        f'<text x="{finish_x - 140:.1f}" y="30" font-size="10" font-weight="800" '
        f'fill="var(--climb-accent)">LLEGADA · <tspan class="mono">{finish_ele_str}</tspan></text>'
    )
    parts.append(
        f'<text x="{finish_x - 152:.1f}" y="44" font-size="11" font-weight="700" '
        f'fill="var(--ink-strong)">{finish_name}</text>'
    )

    # ── Banda inferior de kilometraje (Eje X) ─────────────────────────────
    parts.append(
        f'<rect x="{PAD_L}" y="{PLOT_BOTTOM}" width="{PLOT_W}" height="{KM_BAND}" '
        f'fill="var(--axis-bg)" stroke="var(--line)" stroke-width="1"/>'
    )

    # Marcas regulares de distancia
    km_step = 10 if total_km > 35 else (5 if total_km > 15 else 2)
    cur_km = 0.0
    while cur_km <= total_km - (km_step * 0.4):
        kx = x_of(cur_km)
        parts.append(
            f'<line x1="{kx:.1f}" y1="{PLOT_BOTTOM}" x2="{kx:.1f}" y2="{PLOT_BOTTOM + 7}" '
            f'stroke="var(--muted)" stroke-width="1.2"/>'
        )
        parts.append(
            f'<text x="{kx:.1f}" y="{PLOT_BOTTOM + 22}" class="mono" font-size="11" '
            f'font-weight="700" fill="var(--axis-text)" text-anchor="middle">{int(cur_km)}</text>'
        )
        cur_km += km_step

    # Total de carrera destacado a la derecha
    total_km_str = f"{total_km:.1f} KM"
    parts.append(
        f'<rect x="{W - PAD_R - 86}" y="{PLOT_BOTTOM + 6}" width="86" height="24" '
        f'fill="var(--accent)"/>'
    )
    parts.append(
        f'<text x="{W - PAD_R - 43}" y="{PLOT_BOTTOM + 22}" class="mono" font-size="11" '
        f'font-weight="800" fill="#ffffff" text-anchor="middle">{total_km_str}</text>'
    )

    # Línea resumen compacta en la base
    parts.append(
        f'<text x="{PAD_L + 8}" y="{H - 8}" class="mono" font-size="10" font-weight="600" '
        f'fill="var(--muted)">'
        f'DISTANCIA: <tspan font-weight="700" fill="var(--ink-strong)">{_fmt(total_km)} KM</tspan>    '
        f'DESNIVEL: <tspan font-weight="700" fill="var(--ink-strong)">+{computed_gain} M / -{computed_loss} M</tspan>    '
        f'ALTITUD MÁX: <tspan font-weight="700" fill="var(--accent)">{int(round(max_ele))} MSNM</tspan>'
        f'</text>'
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
        "SELECT route_geojson, distance_km, elevation_gain_m, laps, name, title, start_location "
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

    start_loc = row["start_location"] or "Partida"
    finish_loc = "Meta Final"
    if slug == "la-joya-extreme":
        start_loc = "Cerro Colorado"
        finish_loc = "La Joya"
    elif slug == "z-xtreme-2026":
        start_loc = "Hacienda Luna"
        finish_loc = "Hacienda Luna"
    elif slug == "vuelta-a-los-poblados":
        start_loc = "Buena Vista"
        finish_loc = "Hacienda Luna"

    svg = build_profile_svg(
        json.loads(row["route_geojson"]) if row["route_geojson"] else None,
        summits,
        checkpoints=[],
        stage_name=row["title"] or row["name"],
        start_location=start_loc,
        finish_location=finish_loc,
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
