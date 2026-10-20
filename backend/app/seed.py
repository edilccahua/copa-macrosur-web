import asyncio
import datetime
import os
import shutil
from typing import Optional, List, Dict, Any

from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select

from backend.app.core.db import init_db, async_session_factory
from backend.app.models.entities import (
    Category, Stage, StageStatusEnum, StartWave, Checkpoint,
    Team, Rider, StageEntry, RaceStatusEnum, PaymentStatusEnum,
    SpecialAward, StravaSegment, StravaEffort, ExtraEvent, RouteSummit
)
from backend.app.services.excel_service import (
    import_riders_from_excel, resolve_category, resolve_or_create_team,
    generate_deterministic_dni, slugify, normalize_name,
)
from backend.app.services.pdf_service import extract_race_results_from_pdf, collapse_team_hyphen
from backend.app.services.gpx_service import parse_gpx_in_memory
from backend.app.services.scoring import (
    recalculate_stage_ranks, recalculate_championship_standings,
    recalculate_team_standings, merge_duplicate_entries
)


CATEGORIES_DEF = [
    {"name": "E-BIKE OPEN", "short_code": "EBK", "aliases": ["E-BIKE", "E-BIKE OPEN", "EBIKE"]},
    {"name": "ELITE", "short_code": "ELI", "aliases": ["ELITE", "ELITE (18-29 AÑOS)", "ELITE VARONES"]},
    {"name": "MASTER A", "short_code": "MSA", "aliases": ["MASTER A", "MASTER A (30-39 AÑOS)"]},
    {"name": "MASTER B", "short_code": "MSB", "aliases": ["MASTER B", "MASTER B (40-49 AÑOS)"]},
    {"name": "MASTER C", "short_code": "MSC", "aliases": ["MASTER C", "MASTER C (50-59 AÑOS)"]},
    {"name": "MASTER D", "short_code": "MSD", "aliases": ["MASTER D", "MASTER D (60 A MAS AÑOS)", "MASTER D (60 + AÑOS)"]},
    {"name": "TURISMO OPEN VARONES", "short_code": "TOV", "aliases": ["TURISMO OPEN", "TURISMO VARONES", "TURISMO OPEN VARONES", "TURISMO OPEN VARON"]},
    {"name": "TURISMO MASTER VARONES", "short_code": "TMV", "aliases": ["TURISMO MASTER", "TURISMO MASTER VARONES", "TURISMO MASTER VARON"]},
    {"name": "OPEN DAMAS", "short_code": "OPD", "aliases": ["OPEN DAMAS", "OPEN DAMAS (18-34 AÑOS", "OPEN DAMAS (18-34 AÑOS)", "DAMAS OPEN"]},
    {"name": "DAMAS MASTER", "short_code": "DMM", "aliases": ["DAMAS MASTER", "DAMAS MASTER (35 A MAS)"]},
    {"name": "JUVENILES 15 - 17", "short_code": "JUV", "aliases": ["JUVENILES", "JUVENILES 15 - 17", "JUVENIL"]},
]

PUBLIC_GPX_DIR = os.path.join("frontend", "public", "gpx")

# Categorías que dieron 3 vueltas en la Z Xtreme; el resto dio 2.
Z2_LAPS_3 = {"MSA", "MSB", "MSC", "ELI", "EBK"}
Z2_LAPS_DEFAULT = 2


