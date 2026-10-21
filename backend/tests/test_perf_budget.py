"""
Presupuesto de rendimiento: caché, agregado de portada, compresión y N+1.

Estas pruebas fijan cuatro cosas que se midieron contra la producción real
(Render en Oregon + Neon + Cloudflare Pages):

  · **Tarea 5** — la caché en memoria se invalida cuando algo cambia de
    verdad: con un TTL de 120 s sin invalidar, el público veía datos viejos
    hasta dos minutos después de una marcación del juez.
  · **Tarea 6** — la portada se lee con UNA sola llamada a la API (antes
    eran siete: siete esperas de red en el SSR de Cloudflare).
  · **Tarea 7** — la API comprime sus respuestas grandes (GZip) y la
    transmisión en vivo NO se comprime (el SSE se.secuencia en el tiempo).
  · **Tarea 8** — los endpoints de lectura NO hacen un N+1: una consulta
    por cada fila de la tabla. Medido contra producción, `/api/v1/stages`
    tardaba 983 ms y `/stages/{slug}/summary` 701 ms, y no era la red: era
    SQL (una consulta extra por cada corredor, por cada segmento de
    Strava y por cada fila de la clasificación).

La caché en memoria es GLOBAL al proceso, así que el fixture `client` la
vacía antes de cada prueba: si no, una clasificación cacheada por un test
se vería en el siguiente sin tocar la base de datos.
"""
import re
import uuid
from datetime import date as date_cls, timedelta
from typing import Any, Dict

import pytest_asyncio
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.middleware.gzip import GZipMiddleware

from backend.app.core.cache import cache
from backend.app.core.config import settings
from backend.app.models.entities import (
    Category,
    ChampionshipStanding,
    Checkpoint,
    PaymentStatusEnum,
    RaceStatusEnum,
    Rider,
    Stage,
    StageEntry,
    StageStatusEnum,
    StravaEffort,
    StravaSegment,
    Team,
)

# PIN de juez de la fecha sembrada. No es una credencial real: es la de la
# fecha de prueba, y sirve para exercised el camino del juez.
PIN_JUEZ = "1234"

# Clave de administrador de las pruebas: NUNCA es la real (ésta vive en el
# entorno del servidor, nunca en el repositorio). Se fija con `monkeypatch`
# para que la suite pase igual en un clon limpio, sin `.env`.
CLAVE_DE_PRUEBA = "clave-de-prueba-kuspide"

# Prefijos que ``invalidate_public`` tiene que vaciar: todo lo que el
# público puede leer por la API.
PREFIJOS_PUBLICOS = ("public:", "stages:", "stage:summary:")


# --------------------------------------------------------------------------
# Helpers de siembra
# --------------------------------------------------------------------------


async def _sembrar_campeonato(
    session: AsyncSession, *, corredores: int = 40
) -> Stage:
    """Siembra una fecha disputada con corredores, puntos y tiempos.

    El tamaño importa: un payload de 200 bytes no lo comprime el GZip y un
    podio vacío no prueba que el agregado traiga datos.
    """
    categorias = {}
    for codigo, nombre in (("ELI", "Elite"), ("TOV", "Turismo Open")):
        categoria = Category(short_code=codigo, name=nombre)
        session.add(categoria)
        await session.flush()
        categorias[codigo] = categoria

    equipos = []
    for nombre in ("TEAM ALFA", "TEAM BETA", "TEAM GAMMA"):
        equipo = Team(name=nombre, slug=nombre.lower().replace(" ", "-"))
        session.add(equipo)
        await session.flush()
        equipos.append(equipo)

    stage = Stage(
        stage_number=1,
        name="Fecha 1: La Joya Extreme",
        title="La Joya Extreme",
        short_name="La Joya",
        slug="la-joya-extreme",
        date=date_cls(2026, 5, 17),
        status=StageStatusEnum.FINISHED,
        start_location="Vía de Evitamiento, La Joya",
        start_time="08:00 AM",
        distance_km=40.85,
        elevation_gain_m=384,
        laps=1,
        judge_pin=PIN_JUEZ,
        # La geometría pesa ~58 KB y NINGUNA página la consume: el agregado
        # de la portada no debe arrastrarla.
        route_geojson={
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [
                            [-71.0, -16.0, 1000.0, 0.0],
                            [-71.1, -16.0, 1100.0, 5.0],
                        ],
                    },
                }
            ],
        },
    )
    session.add(stage)
    await session.flush()

    rango_por_categoria: dict[int, int] = {}
    for indice in range(corredores):
        codigo = "ELI" if indice % 2 == 0 else "TOV"
        categoria = categorias[codigo]
        equipo = equipos[indice % len(equipos)]
        rider = Rider(
            dni=f"10000000{indice:02d}",
            full_name=f"CICLISTA {indice:03d}",
            slug=f"ciclista-{indice:03d}",
            team_id=equipo.id,
        )
        session.add(rider)
        await session.flush()

        rango_por_categoria[categoria.id] = rango_por_categoria.get(categoria.id, 0) + 1
        rango = rango_por_categoria[categoria.id]
        session.add(
            StageEntry(
                stage_id=stage.id,
                rider_id=rider.id,
                category_id=categoria.id,
                team_id=equipo.id,
                bib_number=indice + 1,
                race_status=RaceStatusEnum.FINISHED,
                start_time_ms=1_700_000_000_000,
                finish_elapsed_ms=3_600_000 + indice * 30_000,
                category_rank=rango,
                overall_rank=indice + 1,
                points_earned=max(1, 11 - rango),
            )
        )

    await session.commit()
    await session.refresh(stage)
    return stage


