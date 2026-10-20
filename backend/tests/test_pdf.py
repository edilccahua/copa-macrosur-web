import io
import os
import pytest

from backend.app.services.pdf_service import (
    extract_race_results_from_pdf,
    parse_time_to_ms,
    format_ms_to_time,
)

RACES_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "races")
LA_JOYA_PDF = os.path.join(RACES_DIR, "1. LA JOYA EXTREME 2026  RESULTADOS.pdf")
ZETA_PDF = os.path.join(RACES_DIR, "LA Z XTREME 2026 - RESULTADOS.-1.pdf")


def test_parse_time_to_ms_accepts_single_and_double_digit_hour():
    assert parse_time_to_ms("1:04:30") == 3870000
    assert parse_time_to_ms("01:04:30") == 3870000
    assert parse_time_to_ms("01:16:22") == 4582000
    assert parse_time_to_ms("") == 0
    assert parse_time_to_ms("basura") == 0


def test_format_ms_to_time_roundtrip():
    assert format_ms_to_time(3870000) == "01:04:30"


# ---- Formato ZETA: celdas "pegadas" (dorsal+nombre, categoría+tiempo, tiempo+puntos) ----
ZETA_LIKE_TEXT = (
    "DORSALNOMBRE TEAM E-BIKE OPENT. TOTALPUNTOSPUESTO\n"
    "3DIEGO ARMANDO VILLALOBOS CODOCEOJALLALLA BIKE -ARICA CHILE EBIKE 1:08:5210 1\n"
    "4PATRICIO RATH DIAZ LIBRE EBIKE 1:10:349 2\n"
    "234MILDER CRISTHIAN CHAPI HUARAYATEAM COLCA BIKE JUVENILES 15 - 171:04:309 2\n"
)


class _FakePage:
    def __init__(self, text):
        self._text = text

    def extract_text(self, *args, **kwargs):
        return self._text


def _patch_reader(monkeypatch, text):
    import backend.app.services.pdf_service as mod

    class _FakeReader:
        def __init__(self, _):
            self.pages = [_FakePage(text)]

    monkeypatch.setattr(mod, "PdfReader", _FakeReader)


def test_zeta_glued_format_and_category_glued_to_time(monkeypatch):
    _patch_reader(monkeypatch, ZETA_LIKE_TEXT)
    results = extract_race_results_from_pdf(io.BytesIO(b"%PDF-fake"))
    by_bib = {r["bib_number"]: r for r in results}

    assert by_bib[3]["elapsed_ms"] == parse_time_to_ms("1:08:52")
    assert by_bib[4]["elapsed_ms"] == parse_time_to_ms("1:10:34")
    # La categoría "JUVENILES 15 - 17" se pega al tiempo: debe resolverse a 1:04:30
    assert by_bib[234]["time_str"] == "1:04:30"
    assert by_bib[234]["elapsed_ms"] == 3870000


@pytest.mark.skipif(not os.path.exists(LA_JOYA_PDF), reason="dataset races/ no disponible")
def test_real_la_joya_pdf_extraction_and_duplicate_resolution():
    results = extract_race_results_from_pdf(LA_JOYA_PDF)
    bibs = [r["bib_number"] for r in results]
    # Dorsales únicos (el dorsal 161 aparece 2 veces en el PDF original)
    assert len(bibs) == len(set(bibs))
    # Cifra oficial verificada con dos oráculos independientes (pdfplumber por
    # coordenadas y pdftotext -raw): el PDF de La Joya trae 198 resultados.
    assert len(results) == 198
    # El dorsal 161 se queda con el MEJOR tiempo (1:31:15), no con 1:43:23
    by_bib = {r["bib_number"]: r for r in results}
    assert by_bib[161]["time_str"] == "01:31:15"


@pytest.mark.skipif(not os.path.exists(LA_JOYA_PDF), reason="dataset races/ no disponible")
def test_real_la_joya_pdf_keeps_rows_split_over_several_lines():
    """
    pypdf entrega el PDF de La Joya partido en varias líneas por fila cuando el
    nombre o el equipo son largos. Ninguna fila puede perderse por eso.
    """
    results = extract_race_results_from_pdf(LA_JOYA_PDF)
    by_bib = {r["bib_number"]: r for r in results}

    # Dorsal 11: el equipo "CLUB ORIGINAL BIKES AREQUIPA-PERÚ" cae a la línea siguiente.
    assert by_bib[11]["time_str"] == "01:10:43"
    assert by_bib[11]["points"] == 9
    assert by_bib[11]["rank"] == 2
    assert "CHARLES GONZALES" in by_bib[11]["raw_info"]
    assert by_bib[11]["raw_info"].upper().rstrip().endswith("ELITE")

    # Dorsal 14: el NOMBRE cae a la línea siguiente.
    assert by_bib[14]["time_str"] == "01:19:12"
    assert "ANTHONY JOEL MAMANI" in by_bib[14]["raw_info"]
    assert by_bib[14]["raw_info"].upper().rstrip().endswith("ELITE")

    # Dorsal 42: nombre partido ("JUAN AGUSTIN FERNANDEZ / SANTOS").
    assert by_bib[42]["time_str"] == "01:21:59"
    assert "JUAN AGUSTIN FERNANDEZ" in by_bib[42]["raw_info"]
    assert "SANTOS" in by_bib[42]["raw_info"]

    # Dorsal 186: existe SOLO en el PDF (no está en el Excel de inscritos).
    assert by_bib[186]["time_str"] == "01:15:59"
    assert by_bib[186]["points"] == 10


@pytest.mark.skipif(not os.path.exists(LA_JOYA_PDF), reason="dataset races/ no disponible")
def test_real_la_joya_pdf_points_match_the_official_scale():
    """Suma de puntos del PDF oficial = 667 (verificado con oráculo layout-aware)."""
    results = extract_race_results_from_pdf(LA_JOYA_PDF)
    assert sum(r["points"] for r in results) == 667


@pytest.mark.skipif(not os.path.exists(ZETA_PDF), reason="dataset races/ no disponible")
def test_real_zeta_pdf_extraction():
    results = extract_race_results_from_pdf(ZETA_PDF)
    bibs = [r["bib_number"] for r in results]
    assert len(bibs) == len(set(bibs))
    # Cifra oficial verificada con dos oráculos independientes: 112 resultados, 554 puntos.
    assert len(results) == 112
    assert sum(r["points"] for r in results) == 554
    # Ningún tiempo absurdo (todas las carreras duran menos de 6h)
    assert all(r["elapsed_ms"] < 6 * 3600 * 1000 for r in results)