RACE_CONFIG: List[Dict[str, Any]] = [
    {
        "stage_number": 1,
        "name": "Fecha 1: La Joya Extreme",
        "short_name": "La Joya",
        "title": "La Joya Extreme",
        "slug": "la-joya-extreme",
        "date": datetime.date(2026, 5, 17),
        "status": StageStatusEnum.FINISHED,
        "start_location": "Vía de Evitamiento, La Joya",
        "start_time": "08:00 AM",
        "poster_url": "/images/posters/f1-la-joya-extreme-card.webp",
        "judge_pin": "***REMOVED-JUDGE-PIN-F1***",
        "laps": 1,
        "distance_km": 40.85,
        "elevation_gain_m": 384,
        "excel": ["races/1. LA JOYA EXTREME 2026 N f.xlsx", "races/LA JOYA EXTREME 2026 N f.xlsx"],
        "pdf": ["races/1. LA JOYA EXTREME 2026  RESULTADOS.pdf", "races/LA JOYA EXTREME 2026  RESULTADOS.pdf"],
        "gpx": ["races/La Joya Extreme 2026 - Ruta oficial.gpx"],
        "gpx_public": "la-joya-extreme.gpx",
        "strava_route_url": "https://www.strava.com/routes/3486799154256647166",
    },
    {
        "stage_number": 2,
        "name": "Fecha 2: Kúspide Z Xtreme III",
        "short_name": "Z Xtreme",
        "title": "Kúspide Z Xtreme — 3ra Edición",
        "slug": "z-xtreme-2026",
        "date": datetime.date(2026, 8, 23),
        "status": StageStatusEnum.FINISHED,
        "start_location": "Circuito La Z",
        "start_time": "08:00 AM",
        "poster_url": "/images/posters/f2-z-xtreme-card.webp",
        "judge_pin": "***REMOVED-JUDGE-PIN-F2***",
        "laps": 3,
        "distance_km": 11.83,
        "elevation_gain_m": 280,
        "excel": ["races/2. INSCRITOS ZETA EXTREME 2026.xlsx"],
        "pdf": ["races/LA Z XTREME 2026 - RESULTADOS.-1.pdf"],
        "gpx": ["races/Kuspide ZETA Extrema.gpx"],
        "gpx_public": "z-xtreme.gpx",
        "strava_route_url": "https://www.strava.com/routes/3200784336826934006",
        "laps_by_category": True,
    },
    {
        "stage_number": 3,
        "name": "Fecha 3: El Retorno a los Poblados 2",
        "short_name": "Poblados",
        "title": "El Retorno a los Poblados 2",
        "slug": "vuelta-a-los-poblados",
        "date": datetime.date(2026, 10, 25),
        "status": StageStatusEnum.REGISTRATION_OPEN,
        "start_location": "Plaza de Chiguata",
        "start_time": "08:00 AM",
        "poster_url": "/images/posters/f3-retorno-poblados-card.webp",
        "judge_pin": "***REMOVED-JUDGE-PIN-F3***",
        "laps": 1,
        "distance_km": 47.23,
        "elevation_gain_m": 761,
        "excel": [],
        "pdf": [],
        "gpx": ["races/Vuelta a los poblados 2026.gpx"],
        "gpx_public": "vuelta-a-los-poblados.gpx",
        "strava_route_url": "https://www.strava.com/routes/3545824230908680048",
    },
    {
        "stage_number": 4,
        "name": "Fecha 4: Quequeña Xtreme III",
        "short_name": "Quequeña",
        "title": "Quequeña Xtreme III",
        "slug": "quequena-xtreme",
        "date": datetime.date(2026, 12, 13),
        "status": StageStatusEnum.UPCOMING,
        "start_location": "Plaza Principal de Quequeña",
        "start_time": "08:00 AM",
        "poster_url": "/images/posters/f4-quequena-xtreme-card.webp",
        "judge_pin": "***REMOVED-JUDGE-PIN-F4***",
        "laps": 1,
        "distance_km": 45.0,
        "elevation_gain_m": 950,
        "excel": [],
        "pdf": [],
        "gpx": [],
        "gpx_public": None,
        "strava_route_url": None,
    },
]

EXTRA_EVENTS: List[Dict[str, Any]] = [
    {
        "name": "La Vuelta a Talamolle 2026",
        "short_name": "Talamolle",
        "slug": "vuelta-a-talamolle-2026",
        "event_type": "ROAD",
        "edition": "Edición 2026",
        "dates_text": "26 de Julio de 2026",
        "start_location": "Plaza de Mollebaya",
        "start_time": "08:00 AM",
        "distance_text": "63 KM / 43 KM",
        "description": "Ruta en línea de alta exigencia: Mollebaya - Talamolle (63 KM para Elite y Master A, B, C, D / 43 KM para Turismo y Damas). Carrera preparatoria oficial para la Doble Arequipa - Mollendo.",
        "poster_url": "/images/posters/extra-vuelta-talamolle-card.webp",
        "whatsapp_contact": "994382248",
        "registration_fee_text": "S/ 40.00 (Preventa) / S/ 50.00 (General)",
        "status": "FINISHED",
        "is_active": True,
    },
    {
        "name": "Clásica Arequipa - Mollendo",
        "short_name": "Arequipa - Mollendo",
        "slug": "clasica-arequipa-mollendo-72",
        "event_type": "ROAD",
        "edition": "72ª Edición",
        "dates_text": "07 y 08 de Noviembre de 2026",
        "start_location": "Arequipa",
        "start_time": "08:00 AM",
        "distance_text": "2 Etapas en Ruta",
        "description": "Tradición, pasión y leyenda en el sur del Perú. 72ª Edición de la carrera ciclista de ruta más emblemática del país en dos etapas épicas con cupos limitados.",
        "poster_url": "/images/posters/extra-clasica-mollendo-card.webp",
        "whatsapp_contact": "994382248",
        "registration_fee_text": "Cupos Limitados — Informes WhatsApp",
        "status": "UPCOMING",
        "is_active": True,
    },
]


def find_race_file(*candidates: str) -> Optional[str]:
    """Busca un archivo entre varias rutas candidatas relativas al repo."""
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


def sync_public_gpx(src: str, dest_name: Optional[str]) -> Optional[str]:
    """Copia el GPX a frontend/public/gpx y devuelve su URL pública."""
    if not src or not dest_name:
        return None
    try:
        os.makedirs(PUBLIC_GPX_DIR, exist_ok=True)
        shutil.copyfile(src, os.path.join(PUBLIC_GPX_DIR, dest_name))
        return f"/gpx/{dest_name}"
    except OSError as exc:
        print(f"AVISO: no se pudo copiar GPX público ({dest_name}): {exc}")
        return None


async def seed_categories(session: AsyncSession) -> Dict[str, Category]:
    print("Sembrando 11 categorías oficiales...")
    cat_map: Dict[str, Category] = {}
    for c_def in CATEGORIES_DEF:
        stmt = select(Category).where(Category.short_code == c_def["short_code"])
        existing = (await session.exec(stmt)).first()
        if not existing:
            cat = Category(name=c_def["name"], short_code=c_def["short_code"], aliases=c_def["aliases"])
            session.add(cat)
            await session.flush()
            cat_map[c_def["short_code"]] = cat
        else:
            existing.name = c_def["name"]
            existing.aliases = c_def["aliases"]
            session.add(existing)
            cat_map[c_def["short_code"]] = existing
    await session.commit()
    return cat_map


