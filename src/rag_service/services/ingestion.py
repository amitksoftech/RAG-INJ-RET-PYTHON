"""Durable ingestion submission and worker execution."""

from __future__ import annotations

import hashlib
import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from rag_service.config import Settings
from rag_service.domain import IncomingDocument, VectorPoint
from rag_service.errors import ConflictError, PayloadTooLargeError, ValidationError
from rag_service.logging import log_extra
from rag_service.providers.openrouter import OpenRouterClient
from rag_service.repositories.database import Document, IngestionJob, JobRepository, digest_documents
from rag_service.repositories.qdrant import VectorStore
from rag_service.repositories.storage import ObjectStorage
from rag_service.services.chunking import chunk_text
from rag_service.services.events import EventPublisher
from rag_service.services.parsers import parse_document

logger = logging.getLogger(__name__)
Enqueue = Callable[[str], Awaitable[None]]


class IngestionService:
    def __init__(
        self,
        settings: Settings,
        repository: JobRepository,
        storage: ObjectStorage,
        vectors: VectorStore,
        provider: OpenRouterClient,
        events: EventPublisher,
        enqueue: Enqueue,
    ) -> None:
        self._settings = settings
        self._repository = repository
        self._storage = storage
        self._vectors = vectors
        self._provider = provider
        self._events = events
        self._enqueue = enqueue

    async def submit(
        self,
        documents: list[IncomingDocument],
        *,
        namespace: str,
        idempotency_key: str | None,
    ) -> tuple[IngestionJob, bool]:
        self._validate_submission(documents, namespace)
        request_hash = digest_documents([(document.filename, document.content) for document in documents])
        if idempotency_key:
            existing = await self._repository.get_by_idempotency_key(idempotency_key)
            if existing:
                if existing.request_hash != request_hash:
                    raise ConflictError("Idempotency-Key was already used with a different request body")
                return existing, False

        job_id = str(uuid.uuid4())
        records: list[dict[str, Any]] = []
        upload_pairs: list[tuple[str, IncomingDocument]] = []
        for source in documents:
            document_id = str(uuid.uuid4())
            source_hash = hashlib.sha256(source.content).hexdigest()
            object_key = f"sources/{namespace}/{job_id}/{document_id}/{source.filename}"
            records.append(
                {
                    "id": document_id,
                    "filename": source.filename,
                    "content_type": source.content_type,
                    "object_key": object_key,
                    "sha256": source_hash,
                    "metadata_json": source.metadata,
                }
            )
            upload_pairs.append((object_key, source))
        await self._repository.create_job(
            job_id=job_id,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            namespace=namespace,
            documents=records,
        )
        try:
            for object_key, source in upload_pairs:
                await self._storage.put(object_key, source.content, source.content_type)
        except Exception as error:
            message = "Failed to persist one or more source documents"
            await self._repository.fail_job(job_id, message)
            await self._events.publish(
                job_id=job_id,
                kind="failed",
                message=message,
                sequence=1,
                data={"error_type": type(error).__name__},
            )
            raise

        await self._repository.mark_job_queued(job_id)
        await self._events.publish(
            job_id=job_id,
            kind="queued",
            message="Ingestion job queued",
            sequence=1,
            data={"document_count": len(documents)},
        )
        await self._enqueue(job_id)
        job = await self._repository.get_job(job_id)
        if job is None:  # defensive: the job was just committed
            raise RuntimeError("Created ingestion job was not found")
        return job, True

    async def process(self, job_id: str) -> None:
        job = await self._repository.get_job(job_id)
        if job is None or job.status in {"completed", "completed_with_errors", "failed"}:
            return
        sequence = len(job.events) + 1
        completed = 0
        failed = 0
        await self._repository.mark_job_processing(job_id)
        sequence = await self._publish(job_id, sequence, "started", "Worker started processing ingestion job")

        for document in job.documents:
            try:
                sequence = await self._process_document(job, document, sequence)
                completed += 1
            except Exception as error:
                failed += 1
                safe_message = f"Document processing failed: {type(error).__name__}"
                logger.exception(
                    "ingestion_document_failed",
                    extra=log_extra(job_id=job_id, document_id=document.id, error_type=type(error).__name__),
                )
                await self._repository.fail_document(document.id, safe_message)
                try:
                    await self._vectors.delete_document(document.id)
                except Exception:
                    logger.exception(
                        "ingestion_compensating_cleanup_failed",
                        extra=log_extra(job_id=job_id, document_id=document.id),
                    )
                sequence = await self._publish(
                    job_id,
                    sequence,
                    "failed",
                    safe_message,
                    document_id=document.id,
                    data={"filename": document.filename, "error_type": type(error).__name__},
                )

        await self._repository.finish_job(job_id, completed=completed, failed=failed)
        message = "Ingestion completed" if failed == 0 else "Ingestion completed with document errors"
        await self._publish(
            job_id,
            sequence,
            "completed",
            message,
            data={"completed_documents": completed, "failed_documents": failed},
        )

    async def _process_document(self, job: IngestionJob, document: Document, sequence: int) -> int:
        await self._repository.mark_document_processing(document.id)
        sequence = await self._publish(
            job.id,
            sequence,
            "parsing",
            "Parsing document",
            document_id=document.id,
            data={"filename": document.filename},
        )
        content = await self._storage.get(document.object_key)
        parsed = parse_document(document.filename, document.content_type, content)
        base_metadata = {
            "filename": document.filename,
            "source_sha256": document.sha256,
            "metadata": document.metadata_json,
        }
        chunks = chunk_text(
            text=parsed.text,
            document_id=document.id,
            namespace=job.namespace,
            base_metadata=base_metadata,
            size=self._settings.chunk_size_chars,
            overlap=self._settings.chunk_overlap_chars,
        )
        if not chunks:
            raise ValidationError(f"{document.filename} did not produce any chunks")
        sequence = await self._publish(
            job.id,
            sequence,
            "chunking",
            "Document chunked",
            document_id=document.id,
            data={"chunk_count": len(chunks)},
        )
        vectors: list[VectorPoint] = []
        for start in range(0, len(chunks), self._settings.embedding_batch_size):
            batch = chunks[start : start + self._settings.embedding_batch_size]
            embeddings = await self._provider.embed([chunk.text for chunk in batch])
            vectors.extend(
                VectorPoint(chunk=chunk, vector=embedding) for chunk, embedding in zip(batch, embeddings, strict=True)
            )
        sequence = await self._publish(
            job.id,
            sequence,
            "embedding",
            "Embeddings created",
            document_id=document.id,
            data={"chunk_count": len(vectors)},
        )
        await self._vectors.delete_document(document.id)
        await self._vectors.upsert(vectors)
        sequence = await self._publish(
            job.id,
            sequence,
            "indexing",
            "Vectors indexed",
            document_id=document.id,
            data={"chunk_count": len(vectors)},
        )
        await self._repository.mark_document_indexed(document.id, len(vectors))
        return sequence

    async def _publish(
        self,
        job_id: str,
        sequence: int,
        kind: str,
        message: str,
        *,
        document_id: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> int:
        await self._events.publish(
            job_id=job_id,
            kind=kind,
            message=message,
            sequence=sequence,
            document_id=document_id,
            data=data,
        )
        return sequence + 1

    def _validate_submission(self, documents: list[IncomingDocument], namespace: str) -> None:
        if not documents:
            raise ValidationError("At least one document is required")
        if len(documents) > self._settings.max_documents_per_job:
            raise PayloadTooLargeError("Too many documents in one ingestion request")
        if not namespace or len(namespace) > 128:
            raise ValidationError("namespace must be between 1 and 128 characters")
        for document in documents:
            if not document.filename or len(document.filename) > 512:
                raise ValidationError("A valid document filename is required")
            if not document.content:
                raise ValidationError(f"{document.filename} is empty")
            if len(document.content) > self._settings.max_upload_bytes:
                raise PayloadTooLargeError(f"{document.filename} exceeds the upload size limit")
