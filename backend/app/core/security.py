import hmac

from fastapi import Header, HTTPException, status

from backend.app.core.config import settings


async def verify_admin_key(x_admin_key: str = Header(None, alias="X-Admin-Key")) -> str:
    """Valida la clave de administrador.

    Falla CERRADO: si el servidor no tiene `ADMIN_API_KEY` configurada, NINGÚN
    endpoint de administración responde 200. Antes el valor por defecto estaba
    escrito en el código y en el bundle del navegador: la clave era pública y
    cualquiera podía aprobar pagos o pisar la base de datos con un Excel.

    El 503 (y no el 403) distingue "te equivocaste" de "el servidor está mal
    configurado": el 503 es un fallo de despliegue, no de credencial.
    """
    configured = settings.ADMIN_API_KEY
    if not configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El servidor no tiene ADMIN_API_KEY configurada.",
        )
    # `compare_digest` compara en tiempo constante (no filtra por-longitud) y
    # sólo admite texto ASCII: se comparan BYTES para que una cabecera con
    # tildes produzca un 403 y no un 500.
    if not x_admin_key or not hmac.compare_digest(
        x_admin_key.encode("utf-8"), configured.encode("utf-8")
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Credencial de Administrador inválida o ausente (X-Admin-Key).",
        )
    return x_admin_key


async def verify_judge_pin_header(x_judge_pin: str = Header(None, alias="X-Judge-Pin")) -> str:
    if not x_judge_pin:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Falta la cabecera X-Judge-Pin requerida para acciones del juez."
        )
    return x_judge_pin
