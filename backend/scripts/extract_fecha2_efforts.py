"""
Script de extraccion segura y organica para Fecha 2 (Z Xtreme) usando browser-use.
Guarda los resultados crudos inmediatamente en `races/strava_f2_raw_efforts.json`.
"""
import json
import os
import random
import sys
import time

SEGMENTS = [
    {"id": "36718652", "name": "Alterna Giriguaya", "role": "Subida Reina KOM/QOM"},
    {"id": "27868955", "name": "Z de desenfreno 🔥", "role": "Bajada Reina Kamikazes"},
    {"id": "12875208", "name": "Corte_Mollebaya", "role": "Muro Explosivo"},
    {"id": "40129265", "name": "EL PRIMER OBSTACULO", "role": "Muro Tecnico"},
    {"id": "36718907", "name": "Subida giriguaya a la entrada a la Z", "role": "Ascenso Sostenido"},
]

OUTPUT_FILE = "races/strava_f2_raw_efforts.json"


def set_filter(filter_value: str) -> str:
    return js(f"""
    (() => {{
        const getProps = (ctrl) => {{
            const key = Object.keys(ctrl).find(k => k.startsWith('__reactFiber$'));
            if (!key) return null;
            let fiber = ctrl[key];
            for (let i = 0; i < 25 && fiber; i++) {{
                const props = fiber.memoizedProps;
                if (props && props.options && props.onChange) return props;
                fiber = fiber.return;
            }}
            return null;
        }};
        
        const controls = [...document.querySelectorAll('div[class*="css-lruqgf-control"], div[class*="-control"]')];
        for (const c of controls) {{
            const props = getProps(c);
            if (props && props.options && props.options.some(o => o.value === '{filter_value}')) {{
                const opt = props.options.find(o => o.value === '{filter_value}');
                props.onChange(opt);
                return 'changed to {filter_value}';
            }}
        }}
        return 'not found';
    }})()
    """)


def read_table_rows():
    return js("""
    (() => {
        return Array.from(document.querySelectorAll('table tbody tr')).map(tr => {
            const a = tr.querySelector('a[href*="/athletes/"]');
            let id = null;
            if (a) {
                const m = a.href.match(/athletes\\/([0-9]+)/);
                if (m) id = m[1];
            }
            return {
                athleteName: a ? a.innerText.trim() : null,
                athleteId: id,
                cells: Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim())
            };
        });
    })()
    """)


def click_next_page():
    return js("""
    (() => {
        const btn = document.querySelector('button[aria-label*="next_page"]');
        if (btn && !btn.disabled) {
            btn.click();
            return true;
        }
        return false;
    })()
    """)


def extract():
    results = {}
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                results = json.load(f)
            print(f"[*] Respaldo previo cargado con {len(results)} segmentos.", file=sys.stderr)
        except Exception:
            results = {}

    for seg in SEGMENTS:
        seg_id = seg["id"]
        seg_name = seg["name"]

        if seg_id in results and len(results[seg_id].get("efforts", [])) > 0:
            print(f"[SKIP] Segmento {seg_id} ({seg_name}) ya extraído.", file=sys.stderr)
            continue

        url = f"https://www.strava.com/segments/{seg_id}"
        print(f"\n[+] Navegando a segmento {seg_id}: {seg_name} ({seg['role']}) -> {url}", file=sys.stderr)
        goto_url(url)
        time.sleep(random.uniform(8.0, 10.0))

        seg_efforts = []

        # 1. Filtro "Este año"
        res_time = set_filter("this_year")
        time.sleep(random.uniform(2.5, 3.5))

        # 2. Mujeres
        res_female = set_filter("female")
        time.sleep(random.uniform(3.0, 4.0))

        page = 1
        while True:
            rows = read_table_rows()
            print(f"    - Mujeres P{page}: {len(rows)} filas", file=sys.stderr)
            for r in rows:
                if r["athleteName"]:
                    r["gender"] = "F"
                    r["page"] = page
                    seg_efforts.append(r)
            if not click_next_page():
                break
            page += 1
            time.sleep(random.uniform(3.0, 4.0))

        # 3. Hombres
        res_male = set_filter("male")
        time.sleep(random.uniform(3.0, 4.0))

        page = 1
        while page <= 4:
            rows = read_table_rows()
            print(f"    - Hombres P{page}: {len(rows)} filas", file=sys.stderr)
            for r in rows:
                if r["athleteName"]:
                    r["gender"] = "M"
                    r["page"] = page
                    seg_efforts.append(r)
            if not click_next_page():
                break
            page += 1
            time.sleep(random.uniform(3.0, 4.0))

        results[seg_id] = {
            "id": seg_id,
            "name": seg_name,
            "role": seg["role"],
            "total_extracted": len(seg_efforts),
            "efforts": seg_efforts,
        }

        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"[*] Segmento {seg_id} guardado con éxito ({len(seg_efforts)} esfuerzos).", file=sys.stderr)

        time.sleep(random.uniform(9.0, 12.0))

    print("\n[OK] Extracción segura completada.", file=sys.stderr)


if __name__ in ("__main__", "browser_harness.run"):
    extract()
