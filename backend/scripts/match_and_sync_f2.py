"""
Analiza y cruza los esfuerzos extraídos de Strava para Fecha 2 (Z Xtreme)
con los participantes registrados en la BD (167 corredores).

Incluye coincidencia flexible por tokens de nombre (evita rigidez de scripts),
actualiza `riders.strava_athlete_id` e inserta los registros en `strava_efforts`.
"""
import json
import re
import sqlite3
import unicodedata
from typing import Dict, List, Optional, Tuple

RAW_JSON = "races/strava_f2_raw_efforts.json"
DB_PATH = "kuspide_mtb.db"
STAGE_ID = 2
RACE_DATE_STR = "23 ago 2026"
RACE_DATE_ISO = "2026-08-23"

# Mapa de sinónimos / correcciones manuales identificadas para Arequipa
MANUAL_NAME_MAP = {
    "OSCAR CCOLQUE": "OSCAR CCOLQQUE LAROTA",
    "ALEXIS TANTANI": "ALEXIS ARNOLD QUISPE TANTANI",
    "JOSE ALFREDO REYNOSO SIMONI": "ALFREDO REYNOSO",
    "ARNALDO BUSCAGLIA EYZAGUIRRE": "ARNALDO BUSCAGLIA",
    "RONALD LUZA": "RONALD LUZA CALLO",
    "ALEJANDRA CACERES": "ALEJANDRA MELIZA CACERES",
    "VANIA MANRIQUE CHIRINOS": "VANIA MANRIQUE CHIRINOS",
    "CECILIA GUILLEN LOPEZ": "CECILIA GUILLEN LÓPEZ",
    "CAROLINA SALAS ZEGARRA": "CAROLINA SALAS ZEGARRA",
    "NAIDI GARCIA": "NAIDI GARCIA BAUTISTA",
    "VANESSA PATINO PUMA": "MIRIAM VANESSA PATIÑO",
    "LEONEL TINTAYA PINTO": "LEONEL TINTAYA PINTO",
    "JOSE VALVERDE PAREDES": "JOSE VALVERDE PAREDES",
    "BRANDON JOSSEHP QUISPE ZARATE": "BRANDON JOSSEHP QUISPE ZARATE",
    "ALESSANDRO VALDIVIA": "ALESSANDRO VALDIVIA ALARCON",
    "YEISON ZEBALLOS": "YEISON ZEBALLOS NUÑEZ DEL PRADO",
    "RICARDO CORNEJO BALLON": "RICARDO CORNEJO BALLON",
    "GUSTAVO OVIEDO": "GUSTAVO OVIEDO",
    "JUAN CARLOS RODRIGUEZ NEIRA": "JUAN CARLOS RODRIGUEZ NEIRA",
    "DAVID CONDORI": "DAVID CONDORI",
    "ANDRE ZARATE TORRES": "ANDRE ZARATE TORRES",
}


def normalize(text: str) -> str:
    if not text:
        return ""
    # Quitar emojis y caracteres no alfanuméricos
    text = re.sub(r"[^\w\s]", " ", text)
    # Normalizar acentos
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    # Quitar palabras clave de equipos / apodos comunes
    text = re.sub(r"\b(TEAM|CLUB|AYAYAY|BIKERS|LTR|PERU|PE)\b", "", text, flags=re.I)
    # Colapsar espacios y pasar a mayúsculas
    return " ".join(text.upper().split())


def parse_time_to_sec(time_str: str) -> Optional[int]:
    if not time_str or time_str == "—":
        return None
    parts = time_str.strip().split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except ValueError:
        return None
    return None


def load_stage_riders(cur) -> List[Dict]:
    cur.execute("""
        SELECT r.id, r.full_name, r.gender, r.strava_athlete_id, se.bib_number
        FROM stage_entries se
        JOIN riders r ON se.rider_id = r.id
        WHERE se.stage_id = ?
    """, (STAGE_ID,))
    riders = []
    for row in cur.fetchall():
        r_id, full_name, gender, strava_id, bib = row
        riders.append({
            "id": r_id,
            "full_name": full_name,
            "norm_name": normalize(full_name),
            "tokens": set(normalize(full_name).split()),
            "gender": gender,
            "strava_athlete_id": strava_id,
            "bib_number": bib,
        })
    return riders