def _claves_publicas() -> list[str]:
    """Las claves vivas de la caché que el público puede leer."""
    return [key for key in cache.keys() if key.startswith(PREFIJOS_PUBLICOS)]


async def _sembrar_titulos_de_montana(
    session: AsyncSession, stage: Stage, *, prefijo: str = ""
) -> None:
    """Segmentos de Strava con intentos de varón y mujer.

    De ahí salen los cuatro títulos de montaña de la fecha: el KOM y el QOM
    comparten la subida más empinada; los Kamikaze, la bajada más pronunciada.
    """
    for seg_id, nombre, distancia, pendiente, intentos in [
        (
            "1",
            "SUBIDA EMPINADA",
            1000.0,
            9.0,
            [("ESCALADOR M", 300, "M"), ("ESCALADORA F", 360, "F")],
        ),
        (
            "2",
            "BAJADA EMPINADA",
            1000.0,
            -8.0,
            [("KAMIKAZE M", 200, "M"), ("KAMIKAZE F", 260, "F")],
        ),
    ]:
        segment = StravaSegment(
            stage_id=stage.id,
            strava_segment_id=f"{seg_id}{prefijo}",
            name=nombre,
            distance_m=distancia,
            average_grade=pendiente,
        )
        session.add(segment)
        await session.flush()
        for atleta, segundos, genero in intentos:
            session.add(
                StravaEffort(
                    segment_id=segment.id,
                    athlete_name_raw=f"{atleta}{prefijo}",
                    elapsed_time_sec=segundos,
                    measured_on=stage.date.isoformat(),
                    athlete_gender=genero,
                    is_kom_qom=0,
                )
            )
    await session.commit()


# --------------------------------------------------------------------------
# Tarea 5 — la caché se invalida cuando algo cambia de verdad
# --------------------------------------------------------------------------


def test_invalidate_public_borra_las_claves_de_lectura():
    """`invalidate_public` vacía las lecturas públicas y NO toca el resto."""
    cache.set("public:standings:PRO", {"rows": []}, ttl_seconds=60)
    cache.set("public:live_status", {"state": "live"}, ttl_seconds=60)
    cache.set("stages:list", [], ttl_seconds=60)
    cache.set("otra:cosa", 1, ttl_seconds=60)
    cache.invalidate_public()
    assert cache.get("public:standings:PRO") is None
    assert cache.get("public:live_status") is None
    assert cache.get("stages:list") is None
    assert cache.get("otra:cosa") == 1


def test_delete_prefix_solo_borra_lo_que_empieza_por_ese_prefijo():
    """El borrado por prefijo es surgical: lo demás sigue en su sitio."""
    cache.set("public:uno", 1, ttl_seconds=60)
    cache.set("public:dos", 2, ttl_seconds=60)
    cache.set("privado:tres", 3, ttl_seconds=60)

    cache.delete_prefix("public:")

    assert cache.get("public:uno") is None
    assert cache.get("public:dos") is None
    assert cache.get("privado:tres") == 3


def test_la_cache_responde_en_los_tests():
    """La caché FUNCIONA bajo pytest (antes estaba desactivada por un bypass).

    Sin esto la invalidación no se puede probar: `get` devolvía siempre
    `None` y `set` no guardaba nada.
    """
    cache.set("prueba:cache", {"ok": True}, ttl_seconds=60)
    assert cache.get("prueba:cache") == {"ok": True}
    cache.clear()
    assert cache.get("prueba:cache") is None


async def test_una_marcacion_del_juez_invalida_la_cache_publica(
    client, async_session: AsyncSession
):
    """Una marcación del juez invalida lo que el público tiene cacheado.

    Si no se invalidara, la clasificación que ve el público seguiría siendo
    la de antes del cruce por meta hasta que expirara el TTL (120 s).
    """
    stage = await _sembrar_campeonato(async_session)

    # El público lee: la clasificación y el calendario entran en la caché.
    await client.get("/api/v1/public/standings?scope=PRO")
    await client.get("/api/v1/stages")
    assert _claves_publicas(), "la caché pública debería estar llena"

    # El juez marca un paso por el control intermedio.
    checkpoint = Checkpoint(
        stage_id=stage.id,
        name="Control Intermedio Cumbre",
        order_index=50,
        distance_from_start_km=20.425,
        is_finish_line=False,
    )
    async_session.add(checkpoint)
    await async_session.commit()
    await async_session.refresh(checkpoint)

    entrada = (
        await async_session.exec(
            select(StageEntry)
            .where(StageEntry.stage_id == stage.id)
            .order_by(StageEntry.bib_number)
        )
    ).first()
    res = await client.post(
        "/api/v1/timing/events",
        json={
            "id": str(uuid.uuid4()),
            "stage_entry_id": entrada.id,
            "checkpoint_id": checkpoint.id,
            "recorded_at_ms": 1_700_000_100_000,
        },
        headers={"X-Judge-Pin": PIN_JUEZ},
    )
    assert res.status_code == 200, res.text

    assert _claves_publicas() == [], "la marcación del juez no invalidó la caché"


