import asyncio
import datetime
import os
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select

from backend.app.core.db import engine, init_db, async_session_factory
from backend.app.models.entities import (
    Category, Stage, StageStatusEnum, StartWave, Checkpoint,
    Team, Rider, StageEntry, RaceStatusEnum, PaymentStatusEnum,
    SpecialAward, StravaSegment, StravaEffort
)
from backend.app.services.excel_service import import_riders_from_excel
from backend.app.services.pdf_service import extract_race_results_from_pdf
from backend.app.services.scoring import (
    recalculate_stage_ranks, recalculate_championship_standings, recalculate_team_standings
)


CATEGORIES_DEF = [
    {"name": "E-BIKE OPEN", "short_code": "EBK", "aliases": ["E-BIKE", "E-BIKE OPEN", "EBIKE"]},
    {"name": "ELITE", "short_code": "ELI", "aliases": ["ELITE", "ELITE (18-29 AÑOS)", "ELITE VARONES"]},
    {"name": "MASTER A", "short_code": "MSA", "aliases": ["MASTER A", "MASTER A (30-39 AÑOS)"]},
    {"name": "MASTER B", "short_code": "MSB", "aliases": ["MASTER B", "MASTER B (40-49 AÑOS)"]},
    {"name": "MASTER C", "short_code": "MSC", "aliases": ["MASTER C", "MASTER C (50-59 AÑOS)"]},
    {"name": "MASTER D", "short_code": "MSD", "aliases": ["MASTER D", "MASTER D (60 A MAS AÑOS)"]},
    {"name": "TURISMO OPEN VARONES", "short_code": "TOV", "aliases": ["TURISMO OPEN", "TURISMO VARONES", "TURISMO OPEN VARONES"]},
    {"name": "TURISMO MASTER VARONES", "short_code": "TMV", "aliases": ["TURISMO MASTER", "TURISMO MASTER VARONES"]},
    {"name": "OPEN DAMAS", "short_code": "OPD", "aliases": ["OPEN DAMAS", "OPEN DAMAS (18-34 AÑOS", "OPEN DAMAS (18-34 AÑOS)", "DAMAS OPEN"]},
    {"name": "DAMAS MASTER", "short_code": "DMM", "aliases": ["DAMAS MASTER", "DAMAS MASTER (35 A MAS)"]},
    {"name": "JUVENILES 15 - 17", "short_code": "JUV", "aliases": ["JUVENILES", "JUVENILES 15 - 17", "JUVENIL"]},
]


