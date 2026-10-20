import sys
import pathlib

# Garantizar que la raíz del proyecto esté en sys.path tanto en local como en producción (Render)
_REPO_ROOT = str(pathlib.Path(__file__).resolve().parents[2])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.core.config import settings, origen_permitido
from backend.app.core.db import init_db
from backend.app.core.limits import (
    RATE_LIMIT_RULES,
    RateLimitMiddleware,
    default_limiter_factory,
)
from backend.app.routers import timing, stages, riders, teams, excel, public, admin


class SettingsAwareCORSMiddleware(CORSMiddleware):
    """CORS que consulta la configuración EN CADA petición.

    `CORSMiddleware` resuelve los orígenes AL ARRANCAR el servidor: con él,
    cambiar `ENVIRONMENT` (o escribir las pruebas) exigiría reiniciar, y la
    política de producción seguiría siendo la de desarrollo. Aquí la política
    vive en `settings` y se lee en cada petición.
    """

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
cors_options = {
    "allow_origins": settings.CORS_ORIGINS or [],
    "allow_credentials": True,
    "allow_methods": ["GET", "POST", "OPTIONS"],
    "allow_headers": ["Content-Type", "X-Admin-Key", "X-Judge-Pin"],
}
# El regex de localhost NO se pasa al constructor: se aplica en vivo, dentro
# de `origen_permitido`, para que `ENVIRONMENT=production` lo apague sin
# necesidad de reiniciar el servidor.
app.add_middleware(SettingsAwareCORSMiddleware, **cors_options)

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
