"""
Presupuesto de rendimiento: caché, agregado de portada y compresión.

Estas pruebas fijan tres cosas que se midieron contra la producción real
(Render en Oregon + Neon + Cloudflare Pages):

  · **Tarea 5** — la caché en memoria se invalida cuando algo cambia de
    verdad: con un TTL de 120 s sin invalidar, el público veía datos viejos
    hasta dos minutos después de una marcación del juez.
  · **Tarea 6** — la portada se lee con UNA sola llamada a la API (antes
    eran siete: siete esperas de red en el SSR de Cloudflare).
  · **Tarea 7** — la API comprime sus respuestas grandes (GZip) y la
    transmisión en vivo NO se comprime (el SSE se.secuencia en el tiempo).

La caché en memoria es GLOBAL al proceso, así que el fixture `client` la
vacía antes de cada prueba: si no, una clasificación cacheada por un test
se vería en el siguiente sin tocar la base de datos.
"""
import uuid
from datetime import date as date_cls

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from backend.app.core.cache import cache
from backend.app.core.config import settings
from backend.app.models.entities import (
    Category,
    Checkpoint,
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

# Prefijos que ``invalidate_public`` tiene que vaciar: todo lo que el
# público puede leer por la API.
PREFIJOS_PUBLICOS = ("public:", "stages:", "stage:summary:", "stage:list:")


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


async def test_abrir_la_transmision_invalida_la_cache_publica(
    client, async_session: AsyncSession
):
    """Abrir o cerrar la transmisión invalida la caché del público.

    El estado de la transmisión es lo que la portada anuncia: si se
    cacheara, el enlace "en vivo" seguiría apareciendo (o desaparecería)
    hasta dos minutos después de la orden del organizador.
    """
    stage = await _sembrar_campeonato(async_session)

    await client.get("/api/v1/public/live-status")
    assert _claves_publicas(), "la caché pública debería estar llena"

    res = await client.post(
        f"/api/v1/stages/{stage.id}/live",
        json={"active": True},
        headers={"X-Admin-Key": settings.ADMIN_API_KEY},
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