async def upsert_stage(session: AsyncSession, cfg: Dict[str, Any]) -> Stage:
    stmt = select(Stage).where(Stage.stage_number == cfg["stage_number"])
    stage = (await session.exec(stmt)).first()
    if not stage:
        stage = Stage(stage_number=cfg["stage_number"])
        session.add(stage)
    stage.name = cfg["name"]
    stage.short_name = cfg.get("short_name")
    stage.title = cfg.get("title")
    stage.slug = cfg["slug"]
    stage.date = cfg["date"]
    stage.status = cfg["status"]
    stage.start_location = cfg.get("start_location")
    stage.start_time = cfg.get("start_time", "08:00 AM")
    stage.poster_url = cfg["poster_url"]
    stage.judge_pin = cfg["judge_pin"]
    stage.laps = cfg["laps"]
    stage.strava_route_url = cfg.get("strava_route_url")
    stage.distance_km = cfg["distance_km"]
    stage.elevation_gain_m = cfg["elevation_gain_m"]
    await session.flush()
    return stage


async def seed_checkpoints_and_waves(
    session: AsyncSession, stage: Stage, cat_map: Dict[str, Category], distance_km: float
) -> None:
    stmt_cp = select(Checkpoint).where(Checkpoint.stage_id == stage.id)
    if not (await session.exec(stmt_cp)).first():
        session.add_all([
            Checkpoint(stage_id=stage.id, name="Partida", order_index=0, distance_from_start_km=0.0, is_finish_line=False),
            Checkpoint(stage_id=stage.id, name="Control Intermedio Cumbre", order_index=1, distance_from_start_km=distance_km / 2, is_finish_line=False),
            Checkpoint(stage_id=stage.id, name="Meta Final", order_index=99, distance_from_start_km=distance_km, is_finish_line=True),
        ])

    stmt_sw = select(StartWave).where(StartWave.stage_id == stage.id)
    if not (await session.exec(stmt_sw)).first():
        session.add_all([
            StartWave(stage_id=stage.id, name="Manga 1 — Elite & Master A", category_ids=[cat_map["ELI"].id, cat_map["MSA"].id]),
            StartWave(stage_id=stage.id, name="Manga 2 — Master B, C & D", category_ids=[cat_map["MSB"].id, cat_map["MSC"].id, cat_map["MSD"].id]),
            StartWave(stage_id=stage.id, name="Manga 3 — Damas & Juveniles", category_ids=[cat_map["OPD"].id, cat_map["DMM"].id, cat_map["JUV"].id]),
            StartWave(stage_id=stage.id, name="Manga 4 — Turismo & E-Bike", category_ids=[cat_map["TOV"].id, cat_map["TMV"].id, cat_map["EBK"].id]),
        ])


async def load_gpx(session: AsyncSession, stage: Stage, cfg: Dict[str, Any]) -> None:
    gpx_path = find_race_file(*cfg.get("gpx", []))
    if gpx_path:
        print(f"Parseando GPX de '{stage.name}' desde {gpx_path}...")
        with open(gpx_path, "rb") as f:
            data = parse_gpx_in_memory(f.read())
        stage.distance_km = data["distance_km"]
        stage.elevation_gain_m = data["elevation_gain_m"]
        stage.route_geojson = data["route_geojson"]
    # Ruta pública descargable
    stage.gpx_file_url = sync_public_gpx(gpx_path, cfg.get("gpx_public")) if gpx_path else None
    session.add(stage)
    await session.commit()


def category_from_info(info: str, cats: List[Category]) -> Optional[Category]:
    """Resuelve la categoría de un renglón del PDF: el alias/nombre MÁS LARGO que sea sufijo."""
    upper = (info or "").upper()
    best: Optional[Category] = None
    best_len = -1
    for c in cats:
        for cand in [c.name, c.short_code] + list(c.aliases or []):
            cu = (cand or "").upper().strip()
            if cu and upper.endswith(cu) and len(cu) > best_len:
                best, best_len = c, len(cu)
    return best


