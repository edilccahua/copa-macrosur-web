import io
import re
from typing import List, Dict, Any, Union
from pypdf import PdfReader


def parse_time_to_ms(time_str: str) -> int:
    """Convierte formato HH:MM:SS o HH:MM:SS.mmm a milisegundos enteros."""
    parts = time_str.strip().split(":")
    if len(parts) != 3:
        return 0
    hours = int(parts[0])
    minutes = int(parts[1])
    sec_parts = parts[2].split(".")
    seconds = int(sec_parts[0])
    millis = int(sec_parts[1].ljust(3, "0")[:3]) if len(sec_parts) > 1 else 0
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


def extract_race_results_from_pdf(pdf_source: Union[str, bytes, io.BytesIO]) -> List[Dict[str, Any]]:
    """
    Parsea el PDF oficial de resultados de carrera (ej. LA JOYA EXTREME).
    Retorna lista de diccionarios:
    [{ bib_number: int, raw_info: str, time_str: str, elapsed_ms: int, points: int, rank: int }]
    """
    if isinstance(pdf_source, (bytes, bytearray)):
        pdf_file = io.BytesIO(pdf_source)
    elif isinstance(pdf_source, io.BytesIO):
        pdf_file = pdf_source
    else:
        pdf_file = open(pdf_source, "rb")

    reader = PdfReader(pdf_file)
    results = []

    for page in reader.pages:
        text = page.extract_text()
        if not text:
            continue
        for line in text.split("\n"):
            line = line.strip()
            # Formato estándar de fila de llegada: DORSAL ... TIEMPO PUNTOS PUESTO
            m = re.match(r"^(\d+)\s+(.+?)\s+(\d{1,2}:\d{2}:\d{2}(?:\.\d+)?)\s+(\d+)\s+(\d+)$", line)
            if m:
                bib_number = int(m.group(1))
                raw_info = m.group(2).strip()
                time_str = m.group(3)
                points = int(m.group(4))
                rank = int(m.group(5))
                elapsed_ms = parse_time_to_ms(time_str)

                results.append({
                    "bib_number": bib_number,
                    "raw_info": raw_info,
                    "time_str": time_str,
                    "elapsed_ms": elapsed_ms,
                    "points": points,
                    "rank": rank
                })

    if isinstance(pdf_source, str) and not isinstance(pdf_file, io.BytesIO):
        pdf_file.close()

    return results
