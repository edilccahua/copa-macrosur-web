import asyncio
import json
from typing import Dict, Set, AsyncGenerator


class SSEManager:
    def __init__(self):
        # stage_id -> set de asyncio.Queue
        self._listeners: Dict[int, Set[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, stage_id: int) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        async with self._lock:
            if stage_id not in self._listeners:
                self._listeners[stage_id] = set()
            self._listeners[stage_id].add(queue)
        return queue

    async def unsubscribe(self, stage_id: int, queue: asyncio.Queue) -> None:
        async with self._lock:
            if stage_id in self._listeners:
                self._listeners[stage_id].discard(queue)
                if not self._listeners[stage_id]:
                    del self._listeners[stage_id]

    async def broadcast(self, stage_id: int, event_type: str, data: dict) -> None:
        message = {
            "event": event_type,
            "data": data
        }
        async with self._lock:
            queues = list(self._listeners.get(stage_id, []))

        for queue in queues:
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                pass

    async def event_generator(self, stage_id: int) -> AsyncGenerator[str, None]:
        queue = await self.subscribe(stage_id)
        try:
            while True:
                try:
                    # Espera con timeout de 20s para enviar heartbeat : ping
                    message = await asyncio.wait_for(queue.get(), timeout=20.0)
                    event_name = message["event"]
                    payload = json.dumps(message["data"])
                    yield f"event: {event_name}\ndata: {payload}\n\n"
                except asyncio.TimeoutError:
                    # Heartbeat keep-alive para evitar desconexión de proxies
                    yield ": ping\n\n"
        finally:
            await self.unsubscribe(stage_id, queue)


sse_manager = SSEManager()
