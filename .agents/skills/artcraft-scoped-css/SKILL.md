---
name: artcraft-scoped-css
description: Sistema de diseño basado en GetArtCraft (Bento Grid, bordes finos, tipografía editorial, scroll motion) usando CSS Nativo Scoped y copia obligatoria desde /home/edilsonc/Documents/copiaartcraft sin Tailwind.
---

# Skill: Arquitectura CSS Nativa (Clon Estético GetArtCraft)

## 1. Regla Cero: Fuente de Referencia Obligatoria
- **Repositorio Fuente:** `/home/edilsonc/Documents/copiaartcraft`
- Cualquier agente que vaya a construir páginas, layouts, componentes visuales o estilos tiene la **obligación estricta** de leer, copiar y adaptar directamente los archivos de estilos y componentes de:
  - `copiaartcraft/src/styles/tokens.css` (tokens exactos medidos: `--bg`, `--bg-raised`, `--ink`, `--line`, `--accent`, etc.)
  - `copiaartcraft/src/styles/motion.css` (curvas de animación, transiciones)
  - `copiaartcraft/src/styles/display.css` (estilos tipográficos editoriales y display titles)
  - `copiaartcraft/src/styles/reset.css` (resets nativos)
  - `copiaartcraft/src/scripts/showcase-motion.ts` (animaciones de scroll y revelado)
  - `copiaartcraft/src/components/` (`GhostWord.astro`, `DisplayTitle.astro`, `HeroWordmark.astro`, `bento/BentoCard.astro`, `bento/SectionLabel.astro`, etc.)
- Todo el diseño visual se construye con **CSS Moderno Nativo** dentro de bloques `<style>` encapsulados (scoped) en cada archivo `.astro` o `.svelte`.
- **PROHIBIDO instalar o usar Tailwind CSS o Bootstrap.**

## 2. Generación de Assets Visuales con Nanobanana
- Si el agente activo es Gemini, debe crear y generar todas las imágenes requeridas (pósters de las 4 fechas, banners hero, badges de premios especiales, fondos) usando la herramienta `generate_image` (**nanobanana** / Imagen 3) con descripciones visuales acordes al ciclismo MTB de alta intensidad y estética editorial.

## 3. Especificaciones del Sistema de Diseño (Extracción Real)
- **Geometría Editorial:**
  - Los radios de borde son **esquinas rectas (`border-radius: 0`)** para mantener el diseño minimalista de GetArtCraft.
  - Bordes finos con alfa sobre tinta: `--line: #10101429` (16% en claro) y `--line-strong: #10101466`.
- **Tipografía y Números Tabulares:**
  - `--font-mono`: Obligatorio en todos los tiempos `HH:MM:SS.mmm` y dorsales (`font-variant-numeric: tabular-nums`) para que los números permanezcan fijos y no oscilen horizontalmente al actualizarse el cronómetro en vivo.
- **Rendimiento:**
  - Las animaciones de scroll y revelado (`copiaartcraft/src/scripts/showcase-motion.ts`) se aplican ÚNICAMENTE en páginas de escaparate (Home `/` y cabeceras de fechas).
  - En `/en-vivo` y `/admin/juez` está terminantemente prohibido cargar librerías de animación pesadas para no degradar el rendimiento móvil bajo el sol.