async def cross_pdf_results(
    session: AsyncSession, stage: Stage, pdf_results: List[Dict[str, Any]]
) -> tuple:
    """
    Cruza los resultados del PDF con las inscripciones de la fecha, tolerando dorsales
    desalineados entre Excel y PDF. Prioridad:
      1. Por dorsal, si el nombre Y la categoría coinciden.
      2. Por nombre MÁS LARGO contenido, exigiendo que la categoría coincida.
      3. Inscrito sin resultado cuyo nombre coincide: se confía en la categoría del PDF.
      4. Fallback por dorsal, solo si la categoría coincide.
    Los resultados que no cruzan se devuelven para reconciliación (crear inscrito).

    Autoridad del PDF oficial (specs/01 §1.5): el tiempo, la categoría y el DORSAL
    publicado en el PDF mandan sobre la lista de inscritos. Si el dorsal oficial está
    libre en la fecha, se aplica a la inscripción; si ya está ocupado por otro
    corredor, se conserva el dorsal de inscripción y se reporta el conflicto.

    Devuelve (n_cruzados, resultados_sin_inscrito, n_dorsales_oficiales_aplicados).
    """
    entries = (await session.exec(select(StageEntry).where(StageEntry.stage_id == stage.id))).all()
    riders = (await session.exec(select(Rider))).all()
    cats = (await session.exec(select(Category))).all()
    names = {r.id: normalize_name(r.full_name) for r in riders}
    by_bib = {e.bib_number: e for e in entries}
    by_name = [(names.get(e.rider_id), e) for e in entries if names.get(e.rider_id)]

    assigned: Dict[int, int] = {}
    desired_bibs: Dict[int, int] = {}   # entry_id -> dorsal oficial del PDF
    unmatched: List[Dict[str, Any]] = []

    for res in pdf_results:
        norm_info = normalize_name(res["raw_info"])
        hint = category_from_info(res["raw_info"], cats)
        direct = by_bib.get(res["bib_number"])

        target = None
        # 1. Dorsal correcto si el nombre (y categoría, si se conoce) coinciden
        if direct:
            dn = names.get(direct.rider_id)
            if dn and (dn in norm_info or norm_info in dn) and (hint is None or direct.category_id == hint.id):
                target = direct

        # 2. Nombre MÁS LARGO contenido, exigiendo la categoría del PDF
        if target is None:
            best, best_len = None, -1
            for n, e in by_name:
                if hint is not None and e.category_id != hint.id:
                    continue
                if n in norm_info and len(n) > best_len:
                    best, best_len = e, len(n)
            target = best

        # 3. Inscrito sin resultado cuyo nombre coincide: se confía en la categoría del PDF
        if target is None and hint is not None:
            best, best_len = None, -1
            for n, e in by_name:
                if e.id in assigned or e.finish_elapsed_ms is not None:
                    continue
                if n in norm_info and len(n) > best_len:
                    best, best_len = e, len(n)
            if best is not None:
                if best.category_id != hint.id:
                    best.category_id = hint.id
                    if stage.laps > 1:
                        best.laps = stage.laps if hint.short_code in Z2_LAPS_3 else Z2_LAPS_DEFAULT
                    session.add(best)
                target = best

        # 4. Fallback final: el inscrito del MISMO dorsal, solo si la categoría coincide.
        #    Sin esta condición el resultado de un corredor se traspasaría a otro
        #    (p.ej. dorsal 147 en Z Xtreme: el PDF dice WENDY NINA CHIRE / OPEN DAMAS
        #    y la lista de inscritos dice ELMER EFRAIN MAMANI MAQUERA / TURISMO OPEN).
        #    El caso CHARLES/ANDRE GONZALES sí se resuelve aquí: mismo dorsal, misma
        #    categoría, nombre con variante en el PDF oficial.
        if target is None and direct is not None:
            if hint is None or direct.category_id == hint.id:
                target = direct

        if target is None:
            # El dorsal no existe en las inscripciones -> se reconcilia creando el inscrito
            unmatched.append(res)
            continue

        prev = assigned.get(target.id)
        assigned[target.id] = res["elapsed_ms"] if prev is None else min(prev, res["elapsed_ms"])

        # El dorsal oficial del PDF manda sobre el de la lista de inscritos.
        if res["bib_number"] != target.bib_number:
            desired_bibs[target.id] = res["bib_number"]

    # --- Reasignación de dorsales en dos fases ---
    # El PDF oficial puede permutar dorsales (p.ej. JHOAN PAYHUA 40->140 mientras
    # ROLANDO PALOMO 140->166). Primero se liberan los dorsales de las inscripciones
    # que se mueven (valor temporal negativo y único) y luego se aplican los nuevos,
    # de modo que nunca se choque con el UniqueConstraint(stage_id, bib_number).
    moving = set(desired_bibs.keys())
    static_bibs = {e.bib_number for e in entries if e.id not in moving}
    final_bibs: Dict[int, int] = {}
    taken: set = set()
    conflicts: List[tuple] = []
    for eid, bib in desired_bibs.items():
        if bib in static_bibs or bib in taken:
            conflicts.append((eid, bib))
            continue
        final_bibs[eid] = bib
        taken.add(bib)

    if final_bibs:
        for idx, eid in enumerate(final_bibs):
            entry = next(e for e in entries if e.id == eid)
            entry.bib_number = -(1_000_000 + idx)   # dorsal temporal, único por inscripción
        await session.commit()
        for eid, bib in final_bibs.items():
            entry = next(e for e in entries if e.id == eid)
            entry.bib_number = bib

    for e in entries:
        if e.id in assigned:
            e.finish_elapsed_ms = assigned[e.id]
            e.race_status = RaceStatusEnum.FINISHED
            session.add(e)
    await session.commit()
    if conflicts:
        print(f"   AVISO: {len(conflicts)} dorsales oficiales no se pudieron aplicar "
              f"(ocupados por otra inscripción): {conflicts}")
    return len(assigned), unmatched, len(final_bibs)