async def test_una_pre_inscripcion_invalida_la_cache_publica(
    client, async_session: AsyncSession
):
    """Una pre-inscripción invalida lo que el público tiene cacheado.

    La inscripción cambia el número de inscritos que muestra la ficha de la
    fecha (y las clasificaciones): sin esta invalidación, el contador
    quedaría caducado hasta que expirara el TTL (120 s).
    """
    stage = await _sembrar_campeonato(async_session)
    categoria = (await async_session.exec(select(Category))).first()

    # El público lee: la clasificación y el calendario entran en la caché.
    await client.get("/api/v1/public/standings?scope=PRO")
    await client.get("/api/v1/stages")
    assert _claves_publicas(), "la caché pública debería estar llena"

    res = await client.post(
        "/api/v1/public/pre-register",
        json={
            "stage_id": stage.id,
            "dni": "87654321",
            "full_name": "PRE INSCRITO DE PRUEBA",
            "gender": "M",
            "category_id": categoria.id,
            "team_name_or_libre": "LIBRE",
        },
    )
    assert res.status_code == 200, res.text

    assert _claves_publicas() == [], "la pre-inscripción no invalidó la caché"


async def test_abrir_la_transmision_invalida_la_cache_publica(
    client, async_session: AsyncSession, monkeypatch
):
    """Abrir o cerrar la transmisión invalida la caché del público.

    El estado de la transmisión es lo que la portada anuncia: si se
    cacheara, el enlace "en vivo" seguiría apareciendo (o desaparecería)
    hasta dos minutos después de la orden del organizador.

    La clave de administrador se fija en la prueba: en un clon limpio (sin
    `.env`) la del entorno no existe y el endpoint respondería 503 en vez de
    dar su mensaje.
    """
    monkeypatch.setattr(settings, "ADMIN_API_KEY", CLAVE_DE_PRUEBA)
    stage = await _sembrar_campeonato(async_session)

    await client.get("/api/v1/public/live-status")
    assert _claves_publicas(), "la caché pública debería estar llena"

    res = await client.post(
        f"/api/v1/stages/{stage.id}/live",
        json={"active": True},
        headers={"X-Admin-Key": CLAVE_DE_PRUEBA},
    )
    assert res.status_code == 200, res.text

    assert _claves_publicas() == [], "abrir la transmisión no invalidó la caché"


# --------------------------------------------------------------------------
# Tarea 6 — la portada se lee con UNA sola llamada
# --------------------------------------------------------------------------


async def test_home_aggregate_una_sola_llamada(client, async_session: AsyncSession):
    """`GET /public/home` devuelve las siete claves de la portada.

    Antes la portada hacía siete peticiones (dos clasificaciones, la de
    equipos, el calendario, el estado en vivo, los títulos de montaña y el
    premio CLARO) desde el SSR de Cloudflare, que no cachea el HTML.
    """
    await _sembrar_campeonato(async_session)

    res = await client.get("/api/v1/public/home")
    assert res.status_code == 200, res.text
    data = res.json()
    for key in ("stages", "live_status", "pro_podium", "normal_podium",
                "teams_podium", "remontada", "mountain_titles"):
        assert key in data, f"falta la clave {key}"
    assert "judge_pin" not in res.text
    assert "route_geojson" not in res.text
    assert len(data["pro_podium"]) <= 3


async def test_home_no_trae_la_credencial_del_juez_ni_la_geometria(
    client, async_session: AsyncSession
):
    """Ni el PIN del juez ni la traza de la ruta viajan en el agregado.

    El PIN es una credencial (con él se mandan marcaciones falsas) y la
    geometría pesa ~58 KB por fecha: ninguna de las dos cosas tiene nada que
    ver con la portada (specs/00 §1.4).
    """
    await _sembrar_campeonato(async_session)

    res = await client.get("/api/v1/public/home")
    assert res.status_code == 200
    assert PIN_JUEZ not in res.text
    assert "judge_pin" not in res.text
    assert "route_geojson" not in res.text
    assert "LineString" not in res.text


