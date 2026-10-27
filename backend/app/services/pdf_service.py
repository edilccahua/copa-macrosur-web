import io
import re
from typing import List, Dict, Any, Union
from pypdf import PdfReader


def parse_time_to_ms(time_val: Any) -> int:
    """Convierte formato H:MM:SS, HH:MM:SS o HH:MM:SS.mmm o datetime.time a milisegundos enteros."""
    if not time_val:
        return 0
    if hasattr(time_val, "hour") and hasattr(time_val, "minute") and hasattr(time_val, "second"):
        micro = getattr(time_val, "microsecond", 0)
        return ((time_val.hour * 3600) + (time_val.minute * 60) + time_val.second) * 1000 + (micro // 1000)
    time_str = str(time_val).strip()
    parts = time_str.split(":")
    if len(parts) != 3:
        return 0
    try:
        hours = int(parts[0])
        minutes = int(parts[1])
        sec_parts = parts[2].split(".")
        seconds = int(sec_parts[0])
        millis = int(sec_parts[1].ljust(3, "0")[:3]) if len(sec_parts) > 1 else 0
    except (ValueError, IndexError):
        return 0
    return ((hours * 3600) + (minutes * 60) + seconds) * 1000 + millis


def format_ms_to_time(ms: int) -> str:
    """Convierte milisegundos a HH:MM:SS."""
    if not ms or ms < 0:
        return "--:--:--"
    total_sec = ms // 1000
    hours = total_sec // 3600
    minutes = (total_sec % 3600) // 60
    seconds = total_sec % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


# Renglón de resultado tolerante a dos familias de PDF del organizador:
#  - La Joya: campos separados por espacios (pypdf conserva columnas).
#      "  1   PATRICIO RATH DIAZ   LIBRE   EBIKE  01:16:22  10  1"
#  - ZETA:    celdas "pegadas" (dorsal+nombres, categoría+tiempo, tiempo+puntos):
#      "3DIEGO ARMANDO VILLALOBOS CODOCEOJALLALLA BIKE ELITE 1:08:5210 1"
#
# Un renglón NO siempre cabe en una sola línea: cuando el nombre o el club son largos,
# pypdf corta la fila y la continúa en las líneas siguientes (p.ej. La Joya dorsal 11):
#      "11 CHARLES GONZALES CLUB ORIGINAL BIKES AREQUIPA-"
#      "PERÚ ELITE 01:10:43 9 2"
# Por eso el parseo es en dos pasos:
#   1. ROW_START_RE localiza el dorsal que ABRE el renglón.
#   2. Se concatenan las líneas siguientes hasta encontrar la cola
#      ROW_TAIL_RE (tiempo + puntos + puesto) que cierra el renglón.
# La cola está anclada al final ($) y la hora se acota a 00-23, así el caso
# "15 - 17"+"1:04:30" -> "15 - 171:04:30" toma "1:04:30" sin comerse los ceros
# iniciales de "01:xx:xx".
ROW_START_RE = re.compile(r"^(\d{1,4})(?=\D)")
ROW_TAIL_RE = re.compile(
    r"((?:[01]?\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d+)?)\s*(\d{1,3})\s+(\d{1,3})\s*$"
)

# Líneas de cabecera repetidas por bloque de categoría y títulos de página (se ignoran).
HEADER_TOKENS = (
    "DORSAL", "NOMBRE", "T. TOTAL", "T.TOTAL", "PUNTOS", "PUESTO",
    "INSCRITOS", "RESULTADOS", "CLASIFICACION",
)

# Un club partido por el salto de línea del PDF queda como "AREQUIPA- PERÚ".
# Se colapsa el espacio alrededor del guion SOLO cuando sigue una letra, para no
# tocar la categoría "JUVENILES 15 - 17" (guion seguido de dígito).
_HYPHEN_SPACE_RE = re.compile(r"-\s+(?=[A-ZÁÉÍÓÚÑ])")


def collapse_team_hyphen(text: str) -> str:
    """Normaliza 'CLUB X- PERÚ' -> 'CLUB X-PERÚ' sin tocar '15 - 17'."""
    return _HYPHEN_SPACE_RE.sub("-", text or "")


def _is_chrome_line(text: str) -> bool:
    """C True si la línea es cabecera de tabla o título de página (no es un renglón)."""
    upper = text.upper()
    return any(token in upper for token in HEADER_TOKENS)


def _extract_text_lines(pdf_file) -> List[str]:
    reader = PdfReader(pdf_file)
    lines: List[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        lines.extend(text.splitlines())
    return lines


def _iter_result_rows(lines: List[str]):
    """
    Reconstruye los renglones lógicos del PDF uniendo las líneas partidas.

    Devuelve dicts: {bib_number, raw_info, time_str, elapsed_ms, points, rank}.
    """
    buffer: Optional[Dict[str, Any]] = None

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        if _is_chrome_line(line):
            # Cabecera/título: nunca forma parte de un renglón.
            continue

        start = ROW_START_RE.match(line)
        if start:
            # Un dorsal abre un renglón nuevo: el anterior queda incompleto.
            buffer = {
                "bib_number": int(start.group(1)),
                "text": line,
                "head": line[start.end():],
                "bib_len": start.end(),
            }
        else:
            if buffer is None:
                # Continuación sin renglón abierto: se ignora.
                continue
            buffer["text"] += " " + line
            buffer["head"] += " " + line

        tail = ROW_TAIL_RE.search(buffer["text"])
        if tail:
            # `tail.start()` está en coordenadas de `text`; el `head` empieza
            # después del dorsal, así que se resta el largo del prefijo.
            head_cut = tail.start() - buffer["bib_len"]
            yield {
                "bib_number": buffer["bib_number"],
                "raw_info": buffer["head"][:head_cut].strip(),
                "time_str": tail.group(1),
                "points": int(tail.group(2)),
                "rank": int(tail.group(3)),
            }
            buffer = None



def extract_race_results_from_pdf(
    pdf_source: Union[str, bytes, bytearray, io.BytesIO]
) -> List[Dict[str, Any]]:
    """
    Parsea un PDF oficial de resultados (formatos La Joya o ZETA).

    Retorna, ordenado por dorsal y SIN duplicados, una lista de:
    [{ bib_number, raw_info, time_str, elapsed_ms, points, rank }]

    Regla de duplicados (acordada): si un mismo dorsal aparece más de una vez
    en el PDF, se conserva el MEJOR tiempo (menor elapsed_ms).
    """
    own_file = False
    if isinstance(pdf_source, (bytes, bytearray)):
        pdf_file = io.BytesIO(pdf_source)
    elif isinstance(pdf_source, io.BytesIO):
        pdf_file = pdf_source
    else:
        pdf_file = open(pdf_source, "rb")
        own_file = True

    try:
        by_bib: Dict[int, Dict[str, Any]] = {}
        for row in _iter_result_rows(_extract_text_lines(pdf_file)):
            bib_number = row["bib_number"]
            elapsed_ms = parse_time_to_ms(row["time_str"])
            # Sanity check: descarta tiempos imposibles (protección ante líneas corruptas)
            if elapsed_ms <= 0 or elapsed_ms > 12 * 3600 * 1000:
                continue

            candidate = {
                "bib_number": bib_number,
                "raw_info": collapse_team_hyphen(row["raw_info"]),
                "time_str": row["time_str"],
                "elapsed_ms": elapsed_ms,
                "points": row["points"],
                "rank": row["rank"],
            }

            existing = by_bib.get(bib_number)
            if existing is None or elapsed_ms < existing["elapsed_ms"]:
                by_bib[bib_number] = candidate

        return [by_bib[bib] for bib in sorted(by_bib.keys())]
    finally:
        if own_file and not isinstance(pdf_file, io.BytesIO):
            pdf_file.close()
