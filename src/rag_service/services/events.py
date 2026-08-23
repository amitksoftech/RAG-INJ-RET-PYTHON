"""Coordinated durable audit and Redis Stream event publishing."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from rag_service.domain import IngestionEvent
from rag_service.repositories.database import JobRepository
from rag_service.repositories.events import EventStore


class EventPublisher:
    def __init__(self, repository: JobRepository, event_store: EventStore) -> None:
        self._repository = repository
        self._event_store = event_store

    async def publish(
        self,
        *,
        job_id: str,
        kind: str,
        message: str,
        sequence: int,
        document_id: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> str:
        event_data = data or {}
        await self._repository.record_event(job_id, sequence, kind, message, event_data)
        return await self._event_store.append(
            IngestionEvent(
                kind=kind,
                job_id=job_id,
                timestamp=datetime.now(UTC),
                message=message,
                document_id=document_id,
                data=event_data,
            )
        )
