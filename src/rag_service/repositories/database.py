"""SQLAlchemy models and repositories for durable ingestion metadata."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, selectinload
from sqlalchemy.types import JSON


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


JsonType = JSON().with_variant(JSONB, "postgresql")


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    namespace: Mapped[str] = mapped_column(String(128), nullable=False, default="default")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="uploading")
    source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    documents: Mapped[list[Document]] = relationship(
        back_populates="job", cascade="all, delete-orphan", lazy="selectin"
    )
    events: Mapped[list[JobEvent]] = relationship(back_populates="job", cascade="all, delete-orphan", lazy="selectin")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("ingestion_jobs.id", ondelete="CASCADE"))
    namespace: Mapped[str] = mapped_column(String(128), nullable=False, default="default")
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    object_key: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    job: Mapped[IngestionJob] = relationship(back_populates="documents")


class JobEvent(Base):
    __tablename__ = "job_events"
    __table_args__ = (UniqueConstraint("job_id", "sequence", name="uq_job_events_job_sequence"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("ingestion_jobs.id", ondelete="CASCADE"))
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    data_json: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    job: Mapped[IngestionJob] = relationship(back_populates="events")


class Database:
    def __init__(self, url: str) -> None:
        self.engine: AsyncEngine = create_async_engine(url, pool_pre_ping=True)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def close(self) -> None:
        await self.engine.dispose()


class JobRepository:
    """Transaction boundary for ingestion state and event audit records."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def get_by_idempotency_key(self, key: str) -> IngestionJob | None:
        async with self._sessions() as session:
            result = await session.execute(
                select(IngestionJob)
                .where(IngestionJob.idempotency_key == key)
                .options(selectinload(IngestionJob.documents))
            )
            return result.scalar_one_or_none()

    async def get_job(self, job_id: str) -> IngestionJob | None:
        async with self._sessions() as session:
            result = await session.execute(
                select(IngestionJob)
                .where(IngestionJob.id == job_id)
                .options(selectinload(IngestionJob.documents), selectinload(IngestionJob.events))
            )
            return result.scalar_one_or_none()

    async def create_job(
        self,
        *,
        job_id: str,
        idempotency_key: str | None,
        request_hash: str,
        namespace: str,
        documents: Sequence[dict[str, Any]],
    ) -> None:
        async with self._sessions.begin() as session:
            job = IngestionJob(
                id=job_id,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                namespace=namespace,
                status="uploading",
                source_count=len(documents),
            )
            session.add(job)
            for document in documents:
                session.add(Document(job_id=job_id, namespace=namespace, **document))

    async def mark_job_queued(self, job_id: str) -> None:
        await self._update_job(job_id, status="queued", error=None)

    async def mark_job_processing(self, job_id: str) -> None:
        await self._update_job(job_id, status="processing", started_at=utcnow())

    async def finish_job(self, job_id: str, *, completed: int, failed: int) -> None:
        status = "completed" if failed == 0 else "completed_with_errors" if completed else "failed"
        await self._update_job(
            job_id,
            status=status,
            completed_count=completed,
            failed_count=failed,
            finished_at=utcnow(),
        )

    async def fail_job(self, job_id: str, error: str) -> None:
        await self._update_job(job_id, status="failed", error=error, finished_at=utcnow())

    async def mark_document_processing(self, document_id: str) -> None:
        await self._update_document(document_id, status="processing", error=None)

    async def mark_document_indexed(self, document_id: str, chunk_count: int) -> None:
        await self._update_document(document_id, status="indexed", chunk_count=chunk_count, error=None)

    async def fail_document(self, document_id: str, error: str) -> None:
        await self._update_document(document_id, status="failed", error=error)

    async def record_event(self, job_id: str, sequence: int, kind: str, message: str, data: dict[str, Any]) -> None:
        import uuid

        async with self._sessions.begin() as session:
            session.add(
                JobEvent(
                    id=str(uuid.uuid4()),
                    job_id=job_id,
                    sequence=sequence,
                    kind=kind,
                    message=message,
                    data_json=data,
                )
            )

    async def _update_job(self, job_id: str, **values: Any) -> None:
        async with self._sessions.begin() as session:
            await session.execute(update(IngestionJob).where(IngestionJob.id == job_id).values(**values))

    async def _update_document(self, document_id: str, **values: Any) -> None:
        values["updated_at"] = utcnow()
        async with self._sessions.begin() as session:
            await session.execute(update(Document).where(Document.id == document_id).values(**values))


def digest_documents(documents: Sequence[tuple[str, bytes]]) -> str:
    hasher = hashlib.sha256()
    for filename, content in documents:
        hasher.update(filename.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(content)
        hasher.update(b"\0")
    return hasher.hexdigest()
