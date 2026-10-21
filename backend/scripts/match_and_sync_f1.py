"""
Analiza y cruza los esfuerzos extraídos de Strava para Fecha 1 (La Joya Extreme)
con los participantes registrados en la BD (225 corredores).

Filtra ESTRICTAMENTE la fecha de la carrera (17 may 2026 / 2026-05-17),
actualiza `riders.strava_athlete_id` e inserta los registros en `strava_efforts`.
"""
import json
import re
import sqlite3
import unicodedata
from typing import Dict, List, Optional, Tuple

RAW_JSON = "races/strava_f1_raw_efforts.json"
DB_PATH = "kuspide_mtb.db"
STAGE_ID = 1
RACE_DATE_ISO = "2026-05-17"

MANUAL_NAME_MAP = {
    "EDILSON CCAHUA": "EDILSON CCAHUA CCAHUA",
    "ANTHONY CHUCTAYA": "ANTHONY JOEL MAMANI CHUCTAYA",
    "OSCAR CCOLQUE": "OSCAR CCOLQQUE LAROTA",
    "ALEXIS TANTANI": "ALEXIS ARNOLD QUISPE TANTANI",
    "JOSE ALFREDO REYNOSO SIMONI": "ALFREDO REYNOSO",
    "RONALD LUZA": "RONALD LUZA CALLO",
    "ANGEL CHAMBI MAMANI": "ANGEL HECTOR CHAMBI MAMANI",
    "ALEJANDRA CACERES": "ALEJANDRA MELIZA CACERES",
    "CECILIA GUILLEN LOPEZ": "CECILIA GUILLEN LÓPEZ",
    "CAROLINA SALAS ZEGARRA": "CAROLINA SALAS ZEGARRA",
    "SANDRA APAZA NANO": "SANDRA APAZA NANO",
    "KELICITA AGUILAR": "KELICITA AGUILAR",
    "VANESSA PATINO PUMA": "MIRIAM VANESSA PATIÑO",
    "VICTORIA Y": "VICTORIA YUPANQUI",
    "IRENE ALFARO VIZCARRA": "IRENE ALFARO VIZCARRA",
    "RODRIGO SANCHEZ HUAYTA": "RODRIGO SANCHEZ HUAYTA",
    "SILVIO ANCCO": "SILVIO ANCCO",
    "YEISON ZEBALLOS": "YEISON ZEBALLOS NUÑEZ DEL PRADO",
    "OSCAR CARDENAS": "OSCAR CARDENAS SANCHEZ",
    "HAYLER SHIRU LUJAN": "HAYLER SHIRU LUJAN",
    "GONZALO MALAGA": "GONZALO MALAGA ZEBALLOS",
    "REYNER BELLIDO FUENTES": "REYNER BELLIDO FUENTES",
    "ENRIQUE FERNANDEZ": "ENRIQUE FERNANDEZ",
    "FRANCO BENJAMIN": "FRANCO BENJAMIN",
    "JUAN JOSE ALVAREZ MARTINEZ": "JUAN JOSE ALVAREZ MARTINEZ",
    "JOSE MAQUE": "JOSE MAQUE",
    "GIOVANNI CHAVEZ VELANDO R": "GIOVANNI CHAVEZ VELANDO RODRIGUEZ",
    "ANTON RAMSAK": "ANTON RAMSAK",
    "VICTOR ALFONSO JIMENEZ": "VICTOR ALFONSO JIMENEZ",
    "BRANDON JOSSEHP QUISPE ZARATE": "BRANDON JOSSEHP QUISPE ZARATE",
    "PERSY ROQUE": "PERSY ROQUE MOLINA",
    "JUAN AGUSTIN FERNANDEZ SANTOS": "JUAN AGUSTIN FERNANDEZ SANTOS",
}


def normalize(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"[^\w\s]", " ", text)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"\b(TEAM|CLUB|AYAYAY|BIKERS|LTR|PERU|PE)\b", "", text, flags=re.I)
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

    if strava_id:
        for r in riders:
            if r["strava_athlete_id"] and str(r["strava_athlete_id"]) == str(strava_id):
                return r, "strava_id_exact"

    if norm_s in MANUAL_NAME_MAP:
        target = normalize(MANUAL_NAME_MAP[norm_s])
        for r in riders:
            if r["norm_name"] == target:
                return r, "manual_map"

    for r in riders:
        if r["norm_name"] == norm_s:
            return r, "exact_name"

    if len(s_tokens) >= 2:
        candidates = []
        for r in riders:
            if strava_gender and r["gender"] and strava_gender != r["gender"]:
                continue
            if s_tokens.issubset(r["tokens"]):
                candidates.append(r)
            elif {t.replace("CCOLQQUE", "CCOLQUE") for t in s_tokens}.issubset({t.replace("CCOLQQUE", "CCOLQUE") for t in r["tokens"]}):
                candidates.append(r)

        if len(candidates) == 1:
            return candidates[0], "token_subset"

    overlap_candidates = []
    for r in riders:
        if strava_gender and r["gender"] and strava_gender != r["gender"]:
            continue
        common = s_tokens.intersection(r["tokens"])
        if len(common) >= 2:
            overlap_candidates.append((r, len(common)))

    if overlap_candidates:
        overlap_candidates.sort(key=lambda x: x[1], reverse=True)
        if len(overlap_candidates) == 1 or overlap_candidates[0][1] > overlap_candidates[1][1]:
            return overlap_candidates[0][0], "token_overlap"

    return None, "unmatched"


