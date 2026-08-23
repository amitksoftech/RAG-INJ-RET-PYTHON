"""Redis Streams adapter for live and replayable ingestion events."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from redis.asyncio import Redis

from rag_service.config import Settings
from rag_service.domain import IngestionEvent


class EventStore:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: Redis = Redis.from_url(settings.redis_url, decode_responses=True)

    @staticmethod
    def stream_key(job_id: str) -> str:
        return f"ingestion-events:{job_id}"

    async def ping(self) -> None:
        await self._client.ping()

    async def close(self) -> None:
        await self._client.aclose()

    async def append(self, event: IngestionEvent) -> str:
        payload = {
            "kind": event.kind,
            "job_id": event.job_id,
            "timestamp": event.timestamp.isoformat(),
            "message": event.message,
            "document_id": event.document_id or "",
            "data": json.dumps(event.data or {}, separators=(",", ":")),
        }
        stream = self.stream_key(event.job_id)
        event_id = await self._client.xadd(stream, payload)  # type: ignore[arg-type]
        await self._client.expire(stream, self._settings.event_retention_seconds)
        return str(event_id)

    async def read(
        self,
        job_id: str,
        *,
        last_event_id: str = "0-0",
        block_ms: int = 15000,
    ) -> list[tuple[str, IngestionEvent]]:
        response = await self._client.xread({self.stream_key(job_id): last_event_id}, count=100, block=block_ms)
        events: list[tuple[str, IngestionEvent]] = []
        for _, entries in response:
            for entry_id, fields in entries:
                timestamp = datetime.fromisoformat(fields["timestamp"])
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=UTC)
                events.append(
                    (
                        str(entry_id),
                        IngestionEvent(
                            kind=fields["kind"],
                            job_id=fields["job_id"],
                            timestamp=timestamp,
                            message=fields["message"],
                            document_id=fields.get("document_id") or None,
                            data=json.loads(fields.get("data") or "{}"),
                        ),
                    )
                )
        return events

    async def stream(self, job_id: str, last_event_id: str = "0-0") -> AsyncIterator[tuple[str, IngestionEvent]]:
        current_id = last_event_id
        while True:
            events = await self.read(job_id, last_event_id=current_id)
            if not events:
                await asyncio.sleep(0)
                continue
            for event_id, event in events:
                current_id = event_id
                yield event_id, event
