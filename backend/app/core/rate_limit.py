"""Ventana deslizante: el reloj de las cuotas por IP.

Es un limitador EN MEMORIA y POR PROCESO. Sirve para el backend tal como
está hoy (una sola instancia en Render). Si algún día corre en varias
instancias, hay que mover el contador a Redis: dos procesos con contadores
propios dejarían pasar el doble de lo permitido.
"""
import time
from collections import deque
from typing import Deque, Dict, Tuple


class SlidingWindowLimiter:
    """N peticiones por clave y ventana.

    A diferencia de un contador que se reinicia cada minuto, la ventana
    deslizante no tiene "huecos": una persona que manda 10 peticiones en el
    segundo 59 y 10 más en el segundo 61 no puede Colarse entre dos
    reinicios.
    """

    def __init__(self, limit: int, window_seconds: int = 60) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        # clave (IP) -> instantes de las peticiones admitidas
        self._hits: Dict[str, Deque[float]] = {}

    def allow(self, key: str) -> Tuple[bool, int]:
        """¿Admite esta petición?

        Devuelve `(permitido, segundos_para_reintentar)`. El segundo valor
        sólo tiene sentido cuando el primero es `False`: es lo que va en la
        cabecera `Retry-After`.
        """
        ahora = time.monotonic()
        hits = self._hits.setdefault(key, deque())
        # Se olvidan las marcas que ya salieron de la ventana.
        while hits and ahora - hits[0] >= self.window_seconds:
            hits.popleft()
        if len(hits) >= self.limit:
            # La ventana se cierra cuando caduca la marca más antigua.
            retry_after = max(1, int(self.window_seconds - (ahora - hits[0])))
            return False, retry_after
        hits.append(ahora)
        return True, 0

    def reset(self) -> None:
        """Vacía la ventana (arranque limpio y pruebas)."""
        self._hits.clear()
