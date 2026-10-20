from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    PROJECT_NAME: str = "Kúspide MTB Web"
    API_V1_PREFIX: str = "/api/v1"
    DATABASE_URL: str = "sqlite+aiosqlite:///./kuspide_mtb.db"
    ADMIN_API_KEY: str = "***REMOVED-ADMIN-API-KEY***"
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
    ]
    
    # Cloudflare R2
    R2_ACCOUNT_ID: str = ""
    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_BUCKET_NAME: str = "kuspide-assets"
    R2_PUBLIC_URL_PREFIX: str = "https://assets.kuspideweb.com"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
