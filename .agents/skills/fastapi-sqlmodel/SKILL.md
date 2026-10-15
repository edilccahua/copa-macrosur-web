---
name: fastapi-sqlmodel
description: Reglas de arquitectura para el backend en FastAPI, SQLModel (Pydantic v2 + SQLAlchemy 2.0 asíncrono), PostgreSQL en Neon y procesamiento en memoria.
---

# Skill: FastAPI + SQLModel + Neon Serverless

## 1. Estructura de Carpetas del Backend
Mantén una arquitectura limpia por dominios dentro de `backend/app/`:
- `core/config.py`: Variables de entorno con `pydantic-settings`.
- `core/db.py`: Motor asíncrono (`create_async_engine`) y generador de sesiones (`AsyncSession`).
- `models/`: Modelos `SQLModel` (`table=True` y esquemas de lectura/escritura).
- `routers/`: Endpoints agrupados por dominio (`stages.py`, `riders.py`, `excel.py`, `timing.py`).
- `services/`: Lógica pesada de negocio (cálculo de rankings, parseo de Excel y GPX).
- `tests/`: Tests automatizados con `pytest` y `httpx.AsyncClient`.

## 2. Reglas Estrictas de Base de Datos (Neon PostgreSQL)
1. **Driver Asíncrono:** La URL de conexión debe usar `postgresql+asyncpg://...`.
2. **Protección contra Cold-Starts de Neon:** Al instanciar `create_async_engine`, es OBLIGATORIO incluir:
   - `pool_pre_ping=True` (verifica que la conexión siga viva tras un reposo serverless).
   - `pool_recycle=300` (recicla conexiones cada 5 minutos).
3. **Prohibido usar disco local:** Render Free tiene sistema de archivos efímero. Todo archivo subido (`UploadFile` de Excel o `.gpx`) debe procesarse en memoria usando `io.BytesIO(await file.read())` o subirse directamente a Cloudflare R2.

## 3. Reglas de Sintaxis SQLModel y Pydantic v2
- **PROHIBIDO** usar métodos deprecados de Pydantic v1 como `.dict()`, `.parse_obj()` o `class Config: orm_mode = True`.
- **OBLIGATORIO** usar sintaxis Pydantic v2: `.model_dump()`, `.model_validate()` y `model_config = ConfigDict(from_attributes=True)`.
- En consultas de SQLModel, usa siempre `select(Modelo)` importado de `sqlmodel` y ejecuta con `await session.exec(statement)`.

## 4. Manejo de Errores Consistente
Todo error de validación de negocio (ej. errores en filas de un archivo Excel) debe devolver un código HTTP `422 Unprocessable Entity` o `400 Bad Request` con una estructura JSON clara:
`{"detail": "Mensaje general", "errors": [{"row": 14, "field": "bib_number", "message": "Dorsal duplicado en esta fecha"}]}`.