def find_matching_rider(strava_name: str, strava_id: str, strava_gender: str, riders: List[Dict]) -> Tuple[Optional[Dict], str]:
    norm_s = normalize(strava_name)
    s_tokens = set(norm_s.split())

    # 1. Coincidencia directa por strava_athlete_id previo
    if strava_id:
        for r in riders:
            if r["strava_athlete_id"] and str(r["strava_athlete_id"]) == str(strava_id):
                return r, "strava_id_exact"

    # 2. Coincidencia por mapa manual
    if norm_s in MANUAL_NAME_MAP:
        target = normalize(MANUAL_NAME_MAP[norm_s])
        for r in riders:
            if r["norm_name"] == target:
                return r, "manual_map"

    # 3. Coincidencia exacta de nombre normalizado
    for r in riders:
        if r["norm_name"] == norm_s:
            return r, "exact_name"

    # 4. Inclusión de tokens (si los 2 o más nombres del ciclista en Strava están dentro de su nombre completo en BD)
    if len(s_tokens) >= 2:
        candidates = []
        for r in riders:
            # Compatibilidad de género
            if strava_gender and r["gender"] and strava_gender != r["gender"]:
                continue
            if s_tokens.issubset(r["tokens"]):
                candidates.append(r)
            # Manejo de doble Q en Ccolque/Ccolqque
            elif {t.replace("CCOLQQUE", "CCOLQUE") for t in s_tokens}.issubset({t.replace("CCOLQQUE", "CCOLQUE") for t in r["tokens"]}):
                candidates.append(r)

        if len(candidates) == 1:
            return candidates[0], "token_subset"

    # 5. Token overlap fuerte (mínimo 2 tokens coincidentes y mismo género)
    overlap_candidates = []
    for r in riders:
        if strava_gender and r["gender"] and strava_gender != r["gender"]:
            continue
        common = s_tokens.intersection(r["tokens"])
        if len(common) >= 2:
            overlap_candidates.append((r, len(common)))

    if overlap_candidates:
        overlap_candidates.sort(key=lambda x: x[1], reverse=True)
        # Solo si el mejor es único en su puntuación máxima
        if len(overlap_candidates) == 1 or overlap_candidates[0][1] > overlap_candidates[1][1]:
            return overlap_candidates[0][0], "token_overlap"

    return None, "unmatched"


