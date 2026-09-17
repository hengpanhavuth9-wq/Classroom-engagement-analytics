"""
In-memory Redis replacement for local development (no Redis server needed).
Supports: get, setex, publish, pubsub subscribe/listen.
"""
import asyncio
import time
from typing import Any


class InMemoryPubSub:
    def __init__(self, store: "InMemoryRedis", channel: str):
        self._store   = store
        self._channel = channel
        self._queue: asyncio.Queue = asyncio.Queue()

    async def subscribe(self, channel: str):
        self._channel = channel
        self._store._subscribers.setdefault(channel, []).append(self._queue)

    async def unsubscribe(self, channel: str | None = None) -> None:
        """Drop this queue from the channel's subscriber list.

        Without this, a disconnected dashboard's queue stayed registered
        forever — every subsequent frame's metrics kept getting enqueued to
        it, unread, for the life of the process.
        """
        queues = self._store._subscribers.get(channel or self._channel)
        if queues and self._queue in queues:
            queues.remove(self._queue)

    async def aclose(self) -> None:
        await self.unsubscribe()

    async def listen(self):
        while True:
            data = await self._queue.get()
            yield {"type": "message", "data": data}


class InMemoryRedis:
    """Drop-in async Redis mock backed by a plain dict + asyncio queues."""

    def __init__(self):
        self._store: dict[str, tuple[Any, float | None]] = {}  # key -> (value, expires_at)
        self._subscribers: dict[str, list[asyncio.Queue]] = {}

    async def get(self, key: str) -> str | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if expires_at and time.monotonic() > expires_at:
            del self._store[key]
            return None
        return value

    async def set(self, key: str, value: str) -> None:
        self._store[key] = (value, None)

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self._store[key] = (value, time.monotonic() + ttl)

    async def publish(self, channel: str, message: str) -> int:
        queues = self._subscribers.get(channel, [])
        for q in queues:
            await q.put(message)
        return len(queues)

    def pubsub(self) -> InMemoryPubSub:
        return InMemoryPubSub(self, "")

    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        pass