async def test_home_trae_los_tres_podios_con_su_forma(
    client, async_session: AsyncSession
):
    """Los tres podios traen tres filas cada uno, con su forma exacta."""
    await _sembrar_campeonato(async_session, corredores=40)

    data = (await client.get("/api/v1/public/home")).json()

    assert len(data["pro_podium"]) == 3
    assert len(data["normal_podium"]) == 3
    assert len(data["teams_podium"]) == 3
    for fila in data["pro_podium"] + data["normal_podium"]:
        assert fila["rider_name"]
        assert isinstance(fila["total_points"], int)
    for fila in data["teams_podium"]:
        assert fila["team_name"]
        assert isinstance(fila["total_points"], int)


async def test_home_trae_los_titulos_de_montana_de_la_primera_fecha(
    client, async_session: AsyncSession
):
    """Los títulos de montaña son los de la PRIMERA fecha disputada."""
    stage = await _sembrar_campeonato(async_session)
    await _sembrar_titulos_de_montana(async_session, stage, prefijo=" F1")

    stage2 = Stage(
        stage_number=2,
        name="Fecha 2: Z Xtreme",
        title="Z Xtreme",
        short_name="Z Xtreme",
        slug="z-xtreme-2026",
        date=date_cls(2026, 6, 21),
        status=StageStatusEnum.FINISHED,
        distance_km=11.83,
        elevation_gain_m=280,
        laps=3,
    )
    async_session.add(stage2)
    await async_session.commit()
    await async_session.refresh(stage2)
    await _sembrar_titulos_de_montana(async_session, stage2, prefijo=" F2")

    data = (await client.get("/api/v1/public/home")).json()
    titulos = data["mountain_titles"]

    assert titulos["kom"]["athlete_name"] == "ESCALADOR M F1"
    assert titulos["qom"]["athlete_name"] == "ESCALADORA F F1"
    assert titulos["kamikaze_male"]["athlete_name"] == "KAMIKAZE M F1"
    assert titulos["kamikaze_female"]["athlete_name"] == "KAMIKAZE F F1"


async def test_home_sin_fechas_disputadas_no_inventa_podios(
    client, async_session: AsyncSession
):
    """Sin fechas disputadas los podios van vacíos: no se inventan datos."""
    stage = Stage(
        stage_number=1,
        name="Fecha 1: La Joya Extreme",
        slug="la-joya-extreme",
        date=date_cls(2026, 5, 17),
        status=StageStatusEnum.UPCOMING,
    )
    async_session.add(stage)
    await async_session.commit()

    res = await client.get("/api/v1/public/home")
    assert res.status_code == 200
    data = res.json()
    assert data["pro_podium"] == []
    assert data["normal_podium"] == []
    assert data["teams_podium"] == []
    assert data["mountain_titles"] == {
        "kom": None,
        "qom": None,
        "kamikaze_male": None,
        "kamikaze_female": None,
    }


async def test_home_se_cachea_y_se_invalida_al_mutar(
    client, async_session: AsyncSession
):
    """El agregado se cachea 60 s y se invalida cuando algo cambia de verdad."""
    stage = await _sembrar_campeonato(async_session)

    await client.get("/api/v1/public/home")
    assert cache.get("public:home") is not None, "el agregado no se cacheó"

    checkpoint = Checkpoint(
        stage_id=stage.id,
        name="Control Intermedio Cumbre",
        order_index=50,
        distance_from_start_km=20.425,
        is_finish_line=False,
    )
    async_session.add(checkpoint)
    await async_session.commit()
    await async_session.refresh(checkpoint)

    entrada = (
        await async_session.exec(
            select(StageEntry)
            .where(StageEntry.stage_id == stage.id)
            .order_by(StageEntry.bib_number)
        )
    ).first()
    res = await client.post(
        "/api/v1/timing/events",
        json={
            "id": str(uuid.uuid4()),
            "stage_entry_id": entrada.id,
            "checkpoint_id": checkpoint.id,
            "recorded_at_ms": 1_700_000_100_000,
        },
        headers={"X-Judge-Pin": PIN_JUEZ},
    )
    assert res.status_code == 200, res.text

    assert cache.get("public:home") is None, "la mutación no invalidó el agregado"


async def test_el_live_status_del_agregado_no_se_congela(
    client, async_session: AsyncSession
):
    """El `live_status` de la portada va con SU propio TTL (15 s).

    El agregado de la portada dura 60 s: si el estado de la transmisión
    quedara congelado dentro de él, el enlace "en vivo" aparecería (o
    desaparecería) con hasta un minuto de retraso. Por eso la clave
    `public:home` NO lleva el `live_status` dentro: se resuelve aparte, bajo
    su propia clave `public:live_status`, con el TTL del endpoint
    `/public/live-status`.
    """
    await _sembrar_campeonato(async_session)

    res = await client.get("/api/v1/public/home")
    assert res.status_code == 200, res.text

    agregado = cache.get("public:home")
    assert agregado is not None, "el agregado no se cacheó"
    assert "live_status" not in agregado, (
        "el live_status no puede quedar congelado dentro del agregado de 60 s"
    )
    assert cache.ttl_restante("public:home") is not None

    restante = cache.ttl_restante("public:live_status")
    assert restante is not None, "el live_status no se cacheó con su propia clave"
    assert restante <= 15, (
        f"el live_status se cacheó con {restante:.1f} s: su TTL es de 15 s"
    )

    # Los dos leen el MISMO valor: el agregado y el endpoint no pueden
    # discrepar sobre si hay carrera.
    directo = (await client.get("/api/v1/public/live-status")).json()
    assert res.json()["live_status"] == directo


