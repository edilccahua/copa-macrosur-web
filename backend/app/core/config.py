import pathlib
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

# La raíz del repositorio: el `.env` vive aquí (`backend/app/core/config.py`
# → `backend/app/core` → `backend/app` → `backend` → raíz). Antes el
# `env_file` era relativo al directorio de trabajo, así que el `.env` se
# encontraba en un sitio u otro según dónde se lanzara el servidor.
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    PROJECT_NAME: str = "Kúspide MTB Web"
    API_V1_PREFIX: str = "/api/v1"
    DATABASE_URL: str = "sqlite+aiosqlite:///./kuspide_mtb.db"

    # Clave de administrador de la API. SIN VALOR POR DEFECTO: si el servidor
    # no la tiene configurada, los endpoints de administración responden 503
    # (fail-closed) en vez de aceptar la clave que estaba escrita en el
    # código y en el bundle del navegador.
    ADMIN_API_KEY: str = ""

    # PIN de juez de cada fecha. NUNCA están en el repositorio: se siembran
    # en la base de datos desde aquí (ver `backend/app/core/secrets.py`) y se
    # rotan cambiando la variable y reejecutando el sembrado.
    JUDGE_PIN_F1: str = ""
    JUDGE_PIN_F2: str = ""
    JUDGE_PIN_F3: str = ""
    JUDGE_PIN_F4: str = ""

    # `development` habilita cualquier puerto de localhost en CORS.
    # `production` lo desactiva: sólo valen los orígenes de la lista.
    ENVIRONMENT: str = "development"

    # CORS: se puede sobreescribir en `.env` con un array JSON.
    # La lista incluye varios puertos de desarrollo porque Astro toma el
    # siguiente libre si el 4321 está ocupado: con una lista fija, el sitio
    # "funciona" en el servidor (el SSR no lleva Origin) pero TODAS las islas
    # de cliente fallan en silencio (SSE, clasificaciones, formularios).
    # En producción hay que poner aquí el dominio real.
    CORS_ORIGINS: List[str] = [
        "http://localhost:4321",
        "http://127.0.0.1:4321",
        "http://localhost:4322",
        "http://127.0.0.1:4322",
        "http://localhost:4323",
        "http://127.0.0.1:4323",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://kuspideweb.com",
        "https://www.kuspideweb.com",
    ]

    # En desarrollo se acepta CUALQUIER puerto de localhost: así, si el
    # servidor del front cambia de puerto, el sitio no se rompe en silencio.
    # En producción queda desactivado: el regex de abajo sólo cubre
    # `localhost`, nunca un dominio de terceros.
    CORS_ORIGIN_REGEX: str = r"^https?://((localhost|127\.0\.0\.1)(:\d+)?)$"

    # Cloudflare R2
    R2_ACCOUNT_ID: str = ""
    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_BUCKET_NAME: str = "kuspide-assets"
    R2_PUBLIC_URL_PREFIX: str = "https://assets.kuspideweb.com"

    model_config = SettingsConfigDict(
        env_file=(
            _REPO_ROOT / ".env",
            _REPO_ROOT / "backend" / ".env",
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
