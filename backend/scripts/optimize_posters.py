"""
Script para optimizar y convertir afiches de races/info/ a formato WebP
Genera versiones estándar 4:5 para tarjetas (Bento Grid) y versiones Full HD para detalle.
"""
import os
from PIL import Image

INFO_DIR = "races/info"
OUT_DIR = "frontend/public/images/posters"

os.makedirs(OUT_DIR, exist_ok=True)

TARGET_CARD_RATIO = 4.0 / 5.0 # 0.80
CARD_WIDTH = 720
CARD_HEIGHT = 900
MAX_FULL_DIM = 1200

POSTER_MAPPINGS = [
    {
        "source": "WhatsApp Image 2026-10-19 at 9.17.49 PM.jpeg",
        "prefix": "f1-la-joya-extreme",
        "top_bias": 0.05,
    },
    {
        "source": "z-xtreme-poster.jpeg",
        "prefix": "f2-z-xtreme",
        "top_bias": 0.05,
    },
    {
        "source": "retorno-poster.jpeg",
        "prefix": "f3-retorno-poblados",
        "top_bias": 0.02,
    },
    {
        "source": "WhatsApp Image 2026-10-19 at 9.18.17 PM.jpeg",
        "prefix": "f4-quequena-xtreme",
        "top_bias": 0.15,
    },
    {
        "source": "WhatsApp Image 2026-10-19 at 9.18.17 PM.jpeg",
        "prefix": "copa-macrosur-master",
        "top_bias": 0.10,
    },
    {
        "source": "vuelta-talamolle-poster.jpeg",
        "prefix": "extra-vuelta-talamolle",
        "top_bias": 0.05,
    },
    {
        "source": "clasica-poster.jpeg",
        "prefix": "extra-clasica-mollendo",
        "top_bias": 0.05,
    },
]

def make_card_crop(img: Image.Image, top_bias: float = 0.05) -> Image.Image:
    w, h = img.size
    current_ratio = w / h
    
    if abs(current_ratio - TARGET_CARD_RATIO) < 0.01:
        crop_box = (0, 0, w, h)
    elif current_ratio > TARGET_CARD_RATIO:
        # Demasiado ancha: recortar lados centrados
        new_w = int(h * TARGET_CARD_RATIO)
        offset_x = (w - new_w) // 2
        crop_box = (offset_x, 0, offset_x + new_w, h)
    else:
        # Demasiado alta: recortar verticalmente con bias hacia arriba
        new_h = int(w / TARGET_CARD_RATIO)
        diff_h = h - new_h
        offset_y = int(diff_h * top_bias)
        offset_y = max(0, min(diff_h, offset_y))
        crop_box = (0, offset_y, w, offset_y + new_h)
        
    cropped = img.crop(crop_box)
    return cropped.resize((CARD_WIDTH, CARD_HEIGHT), Image.Resampling.LANCZOS)

def make_full_version(img: Image.Image) -> Image.Image:
    w, h = img.size
    if max(w, h) <= MAX_FULL_DIM:
        return img
    if w >= h:
        new_w = MAX_FULL_DIM
        new_h = int(h * (MAX_FULL_DIM / w))
    else:
        new_h = MAX_FULL_DIM
        new_w = int(w * (MAX_FULL_DIM / h))
    return img.resize((new_w, new_h), Image.Resampling.LANCZOS)

def main():
    print(f"Procesando afiches desde {INFO_DIR}...")
    for item in POSTER_MAPPINGS:
        src_path = os.path.join(INFO_DIR, item["source"])
        if not os.path.exists(src_path):
            print(f"ALERTA: No se encontró {src_path}")
            continue
            
        with Image.open(src_path) as img:
            img = img.convert("RGB")
            prefix = item["prefix"]
            
            # 1. Versión Tarjeta 4:5
            card_img = make_card_crop(img, item.get("top_bias", 0.05))
            card_out = os.path.join(OUT_DIR, f"{prefix}-card.webp")
            card_img.save(card_out, format="WEBP", quality=85, method=6)
            card_size_kb = os.path.getsize(card_out) / 1024
            print(f"-> Tarjeta 4:5 guardada: {card_out} ({card_size_kb:.1f} KB)")
            
            # 2. Versión Full
            full_img = make_full_version(img)
            full_out = os.path.join(OUT_DIR, f"{prefix}-full.webp")
            full_img.save(full_out, format="WEBP", quality=85, method=6)
            full_size_kb = os.path.getsize(full_out) / 1024
            print(f"-> Full HD guardada: {full_out} ({full_size_kb:.1f} KB)")

    print("\n¡Optimización completada con éxito!")

if __name__ == "__main__":
    main()
