from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.core.config import settings
from backend.app.core.db import init_db
from backend.app.routers import timing, stages, riders, teams, excel, public, admin


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
# En desarrollo se acepta cualquier puerto de localhost: si el servidor del
# front cambia de puerto (Astro toma el siguiente libre si el 4321 está
# ocupado), el sitio no debe romperse en silencio — el SSR seguiría
# funcionando porque no lleva `Origin`, pero TODAS las islas de cliente
# (SSE, clasificaciones, formularios) fallarían.
#
# En producción (`ENVIRONMENT=production`) el regex se desactiva y sólo
# valen los orígenes de `CORS_ORIGINS`.
cors_options = {
    "allow_origins": settings.CORS_ORIGINS or ["*"],
    "allow_credentials": True,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
}
if settings.CORS_ORIGIN_REGEX:
    cors_options["allow_origin_regex"] = settings.CORS_ORIGIN_REGEX

app.add_middleware(CORSMiddleware, **cors_options)

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