async def seed_data():
    print("Iniciando base de datos...")
    await init_db()

    async with async_session_factory() as session:
        # 1. Sembrar Categorías
        print("Sembrando 11 categorías oficiales...")
        cat_map = {}
        for c_def in CATEGORIES_DEF:
            stmt = select(Category).where(Category.short_code == c_def["short_code"])
            existing = (await session.exec(stmt)).first()
            if not existing:
                cat = Category(
                    name=c_def["name"],
                    short_code=c_def["short_code"],
                    aliases=c_def["aliases"]
                )
                session.add(cat)
                await session.flush()
                cat_map[c_def["short_code"]] = cat
            else:
                existing.aliases = c_def["aliases"]
                session.add(existing)
                cat_map[c_def["short_code"]] = existing
        await session.commit()

        # 2. Sembrar las 4 Fechas
        print("Sembrando las 4 etapas del campeonato...")
        stages_data = [
            {
                "stage_number": 1,
                "name": "Fecha 1: La Joya Extreme",
                "slug": "la-joya-extreme",
                "date": datetime.date(2026, 3, 15),
                "status": StageStatusEnum.FINISHED,
                "poster_url": "/images/la_joya_extreme.jpg",
                "distance_km": 48.5,
                "elevation_gain_m": 920,
                "judge_pin": "***REMOVED-JUDGE-PIN-F1***"
            },
            {
                "stage_number": 2,
                "name": "Fecha 2: Vuelta a los Poblados",
                "slug": "vuelta-a-los-poblados",
                "date": datetime.date(2026, 10, 25),
                "status": StageStatusEnum.REGISTRATION_OPEN,
                "poster_url": "/images/vuelta_a_los_poblados.jpg",
                "distance_km": 64.2,
                "elevation_gain_m": 1780,
                "judge_pin": "KUS-F2-POB"
            },
            {
                "stage_number": 3,
                "name": "Fecha 3: Rally Chachani",
                "slug": "rally-chachani",
                "date": datetime.date(2026, 11, 22),
                "status": StageStatusEnum.UPCOMING,
                "poster_url": "/images/la_joya_extreme.jpg",
                "distance_km": 52.0,
                "elevation_gain_m": 1350,
                "judge_pin": "KUS-F3-CHA"
            },
            {
                "stage_number": 4,
                "name": "Fecha 4: Desafío del Misti",
                "slug": "desafio-del-misti",
                "date": datetime.date(2026, 12, 13),
                "status": StageStatusEnum.UPCOMING,
                "poster_url": "/images/vuelta_a_los_poblados.jpg",
                "distance_km": 72.0,
                "elevation_gain_m": 2100,
                "judge_pin": "KUS-F4-MIS"
            }
        ]

        stage_objs = {}
        for s_data in stages_data:
            stmt = select(Stage).where(Stage.stage_number == s_data["stage_number"])
            s_obj = (await session.exec(stmt)).first()
            if not s_obj:
                s_obj = Stage(**s_data)
                session.add(s_obj)
                await session.flush()
            stage_objs[s_data["stage_number"]] = s_obj

            # Checkpoints para cada fecha
            stmt_cp = select(Checkpoint).where(Checkpoint.stage_id == s_obj.id)
            cps = (await session.exec(stmt_cp)).all()
            if not cps:
                cp_start = Checkpoint(stage_id=s_obj.id, name="Partida", order_index=0, distance_from_start_km=0.0, is_finish_line=False)
                cp_mid = Checkpoint(stage_id=s_obj.id, name="Control Intermedio Cumbre", order_index=1, distance_from_start_km=s_data["distance_km"] / 2, is_finish_line=False)
                cp_finish = Checkpoint(stage_id=s_obj.id, name="Meta Final", order_index=99, distance_from_start_km=s_data["distance_km"], is_finish_line=True)
                session.add_all([cp_start, cp_mid, cp_finish])

        await session.commit()

        # 3. Importar Inscritos desde LA JOYA EXTREME .xlsx
        excel_path = "races/LA JOYA EXTREME 2026 N f.xlsx"
        stage_1_id = stage_objs[1].id
        if os.path.exists(excel_path):
            print(f"Importando inscritos reales desde {excel_path}...")
            with open(excel_path, "rb") as f:
                content = f.read()
            await import_riders_from_excel(session, stage_1_id, content, is_legacy_format=True)
            print("Inscritos importados con éxito.")

        # 4. Parsear y Cruce de Resultados desde el PDF oficial
        pdf_path = "races/LA JOYA EXTREME 2026  RESULTADOS.pdf"
        if os.path.exists(pdf_path):
            print(f"Parseando resultados oficiales desde {pdf_path}...")
            pdf_results = extract_race_results_from_pdf(pdf_path)
            print(f"Se extrajeron {len(pdf_results)} tiempos oficiales del PDF.")

            # Cruzar con las inscripciones de Fecha 1 por bib_number
            for res in pdf_results:
                bib = res["bib_number"]
                stmt_entry = select(StageEntry).where(
                    StageEntry.stage_id == stage_1_id,
                    StageEntry.bib_number == bib
                )
                entry = (await session.exec(stmt_entry)).first()
                if entry:
                    entry.finish_elapsed_ms = res["elapsed_ms"]
                    entry.race_status = RaceStatusEnum.FINISHED
                    session.add(entry)

            await session.commit()
            print("Cruce de tiempos completado. Recalculando rankings...")
            await recalculate_stage_ranks(session, stage_1_id)
            await recalculate_championship_standings(session)
            await recalculate_team_standings(session, stage_1_id)

        # 5. Sembrar Premios Especiales
        print("Sembrando premios especiales con imágenes oficiales...")
        stmt_aw = select(SpecialAward).where(SpecialAward.stage_id == stage_1_id)
        if not (await session.exec(stmt_aw)).first():
            award_coca = SpecialAward(
                stage_id=stage_1_id,
                title="Premio Especial Coca",
                sponsor_name="Tradición Andina",
                sponsor_logo_url="/images/premio_coca.jpg",
                prize_description="S/ 300 + Trofeo Conmemorativo Coca de Bronce",
                metric_value="Premio a la Resistencia y Espíritu Deportivo"
            )
            award_kom = SpecialAward(
                stage_id=stage_1_id,
                title="Rey de la Montaña (KOM)",
                sponsor_name="Kúspide Performance",
                sponsor_logo_url="/images/rey_montana.jpg",
                prize_description="S/ 500 + Maillot de Lunares de Líder Escalador",
                metric_value="Mejor tiempo en el sector de ascenso Cumbre"
            )
            session.add_all([award_coca, award_kom])
            await session.commit()

        # 6. Sembrar Segmentos Strava y esfuerzos simulados (filosofía Strava)
        print("Sembrando segmentos Strava y esfuerzos...")
        stmt_seg = select(StravaSegment).where(StravaSegment.stage_id == stage_1_id)
        if not (await session.exec(stmt_seg)).first():
            seg1 = StravaSegment(
                stage_id=stage_1_id,
                strava_segment_id="32984120",
                name="Muro Volcánico La Joya (Sector KOM)",
                distance_m=3400.0,
                average_grade=8.4
            )
            seg2 = StravaSegment(
                stage_id=stage_1_id,
                strava_segment_id="29481023",
                name="Sprint Cañón del Río",
                distance_m=1800.0,
                average_grade=1.2
            )
            session.add_all([seg1, seg2])
            await session.flush()

            # Esfuerzos simulados para seg1
            eff1 = StravaEffort(segment_id=seg1.id, athlete_name_raw="ALEXIS ARNOLD QUISPE", elapsed_time_sec=642, is_kom_qom=True)
            eff2 = StravaEffort(segment_id=seg1.id, athlete_name_raw="PATRICIO RATH DIAZ", elapsed_time_sec=685, is_kom_qom=False)
            eff3 = StravaEffort(segment_id=seg1.id, athlete_name_raw="ORIANA GONZALES", elapsed_time_sec=715, is_kom_qom=True)
            session.add_all([eff1, eff2, eff3])
            await session.commit()

        # Inscribir algunos corredores en Fecha 2 ("Vuelta a los Poblados") para testing del portal
        stage_2_id = stage_objs[2].id
        stmt_e2 = select(StageEntry).where(StageEntry.stage_id == stage_2_id)
        if not (await session.exec(stmt_e2)).first():
            # Inscribir los primeros 10 corredores de Fecha 1 en Fecha 2
            stmt_r10 = select(Rider).limit(10)
            top_riders = (await session.exec(stmt_r10)).all()
            for idx, r in enumerate(top_riders, start=1):
                session.add(StageEntry(
                    stage_id=stage_2_id,
                    rider_id=r.id,
                    category_id=cat_map["ELI"].id,
                    team_id=r.team_id,
                    bib_number=idx + 10,
                    payment_status=PaymentStatusEnum.PAID,
                    race_status=RaceStatusEnum.REGISTERED
                ))
            await session.commit()

    print("¡Seed completado exitosamente!")


if __name__ == "__main__":
    asyncio.run(seed_data())
