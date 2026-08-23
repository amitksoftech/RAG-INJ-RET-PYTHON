from __future__ import annotations

from typing import Any

import pytest

from rag_service.config import Settings
from rag_service.domain import IncomingDocument
from rag_service.repositories.database import IngestionJob
from rag_service.services.ingestion import IngestionService


class FakeRepository:
    def __init__(self) -> None:
        self.jobs: dict[str, IngestionJob] = {}
        self.idempotency: dict[str, IngestionJob] = {}

    async def get_by_idempotency_key(self, key: str) -> IngestionJob | None:
        return self.idempotency.get(key)

    async def create_job(self, **kwargs: Any) -> None:
        job = IngestionJob(
            id=kwargs["job_id"],
            idempotency_key=kwargs["idempotency_key"],
            request_hash=kwargs["request_hash"],
            namespace=kwargs["namespace"],
            source_count=len(kwargs["documents"]),
            status="uploading",
        )
        self.jobs[job.id] = job
        if job.idempotency_key:
            self.idempotency[job.idempotency_key] = job

    async def get_job(self, job_id: str) -> IngestionJob | None:
        return self.jobs.get(job_id)

    async def mark_job_queued(self, job_id: str) -> None:
        self.jobs[job_id].status = "queued"

    async def fail_job(self, job_id: str, error: str) -> None:
        self.jobs[job_id].status = "failed"
        self.jobs[job_id].error = error


class FakeStorage:
    async def put(self, key: str, content: bytes, content_type: str) -> None:
        return None


class FakeEvents:
    async def publish(self, **kwargs: Any) -> str:
        return "1-0"


@pytest.mark.asyncio
async def test_idempotency_reuses_same_job_without_reenqueueing() -> None:
    repository = FakeRepository()
    queued: list[str] = []

    async def enqueue(job_id: str) -> None:
        queued.append(job_id)

    service = IngestionService(
        Settings(embedding_dimensions=2),
        repository,  # type: ignore[arg-type]
        FakeStorage(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        FakeEvents(),  # type: ignore[arg-type]
        enqueue,
    )
    documents = [IncomingDocument("note.txt", "text/plain", b"hello", {})]

    first, created = await service.submit(documents, namespace="default", idempotency_key="same-key")
    second, replayed = await service.submit(documents, namespace="default", idempotency_key="same-key")

    assert created is True
    assert replayed is False
    assert first.id == second.id
    assert queued == [first.id]