async def reconcile_pdf_only_results(
    session: AsyncSession,
    stage: Stage,
    pdf_results: List[Dict[str, Any]],
    laps: int,
) -> int:
    """
    Algunos dorsales del PDF no tienen inscrito en el Excel (filas vacías en origen).
    Para no perder esos resultados, se recupera/crea el corredor a partir del nombre
    del PDF (quitando categoría y equipo conocidos) y se crea su StageEntry.

    Si el corredor YA tiene inscripción en esta fecha (p.ej. el Excel le asignó otro
    dorsal), se reutiliza esa inscripción en lugar de duplicarla: así no se pierde el
    dorsal oficial del PDF al fusionar identidades.
    Devuelve cuántos inscritos se reconstruyeron.
    """
    cats = (await session.exec(select(Category))).all()
    teams = (await session.exec(select(Team))).all()
    team_names = sorted([t.name for t in teams], key=len, reverse=True)
    riders = (await session.exec(select(Rider))).all()
    riders_by_norm = {normalize_name(r.full_name): r for r in riders}
    entries = (await session.exec(select(StageEntry).where(StageEntry.stage_id == stage.id))).all()
    entry_by_rider = {e.rider_id: e for e in entries}
    by_bib = {e.bib_number: e for e in entries}
    created = 0

    def _reserve_bib(taken: set) -> int:
        """Dorsal reservado (0, -1, -2...) para inscripciones sin dorsal confirmado."""
        candidate = 0
        while candidate in taken:
            candidate -= 1
        return candidate

    def _release_bib(official_bib: int) -> None:
        """
        El dorsal oficial del PDF pertenece a un corredor que no está en la lista de
        inscritos. Si ese dorsal lo tenía una inscripción SIN resultado oficial, se
        libera: la inscripción queda DNS (no aparece en los resultados oficiales) y
        su dorsal se marca como no confirmado.
        """
        holder = by_bib.get(official_bib)
        if holder is None:
            return
        if holder.finish_elapsed_ms is not None:
            print(f"   AVISO: el dorsal oficial {official_bib} ya lo tiene un corredor "
                  f"con resultado; se conserva el dorsal de la inscripción")
            return
        taken = set(by_bib.keys())
        holder.bib_number = _reserve_bib(taken)
        holder.race_status = RaceStatusEnum.DNS
        session.add(holder)
        by_bib.pop(official_bib, None)
        by_bib[holder.bib_number] = holder

    for res in pdf_results:
        info = collapse_team_hyphen(res["raw_info"].strip())

        # 1. Categoría: el alias/nombre MÁS LARGO que sea sufijo del texto
        category = category_from_info(info, cats)
        if not category:
            continue
        upper = info.upper()
        cat_text = ""
        for cand in [category.name, category.short_code] + list(category.aliases or []):
            cu = (cand or "").upper().strip()
            if cu and upper.endswith(cu) and len(cu) > len(cat_text):
                cat_text = cu
        remainder = info[: len(info) - len(cat_text)].strip()

        # 2. Equipo: team conocido más largo que sea sufijo del resto
        team_id = None
        for tname in team_names:
            if remainder.upper().endswith(tname.upper()):
                remainder = remainder[: len(remainder) - len(tname)].strip()
                team_id = await resolve_or_create_team(session, tname)
                break
        if team_id is None and remainder.upper().endswith("LIBRE"):
            remainder = remainder[: len(remainder) - len("LIBRE")].strip()

        # 3. Nombre del ciclista (mejor esfuerzo)
        name = remainder.strip(" .-") or f"DORSAL {res['bib_number']}"
        norm = normalize_name(name)

        rider = riders_by_norm.get(norm)
        if not rider:
            # coincidencia parcial (mismo ciclista con nombre algo distinto entre fechas)
            for key, candidate in riders_by_norm.items():
                if len(norm) > 6 and (norm in key or key in norm):
                    rider = candidate
                    break
        if not rider:
            dni = generate_deterministic_dni(name)
            rider = Rider(
                dni=dni, full_name=name, slug=f"{slugify(name)}-{dni[-4:]}", team_id=team_id,
            )
            session.add(rider)
            await session.flush()
            riders_by_norm[norm] = rider

        # El corredor ya tenía inscripción en esta fecha: se reutiliza y se actualiza
        # con los datos oficiales (dorsal, categoría, equipo y tiempo).
        entry = entry_by_rider.get(rider.id)
        if entry is not None:
            if entry.bib_number != res["bib_number"]:
                _release_bib(res["bib_number"])
            entry.bib_number = res["bib_number"]
            entry.category_id = category.id
            if team_id is not None:
                entry.team_id = team_id
            entry.payment_status = PaymentStatusEnum.PAID
            entry.race_status = RaceStatusEnum.FINISHED
            entry.finish_elapsed_ms = res["elapsed_ms"]
            entry.laps = laps if laps <= 1 else (laps if category.short_code in Z2_LAPS_3 else Z2_LAPS_DEFAULT)
            session.add(entry)
            by_bib[entry.bib_number] = entry
            created += 1
            continue

        # Corredor que solo existe en el PDF oficial: se libera su dorsal si la lista
        # de inscritos lo tenía asignado a alguien sin resultado oficial.
        if res["bib_number"] in by_bib:
            _release_bib(res["bib_number"])

        entry = StageEntry(
            stage_id=stage.id,
            rider_id=rider.id,
            category_id=category.id,
            team_id=team_id or rider.team_id,
            bib_number=res["bib_number"],
            payment_status=PaymentStatusEnum.PAID,
            race_status=RaceStatusEnum.FINISHED,
            finish_elapsed_ms=res["elapsed_ms"],
            laps=laps if laps <= 1 else (laps if category.short_code in Z2_LAPS_3 else Z2_LAPS_DEFAULT),
        )
        session.add(entry)
        entry_by_rider[rider.id] = entry
        by_bib[entry.bib_number] = entry
        created += 1

    await session.commit()
    return created


