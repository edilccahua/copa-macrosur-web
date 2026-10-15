import io
from typing import Optional
import boto3
from botocore.config import Config
from backend.app.core.config import settings


def get_r2_client():
    if not settings.R2_ACCOUNT_ID or not settings.R2_ACCESS_KEY_ID:
        return None
    endpoint_url = f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4")
    )


async def upload_file_to_r2(file_bytes: bytes, file_key: str, content_type: str = "application/octet-stream") -> str:
    """Sube un archivo en memoria hacia Cloudflare R2 y retorna la URL pública."""
    client = get_r2_client()
    if not client:
        # Modo local / fallback
        return f"{settings.R2_PUBLIC_URL_PREFIX}/{file_key}"

    client.upload_fileobj(
        io.BytesIO(file_bytes),
        settings.R2_BUCKET_NAME,
        file_key,
        ExtraArgs={"ContentType": content_type}
    )
    return f"{settings.R2_PUBLIC_URL_PREFIX}/{file_key}"