# --------------------------------------------------------------------------
# Tarea 7 — la API comprime sus respuestas grandes
# --------------------------------------------------------------------------


async def test_json_comprimido(client, async_session: AsyncSession):
    """Las respuestas grandes de la API van comprimidas.

    El resumen de una fecha pesaba 64 KB sin comprimir: por el cable entre
    Render y el navegador iban enteros. Con GZip bajan a ~9 KB.
    """
    await _sembrar_campeonato(async_session, corredores=40)

    sin_comprimir = await client.get(
        "/api/v1/public/standings?scope=PRO",
        headers={"Accept-Encoding": "identity"},
    )
    assert sin_comprimir.status_code == 200
    assert len(sin_comprimir.content) > 1000, (
        "el payload de prueba no pasa el umbral: la prueba no probaría nada"
    )

    res = await client.get(
        "/api/v1/public/standings?scope=PRO",
        headers={"Accept-Encoding": "gzip"},
    )
    assert res.status_code == 200
    assert res.headers.get("content-encoding") == "gzip"


async def test_las_respuestas_pequenas_no_se_comprimen(client):
    """`/health` es diminuto: comprimirlo sólo gastaría CPU."""
    res = await client.get("/health", headers={"Accept-Encoding": "gzip"})
    assert res.status_code == 200
    assert res.headers.get("content-encoding") is None


async def test_el_sse_no_se_comprime():
    """La transmisión en vivo NO va comprimida.

    Los eventos del cronómetro son pequeños y seguidos: comprimidos, zlib
    agruparía los eventos y el panel del juez los vería a ráfagas en vez de
    en vivo. Starlette excluye `text/event-stream` por defecto; este test lo
    fija para que un cambio de versión no lo rompa en silencio.

    No se puede pedir el canal por el cliente de pruebas: el generador SSE
    nunca termina, así que la petición se quedaría colgada.
    """
    async def app_de_prueba(scope, receive, send):
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"text/event-stream; charset=utf-8")],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": b"event: timing-update\ndata: {}\n\n",
                "more_body": False,
            }
        )

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/stages/1/stream",
        "query_string": b"",
        "headers": [(b"accept-encoding", b"gzip")],
    }
    enviados: list[dict] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        enviados.append(message)

    middleware = GZipMiddleware(app_de_prueba, minimum_size=1000)
    await middleware(scope, receive, send)

    cabeceras = {k.decode(): v.decode() for k, v in enviados[0]["headers"]}
    assert "content-encoding" not in cabeceras
    assert enviados[1]["body"] == b"event: timing-update\ndata: {}\n\n"


# --------------------------------------------------------------------------
# Tarea 8 — cero N+1 en los endpoints de lectura
# --------------------------------------------------------------------------
#
# Un N+1 es UNA consulta por cada fila de la tabla: con 40 corredores el
# endpoint hace 40 consultas de más y la latencia se multiplica. El
# contador engancha el evento `before_cursor_execute` del engine de pruebas
# y cuenta las sentencias SQL que ejecuta la petición.
#
# El límite es "un número pequeño" (8): con seis filas ya se distingue un
# N+1 de una consulta con JOIN, y no es frágil si mañana se añade una
# consulta a un endpoint.


@pytest_asyncio.fixture
async def query_counter(async_session):
    """Contador de sentencias SQL de la petición que se mida.

    `{"n": 0}` lleva el número de consultas; `{"sql": [...]}` las sentencias
    literales, para poder decir QUÉ se repite cuando el test falla.

    El enganche es al motor de la sesión de pruebas (el `sync_engine` de
    `test_engine`): se toma del propio bind de la sesión y no de un
    `import`, para no depender de que el módulo de `conftest` se haya
    importado una sola vez.
    """
    from sqlalchemy import event

    counter: Dict[str, Any] = {"n": 0, "sql": []}

    def _before(conn, cursor, statement, parameters, context, executemany):
        counter["n"] += 1
        counter["sql"].append(statement)

    motor = async_session.get_bind()
    event.listen(motor, "before_cursor_execute", _before)
    try:
        yield counter
    finally:
        event.remove(motor, "before_cursor_execute", _before)


def _reiniciar_contador(counter: Dict[str, Any]) -> None:
    """Olvida lo que se ejecutó durante la siembra."""
    counter["n"] = 0
    counter["sql"] = []


def _consultas_sobre(counter: Dict[str, Any], tabla: str) -> int:
    """Cuántas consultas han CARGADO una tabla concreta.

    Cuenta las consultas que la toman como tabla principal (`FROM tabla`) y
    no las que sólo la unen con un `JOIN`: un `JOIN strava_segments` no
    carga los segmentos, los filtra, y contarlo como una carga de segmentos
    haría creer que hay una consulta de más (o de menos) de la que hay.
    """
    patron = re.compile(rf"\bfrom\s+\"?{re.escape(tabla)}\"?\b", re.IGNORECASE)
    return len([sql for sql in counter["sql"] if patron.search(sql)])