async def reconcile_official_ranks(
    session: AsyncSession,
    stage: Stage,
    pdf_results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Compara el PUESTO publicado en el PDF oficial con el puesto recalculado por tiempo
    (specs/01 §3.1 ordena por `finish_elapsed_ms ASC`).

    El PDF oficial del organizador tiene erratas punctuales en su columna PUESTO
    (puestos repetidos, puestos saltados y un "1" en el lugar del 14º). El motor
    recalcula el puesto por tiempo, que es la regla reglamentaria; este reporte deja
    constancia de cada diferencia para revisión del organizador.
    """
    entries = (await session.exec(select(StageEntry).where(StageEntry.stage_id == stage.id))).all()
    by_bib = {e.bib_number: e for e in entries}
    deviations = []
    for res in pdf_results:
        entry = by_bib.get(res["bib_number"])
        if entry is None or entry.category_rank is None:
            continue
        if entry.category_rank != res["rank"]:
            deviations.append({
                "bib_number": res["bib_number"],
                "official_rank": res["rank"],
                "recalculated_rank": entry.category_rank,
            })
    return {
        "official_rows": len(pdf_results),
        "deviations": deviations,
    }


async def load_results(
    session: AsyncSession,
    stage: Stage,
    cfg: Dict[str, Any],
    cat_map: Dict[str, Category],
) -> None:
    excel_path = find_race_file(*cfg.get("excel", []))
    if not excel_path:
        print(f"'{stage.name}': sin lista de inscritos (fecha futura).")
        return

    print(f"'{stage.name}': importando inscritos desde {excel_path}...")
    with open(excel_path, "rb") as f:
        content = f.read()
    # merge_duplicates=False: la fusión por identidad se resuelve DESPUÉS de cruzar
    # los tiempos del PDF, para conservar el mejor tiempo real de cada ciclista.
    await import_riders_from_excel(session, stage.id, content, is_legacy_format=True, merge_duplicates=False)

    # Vueltas por categoría (solo circuitos por vueltas, ej. Z Xtreme)
    if cfg["laps"] > 1:
        entries = (await session.exec(select(StageEntry).where(StageEntry.stage_id == stage.id))).all()
        cat_by_id = {c.id: c for c in cat_map.values()}
        for e in entries:
            code = cat_by_id[e.category_id].short_code if e.category_id in cat_by_id else None
            e.laps = cfg["laps"] if code in Z2_LAPS_3 else Z2_LAPS_DEFAULT
            session.add(e)
        await session.commit()

    pdf_path = find_race_file(*cfg.get("pdf", []))
    if pdf_path:
        print(f"'{stage.name}': cruzando resultados desde {pdf_path}...")
        # Estado limpio para un cruce determinístico e idempotente
        entries = (await session.exec(select(StageEntry).where(StageEntry.stage_id == stage.id))).all()
        for e in entries:
            e.finish_elapsed_ms = None
            e.race_status = RaceStatusEnum.REGISTERED
            e.category_rank = None
            e.overall_rank = None
            e.points_earned = 0
            session.add(e)
        await session.commit()

        results = extract_race_results_from_pdf(pdf_path)
        print(f"   -> {len(results)} tiempos oficiales extraídos del PDF")
        matched, unmatched, bibs_applied = await cross_pdf_results(session, stage, results)
        print(f"   -> {matched} inscritos cruzados con tiempo")
        if bibs_applied:
            print(f"   -> {bibs_applied} dorsales oficiales del PDF aplicados sobre la lista de inscritos")
        recon = await reconcile_pdf_only_results(session, stage, unmatched, cfg["laps"])
        if recon:
            print(f"   -> {recon} inscritos reconstruidos solo desde el PDF")
    else:
        print(f"'{stage.name}': sin PDF de resultados (fecha futura).")

    # Un solo registro por ciclista y fecha (conserva el mejor tiempo)
    merged = await merge_duplicate_entries(session, stage.id)
    if merged:
        print(f"   -> {merged} inscripciones duplicadas fusionadas")

    await recalculate_stage_ranks(session, stage.id)
    await recalculate_championship_standings(session)
    await recalculate_team_standings(session, stage.id)

    # Reporte de integridad: contraste entre el PUESTO oficial publicado y el
    # recalculado por tiempo (regla de specs/01 §3.1).
    if pdf_path:
        report = await reconcile_official_ranks(session, stage, results)
        if report["deviations"]:
            print(
                f"   -> {len(report['deviations'])} de {report['official_rows']} filas con "
                f"PUESTO oficial distinto al recalculado por tiempo (erratas del PDF): "
                f"{report['deviations']}"
            )
        else:
            print(f"   -> las {report['official_rows']} filas coinciden con el PUESTO oficial")


async def seed_special_awards(session: AsyncSession, stage_1_id: int) -> None:
    stmt = select(SpecialAward).where(SpecialAward.stage_id == stage_1_id)
    if (await session.exec(stmt)).first():
        return
    print("Sembrando premios especiales...")
    session.add_all([
        SpecialAward(
            stage_id=stage_1_id, title="Premio Especial Coca", sponsor_name="Tradición Andina",
            sponsor_logo_url="/images/premio_coca.jpg",
            prize_description="S/ 300 + Trofeo Conmemorativo Coca de Bronce",
            metric_value="Premio a la Resistencia y Espíritu Deportivo",
        ),
        SpecialAward(
            stage_id=stage_1_id, title="Rey de la Montaña (KOM)", sponsor_name="Kúspide Performance",
            sponsor_logo_url="/images/rey_montana.jpg",
            prize_description="S/ 500 + Maillot de Lunares de Líder Escalador",
            metric_value="Mejor tiempo en el sector de ascenso Cumbre",
        ),
    ])
    await session.commit()


async def seed_strava(
    session: AsyncSession,
    stage_1_id: int,
    stage_2_id: int,
    stage_3_id: int,
) -> None:
    """Registra los segmentos oficiales reales. Los esfuerzos se cargan por scraping CDP.

    La lista sale de la tabla `Segments` de cada ruta de Strava (la propia ruta
    oficial de cada fecha), que enumera TODOS los tramos que la cortan con su
    distancia, su desnivel y su pendiente media.
    """
    segments = [
        # --- Fecha 1 · La Joya Extreme (13 segmentos) ---
        (stage_1_id, "31121203", "Por el asfalto", 960.0, -0.2, "Cerro Colorado, Arequipa", 2259, 2263),
        (stage_1_id, "25044168", "Cañon del perro rabioso", 1800.0, 1.0, "Uchumayo, Arequipa", 2159, 2189),
        (stage_1_id, "25045985", "Perro rabioso - trepada", 1000.0, 4.5, "Uchumayo, Arequipa", 2111, 2158),
        (stage_1_id, "30866373", "Recta final a carretera", 1970.0, -1.0, "Uchumayo, Arequipa", 2168, 2190),
        (stage_1_id, "26837710", "Subida canteras hacia La Joya", 1030.0, 1.2, "Uchumayo, Arequipa", None, None),
        (stage_1_id, "31227003", "La encalaminadora Quishuarani", 2840.0, -3.9, "Uchumayo, Arequipa", 1872, 1981),
        (stage_1_id, "31226989", "Desenfreno Quishuarani", 1690.0, -3.0, "Uchumayo, Arequipa", 1820, 1871),
        (stage_1_id, "30566980", "QUISHUARANI a la linea del TREN", 6980.0, 0.7, "Uchumayo, Arequipa", None, None),
        (stage_1_id, "18378066", "Pte. Quishuarani / Antes bajada a La Joya", 6920.0, 0.7, "Uchumayo, Arequipa", 1799, 1913),
        (stage_1_id, "31121169", "Cenicero", 1370.0, 2.5, "Uchumayo, Arequipa", 1826, 1862),
        (stage_1_id, "41279552", "Arena, calamina, piedras y trepada", 2960.0, 1.8, "Uchumayo, Arequipa", None, None),
        (stage_1_id, "30612243", "A la Joya", 5510.0, -3.9, "Uchumayo, Arequipa", 1656, 1873),
        (stage_1_id, "41448847", "La Joya Xtreme 26", 38800.0, -1.6, "Cerro Colorado, Arequipa", 1679, 2284),
        # --- Fecha 2 · Z Xtreme 2026 (3 segmentos) ---
        (stage_2_id, "12875208", "Corte_Mollebaya", 710.0, 8.1, "Giriguaya, Arequipa", None, None),
        (stage_2_id, "41681206", "Circuito La Z Extreme 2026", 11230.0, 0.0, "Uchumayo, Arequipa", 2488, 2747),
        (stage_2_id, "27868955", "Z de desenfreno", 5720.0, -4.2, "Uchumayo, Arequipa", None, None),
        # --- Fecha 3 · Vuelta a los Poblados (10 segmentos) ---
        (stage_3_id, "25245306", "Trepada Carretera 602 - Hasta Iglesia Cacayaco", 5400.0, 6.2, "Cacayaco, Arequipa", None, None),
        (stage_3_id, "21396382", "Cruce Chiguata - Mosopuquio", 8730.0, 3.7, "Mosopuquio, Arequipa", None, None),
        (stage_3_id, "26168484", "Chiguata a Tuctumpaya", 15840.0, 2.5, "Tuctumpaya, Arequipa", None, None),
        (stage_3_id, "30658106", "Santa Maria a Cacayaco", 4330.0, 6.9, "Cacayaco, Arequipa", None, None),
        (stage_3_id, "26420480", "Desvio-Mosopuquio", 6970.0, 4.2, "Mosopuquio, Arequipa", None, None),
        (stage_3_id, "21396392", "Mosopuquio - Tuctumpaya", 6850.0, 0.7, "Tuctumpaya, Arequipa", None, None),
        (stage_3_id, "32049640", "Piaca, el regreso", 4540.0, -1.0, "Piaca, Arequipa", None, None),
        (stage_3_id, "19713632", "DH Cruce Pocsi - Z", 3320.0, -4.6, "Pocsi, Arequipa", None, None),
        (stage_3_id, "31319233", "Hacienda la Luna", 1210.0, 2.5, "Arequipa", None, None),
    ]
    for stage_id, seg_id, name, dist, grade, location, ele_min, ele_max in segments:
        stmt = select(StravaSegment).where(StravaSegment.strava_segment_id == seg_id)
        existing = (await session.exec(stmt)).first()
        # El tipo del tramo: subida, bajada o llano. Lo decide la pendiente media.
        if grade >= 0.5:
            kind = "CLIMB"
        elif grade <= -0.5:
            kind = "DESCENT"
        else:
            kind = "FLAT"
        if existing:
            existing.stage_id = stage_id
            existing.name = name
            existing.distance_m = dist
            existing.average_grade = grade
            existing.location = location
            existing.elevation_min_m = ele_min
            existing.elevation_max_m = ele_max
            existing.kind = kind
            session.add(existing)
        else:
            session.add(StravaSegment(
                stage_id=stage_id,
                strava_segment_id=seg_id,
                name=name,
                distance_m=dist,
                average_grade=grade,
                location=location,
                elevation_min_m=ele_min,
                elevation_max_m=ele_max,
                kind=kind,
            ))
    await session.commit()


async def seed_route_summits(session: AsyncSession, stage: Stage) -> None:
    """Siembra las cimas de la ruta con su nombre real.

    El nombre sale del reverse-geocode de OpenStreetMap (Nominatim) sobre la
    coordenada de la cima. La red se consulta **solo al sembrar**: en cada
    request la página no depende de un servicio externo.

    Los nombres ya resueltos se guardan aquí para que el seed sea
    idempotente y no vuelva a pegarle a Nominatim en cada ejecución.
    """
    from backend.app.services.route_profile_service import extract_summits

    existing = (
        await session.exec(select(RouteSummit).where(RouteSummit.stage_id == stage.id))
    ).all()
    if existing:
        return

    summits = extract_summits(stage.route_geojson, geocode=False)
    if not summits:
        return

    for summit in summits:
        session.add(
            RouteSummit(
                stage_id=stage.id,
                name=summit["name"],
                category=summit["category"],
                distance_km=summit["distance_km"],
                elevation_m=summit["elevation_m"],
                climb_gain_m=summit["climb_gain_m"],
                avg_grade_pct=summit["avg_grade_pct"],
                max_grade_pct=summit["max_grade_pct"],
                lat=summit["lat"],
                lon=summit["lon"],
                name_source=summit["name_source"],
            )
        )
    await session.commit()


async def seed_extra_events(session: AsyncSession) -> None:
    """Siembra los eventos de ruta y especiales no puntuables del campeonato."""
    print("Sembrando eventos especiales de ruta...")
    for item in EXTRA_EVENTS:
        stmt = select(ExtraEvent).where(ExtraEvent.slug == item["slug"])
        ev = (await session.exec(stmt)).first()
        if not ev:
            ev = ExtraEvent(
                name=item["name"],
                short_name=item.get("short_name"),
                slug=item["slug"],
                event_type=item.get("event_type", "ROAD"),
                edition=item.get("edition"),
                dates_text=item["dates_text"],
                start_location=item.get("start_location"),
                start_time=item.get("start_time"),
                distance_text=item.get("distance_text"),
                description=item.get("description"),
                poster_url=item.get("poster_url"),
                whatsapp_contact=item.get("whatsapp_contact", "994382248"),
                registration_fee_text=item.get("registration_fee_text"),
                status=item.get("status", "UPCOMING"),
                is_active=item.get("is_active", True),
            )
            session.add(ev)
        else:
            ev.name = item["name"]
            ev.short_name = item.get("short_name")
            ev.event_type = item.get("event_type", "ROAD")
            ev.edition = item.get("edition")
            ev.dates_text = item["dates_text"]
            ev.start_location = item.get("start_location")
            ev.start_time = item.get("start_time")
            ev.distance_text = item.get("distance_text")
            ev.description = item.get("description")
            ev.poster_url = item.get("poster_url")
            ev.whatsapp_contact = item.get("whatsapp_contact", "994382248")
            ev.registration_fee_text = item.get("registration_fee_text")
            ev.status = item.get("status", "UPCOMING")
            ev.is_active = item.get("is_active", True)
            session.add(ev)
    await session.commit()


async def seed_data() -> None:
    print("Iniciando base de datos...")
    await init_db()

    async with async_session_factory() as session:
        cat_map = await seed_categories(session)

        print("Sembrando las 4 fechas del campeonato...")
        stages: Dict[int, Stage] = {}
        for cfg in RACE_CONFIG:
            stages[cfg["stage_number"]] = await upsert_stage(session, cfg)
        await session.commit()

        for cfg in RACE_CONFIG:
            stage = stages[cfg["stage_number"]]
            await seed_checkpoints_and_waves(session, stage, cat_map, stage.distance_km)
            await load_gpx(session, stage, cfg)
        await session.commit()

        for cfg in RACE_CONFIG:
            stage = stages[cfg["stage_number"]]
            await load_results(session, stage, cfg, cat_map)

        await seed_special_awards(session, stages[1].id)
        await seed_strava(session, stages[1].id, stages[2].id, stages[3].id)
        await seed_extra_events(session)

        print("Sembrando las cimas de las rutas...")
        for cfg in RACE_CONFIG:
            stage = stages[cfg["stage_number"]]
            await seed_route_summits(session, stage)

    print("¡Seed completado exitosamente!")


if __name__ == "__main__":
    asyncio.run(seed_data())
