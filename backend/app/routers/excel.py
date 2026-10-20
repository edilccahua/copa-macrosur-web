from fastapi import APIRouter, Depends, UploadFile, File, Response, Query, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from backend.app.core.config import settings
from backend.app.core.db import get_session
from backend.app.core.limits import detalle_excede_tope
from backend.app.core.security import verify_admin_key
from backend.app.services.excel_service import import_riders_from_excel, export_stage_results_to_excel

router = APIRouter(prefix="", tags=["Excel"])


@router.post("/stages/{stage_id}/import-excel")
async def import_excel_endpoint(
    stage_id: int,
    file: UploadFile = File(...),
    is_legacy: bool = Query(False, description="Activa el adapter legacy de LA JOYA EXTREME"),
    session: AsyncSession = Depends(get_session),
    admin_key: str = Depends(verify_admin_key)
):
    """
    Importación masiva transaccional de participantes o resultados desde archivo .xlsx.
    Procesa en memoria con openpyxl (cero disco local).
    Si hay errores de formato o validación, revierte todo y responde HTTP 422.
    """
    # Tope del archivo: se lee UN byte más que el límite para saber que se
    # pasó sin tragarse el archivo entero en memoria. El `Content-Length` ya
    # lo mira el middleware, pero aquí el corte es el DEFINITIVO (el
    # multipart engaña: el tamaño de la cabecera no es el del archivo).
    limite = settings.MAX_UPLOAD_BYTES
    content = await file.read(limite + 1)
    if len(content) > limite:
        raise HTTPException(status_code=413, detail=detalle_excede_tope(limite))
    result = await import_riders_from_excel(
        session=session,
        stage_id=stage_id,
        file_bytes=content,
        is_legacy_format=is_legacy
    )
    return result


@router.get("/stages/{stage_id}/export-excel")
async def export_excel_endpoint(
    stage_id: int,
    session: AsyncSession = Depends(get_session)
):
    """
    Genera en memoria un archivo Excel con 3 hojas:
    1. Resultados_Fecha
    2. Ranking_Acumulado_Individual
    3. Ranking_Equipos
    """
    excel_bytes = await export_stage_results_to_excel(session=session, stage_id=stage_id)
    filename = f"Resultados_Etapa_{stage_id}.xlsx"
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )
