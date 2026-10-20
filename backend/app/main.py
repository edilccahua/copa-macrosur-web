import sys
import pathlib

# Garantizar que la raíz del proyecto esté en sys.path tanto en local como en producción (Render)
_REPO_ROOT = str(pathlib.Path(__file__).resolve().parents[2])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from backend.app.core.config import settings, origen_permitido
from backend.app.core.db import init_db
from backend.app.core.limits import (
    RATE_LIMIT_RULES,
    RateLimitMiddleware,
    default_limiter_factory,
)
from backend.app.routers import timing, stages, riders, teams, excel, public, admin


class SettingsAwareCORSMiddleware(CORSMiddleware):
    """CORS cuya política de orígenes se consulta EN CADA petición.

    `CORSMiddleware` resuelve los orígenes AL ARRANCAR el servidor. Aquí la
    política vive en `settings` (`origen_permitido`) y se lee en cada
    petición: así las pruebas, que cambian la configuración en caliente, ven
    el cambio.

    OJO: `settings` se instancia al IMPORTAR el módulo, así que en
    PRODUCCIÓN cambiar `ENVIRONMENT` o `CORS_ORIGINS` en el entorno EXIGE
    reiniciar el servicio (en Render, un redeploy). Lo que se resuelve en
    caliente es sólo lo que las pruebas mutan en memoria.
    """

    def __init__(self, app, **kwargs):
        # La lista de orígenes la decide `origen_permitido`, no Starlette.
        # Se fuerza `allow_origins=[]` para que el middleware NUNCA entre por
        # la rama `allow_all_origins`: con `allow_origins=["*"]` y
        # `allow_credentials=True`, Starlette refleja el `Origin` del atacante
        # con `Access-Control-Allow-Credentials: true` SIN consultar la
        # política. Un `*` en `CORS_ORIGINS` es, además, el error de operador
        # más probable ("añado `*` para que no me dé error de CORS"): aquí se
        # ignora en vez de abrir la API.
        kwargs["allow_origins"] = []
        super().__init__(app, **kwargs)

    def is_allowed_origin(self, origin: str) -> bool:
        return origen_permitido(origin)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="API Oficial de Cronometraje y Ranking MTB Kúspide",
    version="1.0.0",
    lifespan=lifespan
)

# CORS
#
# El sitio se sirve desde Cloudflare Pages y la API desde Render: el
# navegador del visitante manda la cabecera `Origin`. Si el backend acepta
# cualquier origen, cualquiera puede leer la API desde su propia página.
#
# En desarrollo se acepta cualquier puerto de localhost: si el servidor del
# front cambia de puerto (Astro toma el siguiente libre si el 4321 está
# ocupado), el sitio no debe romperse en silencio — el SSR seguiría
# funcionando porque no lleva `Origin`, pero TODAS las islas de cliente
# (SSE, clasificaciones, formularios) fallarían.
#
# En producción (`ENVIRONMENT=production`) el regex se desactiva y sólo
# valen los orígenes de `CORS_ORIGINS`.
#
# `allow_methods` y `allow_headers` dejan de ser `"*"`: el cliente sólo usa
# esos tres verbos y esas tres cabeceras (la de contenido, la de
# administrador y la de juez).
#
# `allow_origins` se pasa VACÍO a propósito: la política la decide
# `origen_permitido` en cada petición (ver `SettingsAwareCORSMiddleware`).
# Si la lista de orígenes se pasara a Starlette, un `*` en `CORS_ORIGINS`
# haría que Starlette reflejase el `Origin` de cualquiera con credenciales.
cors_options = {
    "allow_origins": [],
    "allow_credentials": True,
    "allow_methods": ["GET", "POST", "OPTIONS"],
    "allow_headers": ["Content-Type", "X-Admin-Key", "X-Judge-Pin"],
}
# El regex de localhost NO se pasa al constructor: se aplica dentro de
# `origen_permitido`, que es donde vive toda la política.
app.add_middleware(SettingsAwareCORSMiddleware, **cors_options)

# GZip: las respuestas grandes de la API viajaban enteras por el cable entre
# Render y el navegador (el resumen de una fecha pesaba 64 KB). Comprimidas
# bajan a ~9 KB y el coste es cero para el cliente: el navegador y el CDN
# las descomprimen solos.
#
# `minimum_size=1000` deja fuera las respuestas diminutas (`/health`), donde
# comprimir sólo gastaría CPU, y comprime las grandes.
#
# La transmisión en vivo (SSE) NO se comprime: sus eventos son pequeños y
# seguidos, y comprimidos zlib los agruparía y el panel del juez los vería a
# ráfagas en vez de en vivo. Starlette excluye `text/event-stream` por
# defecto; el test `test_el_sse_no_se_comprime` lo fija.
#
# Se registra DESPUÉS del CORS y ANTES del limitador: `add_middleware` apila
# al revés, así que el limitador sigue siendo el primero que ve la petición
# (es él quien decide si la petición entra).
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Límites de entrada (cuota por IP, tope del cuerpo y tope del archivo).
#
# Se registra DESPUÉS del CORS porque `add_middleware` apila al revés: el
# ÚLTIMO registrado es el PRIMERO que se ejecuta. Así el limitador decide
# antes de que la petición llegue a la ruta.
#
# Y los preflight (OPTIONS) no gastan cuota: son la negociación de CORS, no
# trabajo real del servidor.
app.add_middleware(
    RateLimitMiddleware,
    rules=RATE_LIMIT_RULES,
    limiter_factory=default_limiter_factory,
)

# Routers bajo /api/v1
app.include_router(timing.router, prefix=settings.API_V1_PREFIX)
app.include_router(stages.router, prefix=settings.API_V1_PREFIX)
app.include_router(riders.router, prefix=settings.API_V1_PREFIX)
app.include_router(teams.router, prefix=settings.API_V1_PREFIX)
app.include_router(excel.router, prefix=settings.API_V1_PREFIX)
app.include_router(public.router, prefix=settings.API_V1_PREFIX)
app.include_router(admin.router, prefix=settings.API_V1_PREFIX)


@app.get("/health")
async def health_check():
    return {"status": "ok", "project": settings.PROJECT_NAME}


@app.get("/")
async def root():
    return {
        "message": "Bienvenido a la API de Kúspide MTB",
        "docs": "/docs",
        "api_v1": settings.API_V1_PREFIX
    }
