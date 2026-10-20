import pathlib
import re
from pydantic import model_validator
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
    #
    # La lista es la de PRODUCCIÓN: el sitio se sirve desde Cloudflare Pages
    # (`copa-macrosur-web.pages.dev`) y el dominio propio (`kuspideweb.com`).
    # Los puertos de localhost NO están en la lista: en desarrollo los cubre
    # el regex de abajo, que sólo se aplica si `ENVIRONMENT != production`.
    #
    # Antes la lista traía también los puertos de desarrollo y el regex
    # estaba activo SIEMPRE: en producción eso dejaba la API abierta a
    # cualquier página servida desde el portátil de cualquiera.
    CORS_ORIGINS: List[str] = [
        "https://copa-macrosur-web.pages.dev",
        "https://kuspideweb.com",
        "https://www.kuspideweb.com",
    ]

    # En desarrollo se acepta CUALQUIER puerto de localhost: así, si el
    # servidor del front cambia de puerto, el sitio no se rompe en silencio.
    # En producción queda desactivado: el regex de abajo sólo cubre
    # `localhost`, nunca un dominio de terceros.
    CORS_ORIGIN_REGEX: str = r"^https?://((localhost|127\.0\.0\.1)(:\d+)?)$"

    # Interruptor explícito del regex de localhost. El validador de abajo lo
    # apaga solo cuando `ENVIRONMENT=production`: es una red de seguridad
    # para que nadie deje el regex activo en el servidor.
    CORS_ALLOW_LOCALHOST: bool = True

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

    @model_validator(mode="after")
    def _apagar_localhost_en_produccion(self) -> "Settings":
        """En producción, el regex de localhost queda DESACTIVADO.

        El regex sólo tiene sentido en el portátil del desarrollador. Con él
        activo en producción, cualquier página servida desde el `localhost`
        de cualquiera puede leer la API.
        """
        if self.ENVIRONMENT == "production":
            self.CORS_ALLOW_LOCALHOST = False
        return self


settings = Settings()


def origen_permitido(origin: str | None) -> bool:
    """¿Este origen puede leer la API?

    La política se evalúa EN VIVO (no al arrancar el servidor): así el cambio
    de `ENVIRONMENT` no exige reiniciar, y la respuesta 429 del limitador
    puede llevar su propia cabecera de CORS — sin ella, el navegador
    escondería el 429 detrás de un error de CORS.
    """
    if not origin:
        return False
    # El regex de localhost es SÓLO de desarrollo: en producción no se aplica
    # aunque `CORS_ORIGINS` lo trajera por error.
    if settings.ENVIRONMENT != "production" and settings.CORS_ALLOW_LOCALHOST:
        patron = settings.CORS_ORIGIN_REGEX
        if patron and re.fullmatch(patron, origin):
            return True
    return origin in (settings.CORS_ORIGINS or [])

