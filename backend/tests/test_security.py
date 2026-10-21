"""
Tests de seguridad del contrato de lectura público.

El PIN de juez es una credencial: con él se pueden mandar marcaciones de
cronometraje falsas (`/timing/events`) y largar mangas (`/waves/*/start`). Por
eso **ningún endpoint público puede devolverlo** (specs/00 §1.4).

La garantía no es "quitar el campo a mano" en cada endpoint: es el
`response_model` de cada ruta. Estos tests fijan ese contrato para las cuatro
lecturas de `/api/v1/stages`.

Aquí viven también las otras tres fronteras de seguridad del backend:

  · la clave de administrador **falla cerrada** (503 si el servidor no la
    tiene, 403 si la que llega no es la buena);
  · el CORS **cerrado en producción** (sólo los orígenes de la lista, nunca
    un `*.pages.dev` arbitrario ni un localhost);
  · los **límites de entrada** (ventana deslizante por IP, tope del cuerpo
    JSON y tope del archivo subido).
"""
import datetime
import io

import openpyxl
import pytest

from backend.app.core.config import settings
from backend.app.models.entities import Stage, StageStatusEnum

# Clave de administrator de las pruebas: NUNCA es la real (ésta vive en el
# entorno del servidor, nunca en el repositorio).
CLAVE_DE_PRUEBA = "clave-de-prueba-kuspide"

async def _seed_stage(session):
    stage = Stage(
        stage_number=99, name="Fecha 99: Prueba", slug="fecha-prueba",
        date=datetime.date(2026, 1, 1), status=StageStatusEnum.FINISHED,
        judge_pin="PIN-SECRETO-DE-PRUEBA",
        route_geojson={"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": {"type": "LineString",
             "coordinates": [[-71.5, -16.4, 2200, 0.0]]}}]},
    )
    session.add(stage)
    await session.commit()
    await session.refresh(stage)
    return stage


async def test_stages_no_expone_judge_pin(client, async_session):
    stage = await _seed_stage(async_session)
    res = await client.get("/api/v1/stages")
    assert res.status_code == 200
    assert "PIN-SECRETO-DE-PRUEBA" not in res.text
    assert "judge_pin" not in res.text


async def test_stage_detalle_no_expone_judge_pin(client, async_session):
    """La ficha de la fecha no lleva el PIN ni tan siquiera el nombre del campo.

    Se comprueban las DOS cosas: el valor del PIN (que es lo que de verdad
    importa: con él se mandan marcaciones falsas) y el LITERAL
    `"judge_pin"` (que delata que el campo sigue viajando en el sobre, aunque
    su valor venga vacío o recortado).
    """
    stage = await _seed_stage(async_session)
    res = await client.get(f"/api/v1/stages/{stage.slug}")
    assert res.status_code == 200
    assert "PIN-SECRETO-DE-PRUEBA" not in res.text
    assert "judge_pin" not in res.text


async def test_stage_summary_no_expone_judge_pin_ni_geometria(client, async_session):
    stage = await _seed_stage(async_session)
    res = await client.get(f"/api/v1/stages/{stage.slug}/summary")
    assert res.status_code == 200
    assert "PIN-SECRETO-DE-PRUEBA" not in res.text
    assert "judge_pin" not in res.text
    # La geometría pesada no viaja en el resumen: la página usa el SVG estatico.
    assert "route_geojson" not in res.text


async def test_stage_results_no_expone_judge_pin(client, async_session):
    """Los resultados tampoco: ni el valor del PIN ni el nombre del campo."""
    stage = await _seed_stage(async_session)
    res = await client.get(f"/api/v1/stages/{stage.slug}/results")
    assert res.status_code == 200
    assert "PIN-SECRETO-DE-PRUEBA" not in res.text
    assert "judge_pin" not in res.text


# ─────────────────────────────────────────────────────────────────────────────
# La clave de administrador falla CERRADO
#
# Antes la clave tenía un valor por DEFECTO en el código y en el bundle del
# navegador: cualquiera que abriera el DevTools podía leerla, aprobar pagos,
# pisar la base de datos con un Excel o abrir la transmisión en vivo.
#
# Ahora la clave vive SÓLO en el entorno del servidor. Si el servidor no la
# tiene, NINGÚN endpoint de administración responde 200.
# ─────────────────────────────────────────────────────────────────────────────


async def test_admin_sin_clave_responde_403(client, monkeypatch):
    """Sin cabecera `X-Admin-Key` la puerta está cerrada (403)."""
    monkeypatch.setattr(settings, "ADMIN_API_KEY", CLAVE_DE_PRUEBA)
    res = await client.get("/api/v1/admin/pending-payments")
    assert res.status_code == 403