async def _sembrar_campeonato_para_n_plus_1(
    session: AsyncSession,
    *,
    fechas: int = 6,
    corredores: int = 20,
    categorias: int = 6,
    equipos: int = 3,
    pago: PaymentStatusEnum = PaymentStatusEnum.PAID,
) -> Dict[str, Any]:
    """Un campeonato con las filas suficientes para que un N+1 se vea.

    Cada fecha tiene sus inscritos, sus tiempos y sus puestos; cada corredor
    tiene su clasificación acumulada en las categorías en las que corrió
    (la clave de `championship_standings` es corredor + categoría).
    """
    cats = []
    for i in range(categorias):
        cat = Category(name=f"CATEGORIA {i}", short_code=f"C{i:02d}")
        session.add(cat)
        await session.flush()
        cats.append(cat)

    teams = []
    for i in range(equipos):
        team = Team(name=f"TEAM {i}", slug=f"team-{i}")
        session.add(team)
        await session.flush()
        teams.append(team)

    stages = []
    for f in range(fechas):
        stage = Stage(
            stage_number=f + 1,
            name=f"Fecha {f + 1}",
            title=f"Fecha {f + 1}",
            slug=f"fecha-{f + 1}",
            date=date_cls(2026, 5, 17) + timedelta(days=f),
            status=StageStatusEnum.FINISHED,
            distance_km=40.0,
            elevation_gain_m=300,
            laps=1,
        )
        session.add(stage)
        await session.flush()
        stages.append(stage)

    riders = []
    for i in range(corredores):
        rider = Rider(
            dni=f"9{i:07d}",
            full_name=f"CICLISTA {i:03d}",
            slug=f"ciclista-{i:03d}",
            team_id=teams[i % len(teams)].id,
        )
        session.add(rider)
        await session.flush()
        riders.append(rider)

    # Inscripciones: cada corredor corre en cada fecha (en una categoría que
    # rota). El dorsal es único dentro de la fecha.
    for f, stage in enumerate(stages):
        puesto: Dict[int, int] = {}
        for i, rider in enumerate(riders):
            cat = cats[(i + f) % len(cats)]
            puesto[cat.id] = puesto.get(cat.id, 0) + 1
            session.add(
                StageEntry(
                    stage_id=stage.id,
                    rider_id=rider.id,
                    category_id=cat.id,
                    team_id=rider.team_id,
                    bib_number=i + 1,
                    payment_status=pago,
                    race_status=RaceStatusEnum.FINISHED,
                    start_time_ms=1_700_000_000_000,
                    finish_elapsed_ms=3_600_000 + i * 30_000,
                    category_rank=puesto[cat.id],
                    overall_rank=i + 1,
                    points_earned=max(1, 11 - puesto[cat.id]),
                )
            )

    # Clasificación acumulada: un corredor, una fila por categoría.
    for rider in riders:
        for cat in cats:
            session.add(
                ChampionshipStanding(
                    rider_id=rider.id,
                    category_id=cat.id,
                    total_points=10,
                    first_places_count=1,
                    last_stage_rank=1,
                    total_elapsed_ms=3_600_000,
                    stages_completed=1,
                    current_rank=1,
                    rank_delta=0,
                )
            )

    await session.commit()
    return {
        "categorias": cats,
        "equipos": teams,
        "fechas": stages,
        "corredores": riders,
    }


async def _sembrar_segmentos_de_strava(
    session: AsyncSession, stage: Stage, *, segmentos: int = 6
) -> None:
    """Segmentos de Strava de la fecha, cada uno con sus intentos.

    Es el caso que más duele: la ficha de una fecha tenía 25 segmentos y
    hacía una consulta por cada uno.
    """
    for s in range(segmentos):
        segment = StravaSegment(
            stage_id=stage.id,
            strava_segment_id=f"{stage.id}-{s}",
            name=f"TRAMO {s}",
            distance_m=1000.0 + s * 10,
            average_grade=5.0 if s % 2 == 0 else -4.0,
        )
        session.add(segment)
        await session.flush()
        for e in range(3):
            session.add(
                StravaEffort(
                    segment_id=segment.id,
                    athlete_name_raw=f"ATLETA {e}",
                    elapsed_time_sec=300 + e * 30,
                    measured_on=stage.date.isoformat(),
                    athlete_gender="M" if e % 2 == 0 else "F",
                    is_kom_qom=False,
                )
            )
    await session.commit()


