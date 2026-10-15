---
name: strava-playwright
description: Automatización local vía Chrome DevTools Protocol (CDP) / browser-use para extraer esfuerzos de segmentos de Strava con sesión Premium existente y enviarlos a FastAPI.
---

# Skill: Extracción Local de Segmentos Strava (CDP / Playwright)

## 1. Regla de Seguridad Anti-Baneo
- Este script NUNCA se despliega ni ejecuta en Render ni en servidores Cloud (IPs de centros de datos son bloqueadas por Cloudflare/Strava).
- Se ejecuta exclusivamente en la máquina local del administrador conectándose a una instancia real de Chrome/Chromium abierta con `--remote-debugging-port=9222` donde el administrador ya inició sesión con su cuenta Strava Premium.

## 2. Flujo de Extracción y Cruce
1. Conectar vía `playwright.chromium.connect_over_cdp("http://localhost:9222")` (o mediante agente `/browser-use` adjunto al perfil local).
2. Navegar a cada URL de segmento configurada para la fecha (`https://www.strava.com/segments/{strava_segment_id}`).
3. Aplicar el filtro visual de tabla de posiciones: **"Hoy" (Today)** o fecha específica del evento para ver a todos los participantes públicos (sean cuentas gratuitas o de pago).
4. Extraer de la tabla del DOM: `athlete_name`, `strava_athlete_id` (desde el `href` del perfil), `elapsed_time_raw` (convertido a segundos enteros) y fecha/hora.
5. Enviar el payload JSON consolidado al endpoint protegido `POST /api/v1/stages/{stage_id}/sync-strava-efforts` usando la `ADMIN_API_KEY`.