async def test_admin_con_clave_invalida_responde_403(client, monkeypatch):
    """Una clave inventada es un 403: no vale, pero el servidor está bien."""
    monkeypatch.setattr(settings, "ADMIN_API_KEY", CLAVE_DE_PRUEBA)
    res = await client.get(
        "/api/v1/admin/pending-payments",
        headers={"X-Admin-Key": "clave-inventada"},
    )
    assert res.status_code == 403


async def test_admin_con_clave_correcta_responde_200(client, monkeypatch):
    """Con la clave buena, la consola de pagos responde 200."""
    monkeypatch.setattr(settings, "ADMIN_API_KEY", CLAVE_DE_PRUEBA)
    res = await client.get(
        "/api/v1/admin/pending-payments",
        headers={"X-Admin-Key": CLAVE_DE_PRUEBA},
    )
    assert res.status_code == 200


async def test_admin_sin_clave_configurada_responde_503(client, monkeypatch):
    """El servidor SIN clave no es un 403: es un 503 (fallo de configuración).

    La diferencia importa: el 403 dice "te equivocaste", el 503 dice "el
    servidor está mal configurado". Con el 503 nadie puede creer que la
    credencial del navegador vale.
    """
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "")
    res = await client.get("/api/v1/admin/pending-payments")
    assert res.status_code == 503
    assert "ADMIN_API_KEY" in res.json()["detail"]


async def test_admin_clave_con_acentos_responde_403(client, monkeypatch):
    """Una cabecera con tildes no puede tumbar el servidor (500).

    `hmac.compare_digest` sólo acepta texto ASCII: hay que comparar BYTES.
    Las cabeceras HTTP viajan en latin-1, así que la prueba manda los bytes.
    """
    monkeypatch.setattr(settings, "ADMIN_API_KEY", CLAVE_DE_PRUEBA)
    res = await client.get(
        "/api/v1/admin/pending-payments",
        headers={"X-Admin-Key": "clávé-ñ".encode("latin-1")},
    )
    assert res.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# CORS cerrado en producción
#
# El sitio se sirve desde Cloudflare Pages y la API desde Render: el navegador
# del visitante manda la cabecera `Origin`. Si el backend acepta cualquier
# origen, cualquiera puede leer la API desde su propia página. En producción
# sólo valen los orígenes de la lista.
# ─────────────────────────────────────────────────────────────────────────────