def main():
    with open(RAW_JSON, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    cur.execute("SELECT id, strava_segment_id, name FROM strava_segments WHERE stage_id = ?", (STAGE_ID,))
    db_segments = {r[1]: (r[0], r[2]) for r in cur.fetchall()}
    print(f"[*] Segmentos en BD para Fecha 1: {len(db_segments)}")

    riders = load_stage_riders(cur)
    print(f"[*] Corredores inscritos en Fecha 1: {len(riders)}")

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

        # Borrar esfuerzos previos de este segmento para etapa 1
        cur.execute("DELETE FROM strava_efforts WHERE segment_id = ?", (db_seg_id,))

        matched_in_seg = 0
        unmatched_in_seg = 0

        for eff in efforts:
            athlete_name = eff.get("athleteName") or ""
            athlete_id = eff.get("athleteId")
            cells = eff.get("cells", [])
            gender = eff.get("gender")

            date_cell = None
            time_cell = None

            for c in cells:
                if any(m in c for m in ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic", "2026"]):
                    date_cell = c
                if re.match(r"^\d{1,2}:\d{2}(:\d{2})?$", c):
                    time_cell = c

            # Fecha oficial de la Fecha 1: 17 de mayo de 2026
            is_race_day = False
            if date_cell and "17 may" in date_cell:
                is_race_day = True
            elif date_cell and "2026" in date_cell and ("16 may" in date_cell or "18 may" in date_cell):
                is_race_day = True

            if not is_race_day:
                continue

            elapsed_sec = parse_time_to_sec(time_cell)
            if not elapsed_sec:
                continue

            rider, match_type = find_matching_rider(athlete_name, athlete_id, gender, riders)

            if rider:
                matched_in_seg += 1
                matched_riders.add(rider["id"])

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
                    False,
                    RACE_DATE_ISO,
                    athlete_id,
                    gender,
                ))
                total_inserted += 1
                print(f"  ✓ [{gender}] {athlete_name:30} -> #{rider['bib_number']:3d} {rider['full_name']:32} ({elapsed_sec}s · {time_cell}) [{match_type}]")
            else:
                unmatched_in_seg += 1
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
                print(f"  ? [{gender}] {athlete_name:30} (No inscrito en F1 · guardado para auditoría) ({elapsed_sec}s · {time_cell})")

        print(f"  Subtotal {db_seg_name}: {matched_in_seg} corredores inscritos cruzados, {unmatched_in_seg} no inscritos guardados.")

    updated_count = 0
    for r_id, s_id in athlete_id_updates.items():
        cur.execute("SELECT id FROM riders WHERE strava_athlete_id = ? AND id != ?", (s_id, r_id))
        existing_holder = cur.fetchone()
        if existing_holder:
            continue
        cur.execute("UPDATE riders SET strava_athlete_id = ? WHERE id = ?", (s_id, r_id))
        updated_count += 1
    print(f"\n[*] Strava Athlete IDs actualizados en tabla riders: {updated_count}")

    # Asignar is_kom_qom para Fecha 1:
    # 1. Perro rabioso - trepada (DB ID: 3) -> KOM y QOM
    cur.execute("""
        UPDATE strava_efforts SET is_kom_qom = 1
        WHERE id IN (
            SELECT id FROM strava_efforts WHERE segment_id = 3 AND athlete_gender = 'M' AND rider_id IS NOT NULL ORDER BY elapsed_time_sec ASC LIMIT 1
        ) OR id IN (
            SELECT id FROM strava_efforts WHERE segment_id = 3 AND athlete_gender = 'F' AND rider_id IS NOT NULL ORDER BY elapsed_time_sec ASC LIMIT 1
        )
    """)
    print(f"[*] KOM/QOM asignado en segmento Perro rabioso.")

    # 2. La encalaminadora Quishuarani (DB ID: 6) -> Kamikazes
    cur.execute("""
        UPDATE strava_efforts SET is_kom_qom = 1
        WHERE id IN (
            SELECT id FROM strava_efforts WHERE segment_id = 6 AND athlete_gender = 'M' AND rider_id IS NOT NULL ORDER BY elapsed_time_sec ASC LIMIT 1
        ) OR id IN (
            SELECT id FROM strava_efforts WHERE segment_id = 6 AND athlete_gender = 'F' AND rider_id IS NOT NULL ORDER BY elapsed_time_sec ASC LIMIT 1
        )
    """)
    print(f"[*] Kamikaze M/F asignado en segmento La encalaminadora.")

    con.commit()
    con.close()
    print(f"\n[OK] Sincronización Fecha 1 finalizada. Total esfuerzos registrados en BD: {total_inserted}")


if __name__ == "__main__":
    main()