async def test_perfil_corredor_no_hace_n_plus_1(
    client, async_session: AsyncSession, query_counter
):
    """El perfil de un corredor no hace una consulta por cada fila.

    Antes: por cada fila de la clasificación acumulada del corredor se
    pedía su categoría con un `SELECT` aparte (y el `refresh` del corredor
    cargaba equipo y clasificaciones por separado).
    """
    datos = await _sembrar_campeonato_para_n_plus_1(
        async_session, fechas=6, corredores=20, categorias=6, equipos=3
    )
    corredor = datos["corredores"][0]

    _reiniciar_contador(query_counter)
    res = await client.get(f"/api/v1/riders/{corredor.slug}")
    assert res.status_code == 200, res.text

    # El dato sigue siendo el mismo: seis clasificaciones y seis fechas.
    cuerpo = res.json()
    assert len(cuerpo["standings"]) == 6
    assert len(cuerpo["history"]) == 6
    assert cuerpo["rider"]["slug"] == corredor.slug

    assert query_counter["n"] <= 8, (
        f"Hace {query_counter['n']} consultas para un corredor: {query_counter['sql']}"
    )


async def test_el_numero_de_consultas_no_crece_con_las_filas(
    client, async_session: AsyncSession, query_counter
):
    """La firma del N+1: más filas NO pueden significar más consultas.

    Es la prueba que no depende del umbral: con el doble de clasificaciones
    acumuladas, el endpoint tiene que hacer las MISMAS consultas.
    """
    datos = await _sembrar_campeonato_para_n_plus_1(
        async_session, fechas=2, corredores=1, categorias=2, equipos=1
    )
    corredor = datos["corredores"][0]

    _reiniciar_contador(query_counter)
    res = await client.get(f"/api/v1/riders/{corredor.slug}")
    assert res.status_code == 200, res.text
    consultas_pocas = query_counter["n"]
    assert len(res.json()["standings"]) == 2

    # El corredor pasa a tener clasificaciones en más categorías: las filas
    # crecen, las consultas NO pueden crecer con ellas.
    for i in range(2, 6):
        cat = Category(name=f"CATEGORIA {i}", short_code=f"C{i:02d}")
        async_session.add(cat)
        await async_session.flush()
        async_session.add(
            ChampionshipStanding(
                rider_id=corredor.id,
                category_id=cat.id,
                total_points=10,
                first_places_count=1,
                last_stage_rank=1,
                total_elapsed_ms=3_600_000,
                stages_completed=1,
                current_rank=1,
                rank_delta=0,
            )
        )
    await async_session.commit()

    _reiniciar_contador(query_counter)
    res = await client.get(f"/api/v1/riders/{corredor.slug}")
    assert res.status_code == 200, res.text
    consultas_muchas = query_counter["n"]
    assert len(res.json()["standings"]) == 6

    assert consultas_muchas == consultas_pocas, (
        f"el número de consultas crece con las filas: {consultas_pocas} -> {consultas_muchas}"
    )


async def test_perfil_equipo_no_hace_n_plus_1(
    client, async_session: AsyncSession, query_counter
):
    """El perfil de un equipo no hace dos consultas por cada corredor.

    Antes: por cada corredor de la plantilla se ejecutaba la MISMA consulta
    de sus inscripciones dos veces (una para los puntos y otra para las
    categorías).
    """
    datos = await _sembrar_campeonato_para_n_plus_1(
        async_session, fechas=2, corredores=20, categorias=3, equipos=1
    )
    equipo = datos["equipos"][0]

    _reiniciar_contador(query_counter)
    res = await client.get(f"/api/v1/teams/{equipo.slug}")
    assert res.status_code == 200, res.text

    cuerpo = res.json()
    assert len(cuerpo["roster"]) == 20

    assert query_counter["n"] <= 8, (
        f"Hace {query_counter['n']} consultas para un equipo: {query_counter['sql']}"
    )


async def test_resultados_de_fecha_no_hacen_n_plus_1(
    client, async_session: AsyncSession, query_counter
):
    """Los resultados de una fecha no hacen una consulta por cada corredor.

    Antes: cada inscripción recargaba corredor, categoría y equipo con un
    `refresh` (cuatro consultas por fila).
    """
    datos = await _sembrar_campeonato_para_n_plus_1(
        async_session, fechas=1, corredores=20, categorias=3, equipos=3
    )
    fecha = datos["fechas"][0]

    _reiniciar_contador(query_counter)
    res = await client.get(f"/api/v1/stages/{fecha.slug}/results")
    assert res.status_code == 200, res.text

    total = sum(len(filas) for filas in res.json()["categories"].values())
    assert total == 20

    assert query_counter["n"] <= 8, (
        f"Hace {query_counter['n']} consultas para los resultados: {query_counter['sql']}"
    )


