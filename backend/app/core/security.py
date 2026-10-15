from fastapi import Header, HTTPException, status
from backend.app.core.config import settings


async def verify_admin_key(x_admin_key: str = Header(None, alias="X-Admin-Key")) -> str:
    if not x_admin_key or x_admin_key != settings.ADMIN_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Credencial de Administrador inválida o ausente (X-Admin-Key)."
        )
    return x_admin_key


async def verify_judge_pin_header(x_judge_pin: str = Header(None, alias="X-Judge-Pin")) -> str:
    if not x_judge_pin:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Falta la cabecera X-Judge-Pin requerida para acciones del juez."
        )
    return x_judge_pin
