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
import secrets
import string
from typing import Dict

from backend.app.core.config import settings

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


__all__ = [
    "JUDGE_PIN_ENV",
    "PIN_ALPHABET",
    "PIN_LENGTH",
    "admin_key",
    "generate_pin",
    "judge_pin_for",
    "os_admin_key",
]