async def test_ficha_de_fecha_no_hace_n_plus_1(
    client, async_session: AsyncSession, query_counter
):
    """La ficha de una fecha no hace una consulta por cada segmento.

    Antes: los intentos de Strava se pedían de uno en uno (25 segmentos en
    la fecha real) y los extremos recargaban corredor, categoría y equipo.
    """
    datos = await _sembrar_campeonato_para_n_plus_1(
        async_session, fechas=1, corredores=20, categorias=3, equipos=3
    )
    fecha = datos["fechas"][0]
    await _sembrar_segmentos_de_strava(async_session, fecha, segmentos=6)

    _reiniciar_contador(query_counter)
    res = await client.get(f"/api/v1/stages/{fecha.slug}")
    assert res.status_code == 200, res.text

    cuerpo = res.json()
    assert len(cuerpo["strava_segments"]) == 6

    # Los segmentos se cargan de una vez: ni uno por segmento.
    assert _consultas_sobre(query_counter, "strava_segments") <= 1
    assert query_counter["n"] <= 12, (
        f"Hace {query_counter['n']} consultas para la ficha: {query_counter['sql']}"
    )


async def test_live_summary_no_hace_n_plus_1(
    client, async_session: AsyncSession, query_counter
):
    """El resumen en vivo no hace una consulta por cada corredor."""
    datos = await _sembrar_campeonato_para_n_plus_1(
        async_session, fechas=1, corredores=20, categorias=3, equipos=3
    )
    fecha = datos["fechas"][0]

    _reiniciar_contador(query_counter)
    res = await client.get(f"/api/v1/stages/{fecha.id}/live-summary")
    assert res.status_code == 200, res.text
    assert len(res.json()["leaderboard"]) == 20

    assert query_counter["n"] <= 8, (
        f"Hace {query_counter['n']} consultas para el live-summary: {query_counter['sql']}"
    )


async def test_pagos_pendientes_no_hacen_n_plus_1(
    client, async_session: AsyncSession, query_counter, monkeypatch
):
    """La lista de pagos pendientes no hace una consulta por cada inscripción."""
    # La clave de administrador se fija en la prueba: la del entorno puede
    # no existir (clon limpio sin `.env`) y el endpoint respondería 503.
    monkeypatch.setattr(settings, "ADMIN_API_KEY", CLAVE_DE_PRUEBA)

    datos = await _sembrar_campeonato_para_n_plus_1(
        async_session,
        fechas=1,
        corredores=20,
        categorias=3,
        equipos=3,
        pago=PaymentStatusEnum.PENDING,
    )
    assert datos["fechas"]

    _reiniciar_contador(query_counter)
    res = await client.get(
        "/api/v1/admin/pending-payments",
        headers={"X-Admin-Key": CLAVE_DE_PRUEBA},
    )
    assert res.status_code == 200, res.text
    assert len(res.json()) == 20

    assert query_counter["n"] <= 8, (
        f"Hace {query_counter['n']} consultas para los pagos: {query_counter['sql']}"
    )


async def test_clasificacion_individual_no_hace_n_plus_1(
    client, async_session: AsyncSession, query_counter
):
    """La clasificación individual no hace una consulta por cada fila."""
    await _sembrar_campeonato_para_n_plus_1(
        async_session, fechas=1, corredores=10, categorias=3, equipos=3
    )

    _reiniciar_contador(query_counter)
    res = await client.get("/api/v1/public/standings/individual")
    assert res.status_code == 200, res.text
    assert len(res.json()) == 30

    assert query_counter["n"] <= 8, (
        f"Hace {query_counter['n']} consultas para la clasificación: {query_counter['sql']}"
    )


async def test_el_excel_no_hace_n_plus_1(
    client, async_session: AsyncSession, query_counter
):
    """La exportación a Excel no hace una consulta por cada fila."""
    datos = await _sembrar_campeonato_para_n_plus_1(
        async_session, fechas=1, corredores=20, categorias=3, equipos=3
    )
    fecha = datos["fechas"][0]

    _reiniciar_contador(query_counter)
    res = await client.get(f"/api/v1/stages/{fecha.id}/export-excel")
    assert res.status_code == 200, res.text

    assert query_counter["n"] <= 8, (
        f"Hace {query_counter['n']} consultas para el Excel: {query_counter['sql']}"
    )


async def test_el_resumen_de_fecha_carga_los_segmentos_una_sola_vez(
    client, async_session: AsyncSession, query_counter
):
    """El resumen de la fecha comparte la carga de Strava.

    `compute_stage_strava` y `compute_stage_mountain_titles` cargaban los
    MISMOS segmentos y los MISMOS intentos por separado: cuatro consultas
    que se podían leer una sola vez.
    """
    datos = await _sembrar_campeonato_para_n_plus_1(
        async_session, fechas=1, corredores=20, categorias=3, equipos=3
    )
    fecha = datos["fechas"][0]
    await _sembrar_segmentos_de_strava(async_session, fecha, segmentos=6)

    _reiniciar_contador(query_counter)
    res = await client.get(f"/api/v1/stages/{fecha.slug}/summary")
    assert res.status_code == 200, res.text

    assert _consultas_sobre(query_counter, "strava_segments") == 1, (
        "los segmentos de Strava se cargan más de una vez: {0}".format(
            query_counter["sql"]
        )
    )
    assert _consultas_sobre(query_counter, "strava_efforts") == 1, (
        "los intentos de Strava se cargan más de una vez: {0}".format(
            query_counter["sql"]
        )
    )
