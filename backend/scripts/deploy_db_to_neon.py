"""
Sincroniza y despliega el estado de la base de datos local (SQLite) a Neon PostgreSQL (Producción).

- Actualiza `riders.strava_athlete_id`
- Sincroniza `strava_segments` (exactamente 5 por etapa, 15 en total)
- Sincroniza `strava_efforts` (342 para Fecha 1, 260 para Fecha 2, 0 para Fecha 3)
"""
import asyncio
import sqlite3
import asyncpg

NEON_URL = "postgresql://neondb_owner:***REMOVED***@ep-cool-mode-artnzlbi-pooler.c-4.us-west-2.aws.neon.tech/neondb"
SQLITE_PATH = "kuspide_mtb.db"


async def main():
    print("[*] Conectando a SQLite local...")
    s_con = sqlite3.connect(SQLITE_PATH)
    s_cur = s_con.cursor()

    print("[*] Conectando a Neon PostgreSQL en Oregon...")
    p_conn = await asyncpg.connect(NEON_URL)

    # 1. Sincronizar strava_athlete_id en riders
    print("\n--- 1. Sincronizando strava_athlete_id en tabla riders ---")
    s_cur.execute("SELECT id, strava_athlete_id FROM riders WHERE strava_athlete_id IS NOT NULL")
    local_riders_strava = s_cur.fetchall()
    print(f"[*] Corredores con strava_athlete_id en local: {len(local_riders_strava)}")

    updated_riders = 0
    for r_id, s_id in local_riders_strava:
        # Verificar en Neon si otro rider ya tiene ese strava_athlete_id
        holder = await p_conn.fetchval("SELECT id FROM riders WHERE strava_athlete_id = $1 AND id != $2", s_id, r_id)
        if holder:
            continue
        await p_conn.execute("UPDATE riders SET strava_athlete_id = $1 WHERE id = $2", s_id, r_id)
        updated_riders += 1
    print(f"[OK] {updated_riders} corredores actualizados con strava_athlete_id en Neon.")

    # 2. Sincronizar strava_segments
    print("\n--- 2. Sincronizando strava_segments en Neon ---")
    s_cur.execute("""
        SELECT stage_id, strava_segment_id, name, distance_m, average_grade, location, elevation_min_m, elevation_max_m, kind
        FROM strava_segments ORDER BY stage_id, id
    """)
    local_segments = s_cur.fetchall()
    print(f"[*] Segmentos locales oficiales: {len(local_segments)}")

    # Borrar esfuerzos previos para evitar conflictos de FK antes de tocar segmentos
    await p_conn.execute("DELETE FROM strava_efforts")
    await p_conn.execute("DELETE FROM strava_segments")

    # Insertar los 15 segmentos oficiales en Neon
    seg_map = {}  # (stage_id, strava_segment_id) -> neon_id
    for r in local_segments:
        stage_id, strava_seg_id, name, dist, grade, loc, ele_min, ele_max, kind = r
        neon_id = await p_conn.fetchval("""
            INSERT INTO strava_segments (
                stage_id, strava_segment_id, name, distance_m, average_grade, location, elevation_min_m, elevation_max_m, kind
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING id
        """, stage_id, strava_seg_id, name, dist, grade, loc, ele_min, ele_max, kind)
        seg_map[(stage_id, strava_seg_id)] = neon_id

    print(f"[OK] {len(seg_map)} segmentos insertados en Neon.")

    # Mapeo de local_segment_id a (stage_id, strava_segment_id)
    s_cur.execute("SELECT id, stage_id, strava_segment_id FROM strava_segments")
    local_seg_id_to_key = {r[0]: (r[1], r[2]) for r in s_cur.fetchall()}

    # 3. Sincronizar strava_efforts
    print("\n--- 3. Sincronizando strava_efforts en Neon ---")
    s_cur.execute("""
        SELECT segment_id, rider_id, athlete_name_raw, elapsed_time_sec, is_kom_qom, measured_on, strava_athlete_id, athlete_gender
        FROM strava_efforts
    """)
    local_efforts = s_cur.fetchall()
    print(f"[*] Total esfuerzos locales oficiales a transferir: {len(local_efforts)}")

    inserted_efforts = 0
    batch_records = []
    for eff in local_efforts:
        l_seg_id, rider_id, aname, secs, is_kom, measured_on, s_athlete_id, gender = eff
        key = local_seg_id_to_key.get(l_seg_id)
        if not key or key not in seg_map:
            continue
        neon_seg_id = seg_map[key]
        batch_records.append((
            neon_seg_id,
            rider_id,
            aname,
            secs,
            bool(is_kom),
            measured_on,
            s_athlete_id,
            gender,
        ))

    await p_conn.executemany("""
        INSERT INTO strava_efforts (
            segment_id, rider_id, athlete_name_raw, elapsed_time_sec, is_kom_qom, measured_on, strava_athlete_id, athlete_gender
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
    """, batch_records)
    print(f"[OK] {len(batch_records)} esfuerzos insertados con éxito en Neon PostgreSQL.")

    # 4. Verificación
    print("\n--- 4. Verificación final en Neon ---")
    f1_eff = await p_conn.fetchval("""
        SELECT COUNT(se.id) FROM strava_efforts se 
        JOIN strava_segments ss ON se.segment_id = ss.id 
        WHERE ss.stage_id = 1
    """)
    f2_eff = await p_conn.fetchval("""
        SELECT COUNT(se.id) FROM strava_efforts se 
        JOIN strava_segments ss ON se.segment_id = ss.id 
        WHERE ss.stage_id = 2
    """)
    f3_eff = await p_conn.fetchval("""
        SELECT COUNT(se.id) FROM strava_efforts se 
        JOIN strava_segments ss ON se.segment_id = ss.id 
        WHERE ss.stage_id = 3
    """)
    print(f"  · Fecha 1 esfuerzos en Neon: {f1_eff}")
    print(f"  · Fecha 2 esfuerzos en Neon: {f2_eff}")
    print(f"  · Fecha 3 esfuerzos en Neon: {f3_eff} (Limpio para cuando se corra)")

    await p_conn.close()
    s_con.close()
    print("\n[DEPLOY DB COMPLETADO CON ÉXITO]")


if __name__ == "__main__":
    asyncio.run(main())
