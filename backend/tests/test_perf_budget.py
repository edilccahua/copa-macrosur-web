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
    for nombre in ("TEAM ALFA", "TEAM BETA"):
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
