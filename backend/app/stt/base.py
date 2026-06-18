"""Abstraction de session STT temps réel (cf. docs/api-contract.md §3).

Une session reçoit des frames audio (`send_audio`) et émet, de façon
asynchrone, les events du contrat (`vad_status`, `segment_start`, `word`,
`final_text`) consommés via `events()`. Le handler WebSocket lance deux
coroutines : un *feeder* (client → session) et un *forwarder* (session → client).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable


@runtime_checkable
class STTSession(Protocol):
    async def open(self) -> None: ...
    async def send_audio(self, chunk: bytes) -> None: ...
    async def finish(self) -> None: ...      # fin de l'audio montant
    async def close(self) -> None: ...        # libère les ressources
    def events(self) -> AsyncIterator[dict]: ...


class BaseSTTSession:
    """Base avec file interne d'events.

    Les sous-classes produisent des events via `_emit()` et signalent la fin
    avec `_emit_done()`. `events()` draine la file jusqu'au sentinel.
    """

    def __init__(self) -> None:
        self._queue: asyncio.Queue = asyncio.Queue()
        self._closed = False
        self._DONE = object()

    async def _emit(self, event: dict) -> None:
        await self._queue.put(event)

    async def _emit_done(self) -> None:
        if not self._closed:
            self._closed = True
            await self._queue.put(self._DONE)

    async def events(self) -> AsyncIterator[dict]:
        while True:
            item = await self._queue.get()
            if item is self._DONE:
                return
            yield item

    # Surchargeables par les sous-classes.
    async def open(self) -> None: ...

    async def send_audio(self, chunk: bytes) -> None: ...

    async def finish(self) -> None:
        await self._emit_done()

    async def close(self) -> None:
        await self._emit_done()