def main():
    with open(RAW_JSON, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    # Mapeo de strava_segment_id -> db segment_id
    cur.execute("SELECT id, strava_segment_id, name FROM strava_segments WHERE stage_id = ?", (STAGE_ID,))
    db_segments = {r[1]: (r[0], r[2]) for r in cur.fetchall()}
    print(f"[*] Segmentos en BD para Fecha 2: {len(db_segments)}")

    riders = load_stage_riders(cur)
    print(f"[*] Corredores inscritos en Fecha 2: {len(riders)}")

    total_inserted = 0
    matched_riders = set()
    athlete_id_updates = {}

    for strava_seg_id, seg_info in raw_data.items():
        if strava_seg_id not in db_segments:
            print(f"[!] Segmento {strava_seg_id} no está en BD para etapa {STAGE_ID}, saltando.")
            continue

        db_seg_id, db_seg_name = db_segments[strava_seg_id]
        print(f"\n=======================================================")
        print(f"Procesando: {db_seg_name} (Strava ID: {strava_seg_id}, DB ID: {db_seg_id})")
        print(f"=======================================================")

        efforts = seg_info.get("efforts", [])

        # Borrar esfuerzos previos de este segmento para etapa 2
        cur.execute("DELETE FROM strava_efforts WHERE segment_id = ?", (db_seg_id,))

        matched_in_seg = 0
        unmatched_in_seg = 0

        for eff in efforts:
            athlete_name = eff.get("athleteName") or ""
            athlete_id = eff.get("athleteId")
            cells = eff.get("cells", [])
            gender = eff.get("gender")

            # Buscar fecha y tiempo en las celdas
            # Las celdas suelen ser: [Rank, Nombre, Fecha, Velocidad, FC, Potencia, Puntos, Duración]
            date_cell = None
            time_cell = None

            for c in cells:
                if any(m in c for m in ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic", "2026"]):
                    date_cell = c
                if re.match(r"^\d{1,2}:\d{2}(:\d{2})?$", c):
                    time_cell = c

            # Solo nos interesan los esfuerzos del día de la carrera (23 ago 2026)
            is_race_day = False
            if date_cell and "23 ago" in date_cell:
                is_race_day = True
            elif date_cell and "2026" in date_cell and ("22 ago" in date_cell or "24 ago" in date_cell):
                is_race_day = True

            # Si no es del día de carrera, no es un esfuerzo oficial de la Fecha 2
            if not is_race_day:
                continue

            elapsed_sec = parse_time_to_sec(time_cell)
            if not elapsed_sec:
                continue

            rider, match_type = find_matching_rider(athlete_name, athlete_id, gender, riders)

            if rider:
                matched_in_seg += 1
                matched_riders.add(rider["id"])

                # Guardar vinculación de strava_athlete_id
                if athlete_id and not rider["strava_athlete_id"]:
                    athlete_id_updates[rider["id"]] = athlete_id
                    rider["strava_athlete_id"] = athlete_id

                cur.execute("""
                    INSERT INTO strava_efforts (
                        segment_id, rider_id, athlete_name_raw,
                        elapsed_time_sec, is_kom_qom, measured_on,
                        strava_athlete_id, athlete_gender
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    db_seg_id,
                    rider["id"],
                    athlete_name,
                    elapsed_sec,
                    False,  # Se recalcula luego
                    RACE_DATE_ISO,
                    athlete_id,
                    gender,
                ))
                total_inserted += 1
                print(f"  ✓ [{gender}] {athlete_name:30} -> #{rider['bib_number']:3d} {rider['full_name']:32} ({elapsed_sec}s · {time_cell}) [{match_type}]")
            else:
                unmatched_in_seg += 1
                # Si el atleta corrió el día de la carrera pero no está en la lista oficial de inscritos de Fecha 2,
                # guardamos el esfuerzo con rider_id = NULL para integridad de datos según orden del usuario:
                # "guarda tiempo de segmentos de todos los atletas a pesar de que no aparezcan en lader board"
                cur.execute("""
                    INSERT INTO strava_efforts (
                        segment_id, rider_id, athlete_name_raw,
                        elapsed_time_sec, is_kom_qom, measured_on,
                        strava_athlete_id, athlete_gender
                    ) VALUES (?, NULL, ?, ?, ?, ?, ?, ?)
                """, (
                    db_seg_id,
                    athlete_name,
                    elapsed_sec,
                    False,
                    RACE_DATE_ISO,
                    athlete_id,
                    gender,
                ))
                total_inserted += 1
                print(f"  ? [{gender}] {athlete_name:30} (No inscrito en F2 · guardado para auditoría) ({elapsed_sec}s · {time_cell})")

        print(f"  Subtotal {db_seg_name}: {matched_in_seg} corredores inscritos cruzados, {unmatched_in_seg} no inscritos guardados.")

    # Actualizar strava_athlete_id en riders sin violar restricciones UNIQUE
    updated_count = 0
    for r_id, s_id in athlete_id_updates.items():
        # Verificar si otro corredor ya tiene este strava_athlete_id
        cur.execute("SELECT id FROM riders WHERE strava_athlete_id = ? AND id != ?", (s_id, r_id))
        existing_holder = cur.fetchone()
        if existing_holder:
            print(f"  [i] strava_athlete_id {s_id} ya pertenece a rider #{existing_holder[0]}, omitiendo asignación a rider #{r_id}.")
            continue
        cur.execute("UPDATE riders SET strava_athlete_id = ? WHERE id = ?", (s_id, r_id))
        updated_count += 1
    print(f"\n[*] Strava Athlete IDs actualizados en tabla riders: {updated_count}")

    con.commit()
    con.close()
    print(f"\n[OK] Sincronización finalizada. Total esfuerzos registrados en BD: {total_inserted}")


if __name__ == "__main__":
    main()
