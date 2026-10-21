import time
from typing import Any, Dict, List, Optional, Tuple


class MemoryCache:
    """Caché en memoria ultraligero con TTL para endpoints de lectura pública.

    Evita la latencia de red recurrente (160ms por query) entre Render (USA)
    y Neon PostgreSQL (São Paulo, Brasil) para datos que no cambian en cada request.

    IMPORTANTE: la caché funciona TAMBIÉN bajo pytest. Antes había un bypass
    (`PYTEST_CURRENT_TEST`) que la dejaba desactivada en las pruebas; con él,
    la invalidación no se podía probar de verdad y los tests veían siempre la
    base de datos. Como la caché es GLOBAL al proceso, el fixture `client` de
    `backend/tests/conftest.py` la vacía antes de cada prueba: así cada test
    arranca con la caché vacía y ninguno ve el valor de otro.
    """

    def __init__(self, default_ttl_seconds: int = 120):
        self._store: Dict[str, Tuple[float, Any]] = {}
        self.default_ttl = default_ttl_seconds

    def get(self, key: str) -> Optional[Any]:
        item = self._store.get(key)
        if item is None:
            return None
        expires_at, value = item
        if time.time() > expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl
        self._store[key] = (time.time() + ttl, value)

    def delete_prefix(self, prefix: str) -> None:
        """Borra todas las claves que empiezan por `prefix`.

        Se usa para invalidar una familia entera de respuestas (todas las
        clasificaciones, por ejemplo) sin tener que enumerar sus claves.
        """
        for key in [k for k in self._store if k.startswith(prefix)]:
            del self._store[key]

    def ttl_restante(self, key: str) -> Optional[float]:
        """Los segundos que le quedan a una clave, o `None` si no existe.

        Es la inspección que usan las pruebas para comprobar CON QUÉ TTL se
        cacheó una lectura (la caché no expone los plazos por otro lado).
        Una clave ya caducada cuenta como inexistente: no se devuelve un
        TTL negativo que haya que interpretar.
        """
        item = self._store.get(key)
        if item is None:
            return None
        expires_at, _value = item
        restante = expires_at - time.time()
        if restante <= 0:
            del self._store[key]
            return None
        return restante

    def invalidate_public(self) -> None:
        """Invalida TODO lo que el público puede leer.

        Se llama después de cualquier mutación (una marcación del juez, la
        apertura de la transmisión, una ingesta de Excel, una pre-inscripción):
        con la caché de 120 s sin invalidar, el público veía datos viejos
        hasta dos minutos.

        Los prefijos son los REALES de cada lectura: `public:` cubre el
        agregado de la portada (`public:home`), el estado de la transmisión
        (`public:live_status`) y las clasificaciones; `stages:` cubre
        `stages:list` y `stage:summary:` cubre el resumen de cada fecha.
        """
        for prefix in ("public:", "stages:", "stage:summary:"):
            self.delete_prefix(prefix)

    def keys(self) -> List[str]:
        """Las claves vivas. Las caducadas se descartan al listarlas.

        Es la inspección que usan las pruebas: si la invalidación falla, la
        clave sigue viva y el test lo ve.
        """
        ahora = time.time()
        for key in [k for k, (expira, _) in self._store.items() if ahora > expira]:
            del self._store[key]
        return list(self._store.keys())

    def clear(self) -> None:
        self._store.clear()


cache = MemoryCache(default_ttl_seconds=120)