async def test_cors_no_acepta_pages_dev_arbitrario(client, monkeypatch):
    """Un `*.pages.dev` que NO está en la lista no recibe permiso de CORS."""
    from backend.app.core import config as config_module

    monkeypatch.setattr(config_module.settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(
        config_module.settings, "CORS_ORIGINS", ["https://copa-macrosur-web.pages.dev"]
    )
    res = await client.get(
        "/api/v1/public/live-status",
        headers={"Origin": "https://attacker.pages.dev"},
    )
    assert "access-control-allow-origin" not in {k.lower() for k in res.headers}


async def test_cors_en_produccion_no_acepta_localhost(client, monkeypatch):
    """En producción el regex de localhost está DESACTIVADO.

    Antes el regex de localhost estaba activo SIEMPRE, también en producción:
    eso deja abierta la API a cualquier página servida desde el portátil de
    cualquiera.
    """
    from backend.app.core import config as config_module

    monkeypatch.setattr(config_module.settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(config_module.settings, "CORS_ORIGINS", ["https://kuspideweb.com"])
    res = await client.get(
        "/api/v1/public/live-status",
        headers={"Origin": "http://localhost:4321"},
    )
    assert "access-control-allow-origin" not in {k.lower() for k in res.headers}


async def test_cors_en_produccion_acepta_un_origen_de_la_lista(client, monkeypatch):
    """El origen REAL sí recibe permiso: la lista no es un muro."""
    from backend.app.core import config as config_module

    monkeypatch.setattr(config_module.settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(config_module.settings, "CORS_ORIGINS", ["https://kuspideweb.com"])
    res = await client.get(
        "/api/v1/public/live-status",
        headers={"Origin": "https://kuspideweb.com"},
    )
    assert res.headers.get("access-control-allow-origin") == "https://kuspideweb.com"


async def test_cors_en_desarrollo_acepta_cualquier_puerto_de_localhost(client, monkeypatch):
    """En desarrollo vale cualquier puerto de localhost.

    Astro toma el siguiente puerto libre si el 4321 está ocupado: con una
    lista fija, el sitio "funciona" en el servidor (el SSR no lleva `Origin`)
    pero TODAS las islas de cliente fallan en silencio.
    """
    from backend.app.core import config as config_module

    monkeypatch.setattr(config_module.settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(config_module.settings, "CORS_ORIGINS", ["https://kuspideweb.com"])
    res = await client.get(
        "/api/v1/public/live-status",
        headers={"Origin": "http://localhost:4327"},
    )
    assert res.headers.get("access-control-allow-origin") == "http://localhost:4327"


async def test_cors_con_origen_comodin_no_abre_la_api():
    """Un `*` en la lista de orígenes NO abre la API (I-2).

    El error de operador más probable es exactamente este: "añado `*` para
    que no me dé error de CORS". Con `allow_origins=["*"]` y
    `allow_credentials=True`, Starlette_refleja el `Origin` del atacante con
    `Access-Control-Allow-Credentials: true` SIN pasar por la política.

    El middleware se construye aquí a propósito (con `*`) para que el test
    no dependa de lo que hubiera en el entorno al arrancar.
    """
    import httpx
    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    from backend.app.main import SettingsAwareCORSMiddleware

    async def eco(request):
        return JSONResponse({"ok": True})

    app = Starlette(
        routes=[Route("/", eco)],
        middleware=[
            Middleware(
                SettingsAwareCORSMiddleware,
                allow_origins=["*"],
                allow_credentials=True,
                allow_methods=["GET", "POST", "OPTIONS"],
                allow_headers=["Content-Type", "X-Admin-Key", "X-Judge-Pin"],
            )
        ],
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/", headers={"Origin": "https://attacker.pages.dev"})

    assert "access-control-allow-origin" not in {k.lower() for k in res.headers}


async def test_cors_con_origen_comodin_tampoco_en_la_app_real(client, monkeypatch):
    """La app real tampoco abre la API si el entorno trae un `*`."""
    from backend.app.core import config as config_module

    monkeypatch.setattr(config_module.settings, "CORS_ORIGINS", ["*"])
    res = await client.get(
        "/api/v1/public/live-status",
        headers={"Origin": "https://attacker.pages.dev"},
    )
    assert "access-control-allow-origin" not in {k.lower() for k in res.headers}


# ─────────────────────────────────────────────────────────────────────────────
# Límites de entrada
# ─────────────────────────────────────────────────────────────────────────────


def _feedback_de_prueba() -> dict:
    return {
        "stage_id": None,
        "type": "OTHER",
        "submitted_by_name": "Prueba",
        "contact_whatsapp_or_email": "a@b.pe",
        "message": "Mensaje de prueba",
    }


@pytest.fixture
def cuota_publica_limpia():
    """Vacía la cuota de las escrituras públicas antes de cada prueba.

    El limitador es GLOBAL en memoria (por IP y bucket): sin esta limpieza,
    la prueba que manda 11 reclamos deja a las siguientes sin cuota y el
    resultado dependería del orden de ejecución.
    """
    from backend.app.core.limits import rate_limiter_registry

    limitador = rate_limiter_registry.get("public_write")
    if limitador is not None:
        limitador.reset()
    yield


async def test_rate_limit_public_write(client, cuota_publica_limpia):
    """La 11.ª escritura pública en un minuto recibe 429 y `Retry-After`.

    El limitador es GLOBAL en memoria (por IP y bucket), así que el test
    vacía su bucket antes de su propio bucle: si no, el resultado dependería
    de los tests que se ejecutaron antes.
    """
    from backend.app.core.limits import rate_limiter_registry

    rate_limiter_registry["public_write"].reset()
    for _ in range(10):
        res = await client.post("/api/v1/public/feedback", json=_feedback_de_prueba())
        assert res.status_code == 200
    res = await client.post("/api/v1/public/feedback", json=_feedback_de_prueba())
    assert res.status_code == 429
    assert "retry-after" in res.headers


async def test_la_cuota_se_apaga_con_el_flag(client, monkeypatch, cuota_publica_limpia):
    """`RATE_LIMIT_ENABLED=False` apaga la CUOTA (y sólo la cuota).

    El interruptor existe para depurar: con él apagado, las escrituras
    públicas dejan de contar.
    """
    from backend.app.core.limits import rate_limiter_registry

    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
    rate_limiter_registry["public_write"].reset()

    for _ in range(11):
        res = await client.post("/api/v1/public/feedback", json=_feedback_de_prueba())
        assert res.status_code == 200, res.text


async def test_el_tope_del_cuerpo_sigue_vigente_sin_cuota(
    client, monkeypatch, cuota_publica_limpia
):
    """Apagar la cuota NO abre la puerta a un cuerpo gigante.

    La cuota por IP y el tope de tamaño del cuerpo son dos límites distintos:
    el tope protege la RAM del servidor (Render Free: 512 MB) y una petición
    enorme se leería ENTERA en memoria. Apagar el flag de la cuota no puede
    dejarlo desactivado.
    """
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
    monkeypatch.setattr(settings, "MAX_JSON_BYTES", 64)

    res = await client.post("/api/v1/public/feedback", json=_feedback_de_prueba())
    assert res.status_code == 413


def test_el_limitador_usa_la_tabla_de_reglas_que_le_pasan():
    """La tabla de reglas manda sobre lo que quedara registrado.

    Antes, `default_limiter_factory` devolvía SIEMPRE el limitador ya
    registrado e ignoraba la tabla que le pasaban: un middleware montado con
    otra tabla de reglas limitaba con los topes de la de por defecto.
    """
    from backend.app.core.limits import (
        RateRule,
        default_limiter_factory,
        rate_limiter_registry,
    )

    reglas = [RateRule(prefix="/api/v1/prueba", bucket="prueba", limit=3)]
    limitador = default_limiter_factory(reglas[0], reglas)
    assert limitador.limit == 3
    assert rate_limiter_registry["prueba"] is limitador

    # Otra tabla para el MISMO bucket: el limitador se rehace con el tope
    # nuevo (la tabla manda), no se devuelve el viejo.
    otras = [RateRule(prefix="/api/v1/prueba", bucket="prueba", limit=7)]
    limitador_nuevo = default_limiter_factory(otras[0], otras)
    assert limitador_nuevo.limit == 7
    assert rate_limiter_registry["prueba"] is limitador_nuevo

    # Y con la misma tabla, el limitador se REUTILIZA (no se pierde la
    # ventana ya abierta).
    assert default_limiter_factory(otras[0], otras) is limitador_nuevo


async def test_preregistro_nombre_demasiado_largo(client, cuota_publica_limpia):
    """Un nombre de 500 caracteres se rechaza con 422 (no se guarda nada)."""
    res = await client.post(
        "/api/v1/public/pre-register",
        json={
            "stage_id": 1,
            "dni": "12345678",
            "full_name": "X" * 500,
            "gender": "M",
            "category_id": 1,
            "team_name_or_libre": "LIBRE",
        },
    )
    assert res.status_code == 422


async def test_json_supera_el_tope_responde_413(client, monkeypatch, cuota_publica_limpia):
    """Un cuerpo JSON por encima del tope se rechaza ANTES de leerlo."""
    monkeypatch.setattr(settings, "MAX_JSON_BYTES", 64)
    res = await client.post("/api/v1/public/feedback", json=_feedback_de_prueba())
    assert res.status_code == 413


async def test_json_dentro_del_tope_se_procesa(client, cuota_publica_limpia):
    """El control: con el tope normal, el mismo cuerpo se guarda (200)."""
    res = await client.post("/api/v1/public/feedback", json=_feedback_de_prueba())
    assert res.status_code == 200


async def test_upload_excel_supera_el_tope(client, monkeypatch):
    """Un .xlsx por encima del tope se rechaza con 413 (sin tragárselo).

    El tope se baja a 1 KB en vez de mandar 26 MB por el cable: lo que se
    comprueba es que EXISTE el tope, no que el servidor aguante 26 MB.

    El 413 lo da el MIDDLEWARE (por `Content-Length`), que corta antes de
    que el cuerpo se lea; el router repite el corte sobre el archivo ya
    leído, que es el definitivo.
    """
    monkeypatch.setattr(settings, "ADMIN_API_KEY", CLAVE_DE_PRUEBA)
    monkeypatch.setattr(settings, "MAX_UPLOAD_BYTES", 1024)
    res = await client.post(
        "/api/v1/stages/1/import-excel",
        headers={"X-Admin-Key": CLAVE_DE_PRUEBA},
        files={
            "file": (
                "grande.xlsx",
                b"x" * 4096,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert res.status_code == 413
    assert "demasiado grande" in res.json()["detail"]


async def test_upload_grande_se_rechaza_antes_de_leer_el_cuerpo(client, monkeypatch):
    """El tope se aplica ANTES de recibir el cuerpo, y sin credencial (I-1).

    FastAPI parsea el multipart (`await request.form()`) ANTES de resolver las
    dependencias: el archivo entero se escribe en un temporal de disco antes
    del 403. Un atacante sin clave podía llenar el disco del servidor con una
    sola subida.

    Por eso este test NO manda la clave: si la respuesta es 413 y no 403,
    el corte lo hizo el middleware (antes de leer el cuerpo), no el router.
    """
    monkeypatch.setattr(settings, "MAX_UPLOAD_BYTES", 1024)
    res = await client.post(
        "/api/v1/stages/1/import-excel",
        files={
            "file": (
                "grande.xlsx",
                b"x" * 8192,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert res.status_code == 413
    assert "demasiado grande" in res.json()["detail"]


async def test_upload_grande_de_gpx_tambien_se_rechaza(client, monkeypatch):
    """La subida de GPX tiene el mismo corte que la de Excel."""
    monkeypatch.setattr(settings, "MAX_UPLOAD_BYTES", 1024)
    res = await client.post(
        "/api/v1/stages/1/upload-gpx",
        files={"file": ("ruta.gpx", b"x" * 8192, "application/gpx+xml")},
    )
    assert res.status_code == 413


async def test_413_lleva_cabeceras_cors(client, monkeypatch, cuota_publica_limpia):
    """El 413 también lleva su cabecera de CORS (como el 429).

    Sin ella, el navegador enseña el 413 como un "fallo de red" en vez de
    "la petición es demasiado grande".
    """
    monkeypatch.setattr(settings, "MAX_JSON_BYTES", 64)
    res = await client.post(
        "/api/v1/public/feedback",
        json=_feedback_de_prueba(),
        headers={"Origin": "http://localhost:4321"},
    )
    assert res.status_code == 413
    assert res.headers.get("access-control-allow-origin") == "http://localhost:4321"


async def test_json_chunked_excede_el_tope_responde_413(client, monkeypatch, cuota_publica_limpia):
    """Sin `Content-Length` (chunked) el tope se mide sobre el cuerpo real.

    Con `Transfer-Encoding: chunked` no hay `Content-Length` que comparar:
    si el middleware no mide el cuerpo, el tope no existe para ese cliente
    (y FastAPI se lo lee entero en memoria).
    """
    import json

    monkeypatch.setattr(settings, "MAX_JSON_BYTES", 64)
    cuerpo = json.dumps(_feedback_de_prueba()).encode() + b" " * 512

    async def trozos():
        yield cuerpo

    res = await client.post(
        "/api/v1/public/feedback",
        content=trozos(),
        headers={"Content-Type": "application/json"},
    )
    assert res.status_code == 413


async def test_json_chunked_dentro_del_tope_llega_a_la_ruta(client, cuota_publica_limpia):
    """El control: un cuerpo chunked que SÍ cabe llega intacto a la ruta."""
    import json

    async def trozos():
        yield json.dumps(_feedback_de_prueba()).encode()

    res = await client.post(
        "/api/v1/public/feedback",
        content=trozos(),
        headers={"Content-Type": "application/json"},
    )
    assert res.status_code == 200


def test_la_tabla_de_reglas_no_miente():
    """Las reglas de un mismo bucket declaran el MISMO límite (M-3).

    El limitador es uno por bucket: si dos reglas del mismo bucket
    declararan límites distintos, el effective sería el más apretado y la
    tabla estaría mintiendo sobre lo que hace el código.
    """
    from backend.app.core.limits import RATE_LIMIT_RULES, rate_limiter_registry

    for bucket in {r.bucket for r in RATE_LIMIT_RULES}:
        declarados = {r.limit for r in RATE_LIMIT_RULES if r.bucket == bucket}
        assert len(declarados) == 1, f"el bucket {bucket} declara límites distintos: {declarados}"
        assert rate_limiter_registry[bucket].limit == declarados.pop()


async def test_upload_excel_dentro_del_tope_no_se_rechaza(client, monkeypatch):
    """El control: un archivo pequeño LLEGA al importador (no es un 413)."""
    monkeypatch.setattr(settings, "ADMIN_API_KEY", CLAVE_DE_PRUEBA)
    monkeypatch.setattr(settings, "MAX_UPLOAD_BYTES", 1024 * 1024)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "LISTA"
    ws.append(["DORSAL", "NOMBRE", "TEAM", "ELITE", "T. TOTAL", "PUNTOS", "PUESTO"])
    ws.append([15, "JUAN PEREZ", "LIBRE", "ELITE", None, None, None])
    ws.append([15, "PEDRO GOMEZ", "LIBRE", "ELITE", None, None, None])  # dorsal duplicado
    buf = io.BytesIO()
    wb.save(buf)

    res = await client.post(
        "/api/v1/stages/1/import-excel",
        headers={"X-Admin-Key": CLAVE_DE_PRUEBA},
        files={
            "file": (
                "lista.xlsx",
                buf.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    # Llega al importador, que lo rechaza por el dorsal duplicado (422),
    # no por el tamaño.
    assert res.status_code == 422
