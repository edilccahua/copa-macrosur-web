"""
Secretos del servidor.

Los secretos **nunca** viven en el repositorio: se leen del entorno (`.env`
en local, variables de entorno en Render). Este módulo es el único lugar del
backend donde se decide qué es un secreto y cómo se resuelve.

Por qué un módulo aparte:
  · el `seed` necesita los PIN de juez de las cuatro fechas;
  · los scripts de Strava necesitan la clave de administrador;
  · `admin/index.astro` (el panel del organizador) necesita lo mismo, pero en
    el navegador: ese caso lo resuelve el usuario con su gate, no este módulo.

Regla: un secreto que se puede leer en el código fuente o en el historial de
Git **deja de ser un secreto**. Por eso los PIN de juez se guardan en la base
de datos y se siembran desde el entorno, no desde `seed.py`.
"""
import os
import pathlib
import secrets
import string
from typing import Dict

from backend.app.core.config import settings

#: La raíz del repositorio, para leer el `.env` local cuando el script se
#: ejecuta sin `PYTHONPATH=.` (`backend/app/core` → `backend/app` → `backend`
#: → raíz).
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]

#: Longitud del PIN de juez: 4 caracteres en mayúsculas y dígitos, sin los
#: caracteres que se confunden al dictarlos por radio (`0/O`, `1/I/L`).
PIN_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
PIN_LENGTH = 4

#: Variables de entorno que guardan el PIN de cada fecha.
JUDGE_PIN_ENV = {1: "JUDGE_PIN_F1", 2: "JUDGE_PIN_F2", 3: "JUDGE_PIN_F3", 4: "JUDGE_PIN_F4"}


def generate_pin() -> str:
    """Un PIN de juez aleatorio, para desarrollo."""
    return "".join(secrets.choice(PIN_ALPHABET) for _ in range(PIN_LENGTH))


def judge_pin_for(stage_number: int) -> str:
    """El PIN de juez de una fecha.

    Se resuelve en este orden:

      1. la variable de entorno `JUDGE_PIN_F{n}` (Render en producción,
         `.env` en local);
      2. en desarrollo y sin la variable, un PIN aleatorio **impreso una
         sola vez** en consola: sirve para probar, y no queda en ningún
         archivo;
      3. en producción y sin la variable, un error: el servidor no debe
         arrancar con un PIN inventado que nadie conoce.

    El PIN se escribe en la base de datos (`stages.judge_pin`), no en el
    código: por eso puede rotarse sin tocar el repositorio.
    """
    env_name = JUDGE_PIN_ENV.get(stage_number)
    if env_name:
        value = getattr(settings, env_name, "").strip()
        if value:
            return value

    if settings.ENVIRONMENT == "production":
        raise RuntimeError(
            f"Falta la variable de entorno {env_name}: sin ella la fecha "
            f"{stage_number} se quedaría sin PIN de juez utilizable."
        )

    pin = generate_pin()
    print(f"[AVISO] PIN de juez temporal para la fecha {stage_number}: {pin}")
    return pin


def admin_key() -> str:
    """La clave de administrador del backend.

    Vacía significa "el servidor no tiene clave configurada": los endpoints
    de administración responden 503 (fail-closed) en vez de aceptar cualquier
    cosa. Antes el valor por defecto estaba en el código **y en el bundle del
    navegador**: la clave era pública.
    """
    return (settings.ADMIN_API_KEY or "").strip()


def os_admin_key() -> str:
    """La clave de administrador para los scripts locales.

    Los scripts se ejecutan en la máquina del organizador, fuera del servidor:
    leen la clave del entorno o del `.env` de la raíz del repositorio.
    """
    key = os.environ.get("ADMIN_API_KEY", "").strip()
    if key:
        return key
    return admin_key()


def _valor_del_env_local(nombre: str) -> str:
    """Lee una clave del `.env` de la raíz sin depender de `python-dotenv`.

    Se usa sólo cuando la variable no está en el entorno. Un `.env` ausente
    no es un error: devuelve cadena vacía y el llamador decide.
    """
    try:
        texto = (_REPO_ROOT / ".env").read_text(encoding="utf-8")
    except OSError:
        return ""
    for linea in texto.splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        if clave.strip() == nombre:
            return valor.strip().strip('"').strip("'")
    return ""


def _a_dsn_asyncpg(url: str) -> str:
    """`postgresql+asyncpg://` → `postgresql://` (lo que espera asyncpg)."""
    for prefijo in ("postgresql+asyncpg://", "postgres://"):
        if url.startswith(prefijo):
            return "postgresql://" + url[len(prefijo):]
    return url


def os_database_url() -> str:
    """La URL de PostgreSQL de PRODUCCIÓN para los scripts locales.

    Se resuelve en este orden: `NEON_DATABASE_URL` del entorno, `DATABASE_URL`
    del entorno (si es PostgreSQL), y las mismas dos claves en el `.env` de la
    raíz. Una `DATABASE_URL` de SQLite se ignora: este resolvedor es para los
    scripts que escriben en producción, no para el desarrollo local.

    Falla CERRADO con un mensaje accionable. El literal de la contraseña NO
    vive aquí ni en ningún script: la credencial de `neondb_owner` estuvo
    escrita en `backend/scripts/deploy_db_to_neon.py` y quedó publicada en el
    historial del repositorio (ver `CREDENCIALES_PRODUCCION.md` §6.2).
    """
    candidatos = (
        os.environ.get("NEON_DATABASE_URL", ""),
        os.environ.get("DATABASE_URL", ""),
        _valor_del_env_local("NEON_DATABASE_URL"),
        _valor_del_env_local("DATABASE_URL"),
    )
    for bruto in candidatos:
        url = _a_dsn_asyncpg(bruto.strip())
        if url.startswith("postgresql://"):
            return url

    raise RuntimeError(
        "No hay URL de PostgreSQL de producción. Define NEON_DATABASE_URL "
        "(o DATABASE_URL con un DSN de PostgreSQL) en el entorno o en el "
        "`.env` de la raíz del repositorio. La contraseña se obtiene de la "
        "consola de Neon; no se escribe en el código."
    )


__all__ = [
    "JUDGE_PIN_ENV",
    "PIN_ALPHABET",
    "PIN_LENGTH",
    "admin_key",
    "generate_pin",
    "judge_pin_for",
    "os_admin_key",
    "os_database_url",
]
