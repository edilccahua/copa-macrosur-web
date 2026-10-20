import os
import time
from typing import Any, Dict, Optional, Tuple


class MemoryCache:
    """Caché en memoria ultraligero con TTL para endpoints de lectura pública.
    
    Evita la latencia de red recurrente (160ms por query) entre Render (USA)
    y Neon PostgreSQL (São Paulo, Brasil) para datos que no cambian en cada request.
    """

    def __init__(self, default_ttl_seconds: int = 120):
        self._store: Dict[str, Tuple[float, Any]] = {}
        self.default_ttl = default_ttl_seconds

    def get(self, key: str) -> Optional[Any]:
        if "PYTEST_CURRENT_TEST" in os.environ:
            return None
        item = self._store.get(key)
        if item is None:
            return None
        expires_at, value = item
        if time.time() > expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        if "PYTEST_CURRENT_TEST" in os.environ:
            return
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl
        self._store[key] = (time.time() + ttl, value)

    def clear(self) -> None:
        self._store.clear()


cache = MemoryCache(default_ttl_seconds=120)
