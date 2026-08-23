"""Application composition root; keeps framework code separate from services."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import text

from rag_service.config import Settings
from rag_service.domain import IngestionEvent
from rag_service.providers.openrouter import OpenRouterClient
from rag_service.repositories.database import Database, JobRepository
from rag_service.repositories.events import EventStore
from rag_service.repositories.qdrant import VectorStore
from rag_service.repositories.storage import ObjectStorage
from rag_service.services.events import EventPublisher
from rag_service.services.ingestion import IngestionService
from rag_service.services.retrieval import RetrievalService


class ServiceContainer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.database = Database(settings.database_url)
        self.jobs = JobRepository(self.database.sessions)
        self.event_store = EventStore(settings)
        self.storage = ObjectStorage(settings)
        self.vectors = VectorStore(settings)
        self.provider = OpenRouterClient(settings)
        self.events = EventPublisher(self.jobs, self.event_store)
        self.ingestion = IngestionService(
            settings,
            self.jobs,
            self.storage,
            self.vectors,
            self.provider,
            self.events,
            enqueue_ingestion_job,
        )
        self.retrieval = RetrievalService(settings, self.vectors, self.provider)

    async def startup(self) -> None:
        async with self.database.sessions() as session:
            await session.execute(text("SELECT 1"))
        await self.event_store.ping()
        await self.storage.ensure_bucket()
        await self.vectors.ensure_collection()

    async def shutdown(self) -> None:
        await self.provider.close()
        await self.vectors.close()
        await self.event_store.close()
        await self.database.close()

    async def readiness(self) -> bool:
        try:
            await self.startup()
        except Exception:
            return False
        return True

    async def stream_events(self, job_id: str, last_event_id: str = "0-0") -> AsyncIterator[tuple[str, IngestionEvent]]:
        current_id = last_event_id
        terminal_states = {"completed", "completed_with_errors", "failed"}
        while True:
            events = await self.event_store.read(job_id, last_event_id=current_id)
            if events:
                for event_id, event in events:
                    current_id = event_id
                    yield event_id, event
                    if event.kind in {"completed", "failed"}:
                        return
                continue
            job = await self.jobs.get_job(job_id)
            if job is None or job.status in terminal_states:
                if job is not None:
                    event = IngestionEvent(
                        kind="completed" if job.status != "failed" else "failed",
                        job_id=job.id,
                        timestamp=job.finished_at or job.created_at,
                        message=f"Ingestion job is {job.status}",
                        data={
                            "completed_documents": job.completed_count,
                            "failed_documents": job.failed_count,
                        },
                    )
                    yield current_id, event
                return


async def enqueue_ingestion_job(job_id: str) -> None:
    """Queue without importing worker modules during application startup."""

    from rag_service.workers.tasks import process_ingestion_job

    process_ingestion_job.send(job_id)
