---
name: artcraft-scoped-css
description: Sistema de diseño basado en GetArtCraft (Bento Grid oscuro, bordes finos, tipografía editorial) usando CSS Nativo Scoped y Variables CSS sin Tailwind.
---

# Skill: Arquitectura CSS Nativa (Clon Estético GetArtCraft)

## 1. Regla Cero: Prohibido Tailwind y Estilos en Línea
- Todo el diseño visual se construye con **CSS Moderno Nativo** dentro de bloques `<style>` encapsulados (scoped) en cada archivo `.astro` o `.svelte`.
- Ningún componente puede usar colores hexadecimales o medidas arbitrarias "quemadas". Todos deben consumir las variables definidas en `frontend/src/styles/tokens.css`.

## 2. Estructura de `src/styles/tokens.css` (Alimentado por `open-design`)
El archivo global de tokens debe definir las primitivas extraídas de GetArtCraft:
- **Paleta Oscura de Alto Contraste (Surface & Ink):**
  - `--bg-canvas`: Fondo principal ultra oscuro (`#09090b` o token exacto de `open-design`).
  - `--bg-bento-card`: Superficie de tarjeta modular (`#121215`).
  - `--bg-bento-hover`: Superficie interactiva (`#18181c`).
  - `--border-hairline`: Bordes expuestos de `1px solid rgba(255, 255, 255, 0.08)`.
  - `--text-primary`: Blanco hueso de alta legibilidad (`#f4f4f6`).
  - `--text-muted`: Gris técnico para etiquetas y metadatos (`#8e8e98`).
  - `--accent-race`: Color de acento de competición (para líder general, KOM y cronómetro).
  - `--status-up`: Verde esmeralda (`#10b981`) para flechas de subida `▲ +N`.
  - `--status-down`: Rojo coral (`#f43f5e`) para flechas de bajada `▼ -N`.
- **Geometría Bento Grid:**
  - `--radius-bento`: `20px` en Desktop, `14px` en Mobile.
  - `--gap-bento`: `16px` en Desktop, `10px` en Mobile.
  - `--font-mono`: Fuente monoespaciada con `font-variant-numeric: tabular-nums` (OBLIGATORIO en todos los tiempos `HH:MM:SS.mmm` y dorsales para que los números nunca bailen horizontalmente al correr el cronómetro).

## 3. Reglas de Maquetación Mobile-First y Rendimiento
1. **Bento Grid Responsivo:** En móvil (`< 768px`), las grillas Bento se apilan en 1 o máximo 2 columnas (`grid-template-columns: repeat(2, 1fr)` para métricas cortas como "Más Rápido" / "Más Lento"). En Desktop (`>= 1024px`), se expanden a grillas asimétricas de 12 columnas.
2. **Presupuesto de Animación (GSAP):**
   - GSAP (`ScrollTrigger`) solo puede importarse en el layout de escaparate (`Home` y cabecera de `Stage`).
   - Envolver siempre en `window.matchMedia('(prefers-reduced-motion: no-preference)')`.
   - En `/en-vivo` y `/admin/*`, solo se permiten transiciones CSS nativas de `transform` y `opacity`.
