"""HTTP routes: two public business routes plus private operations endpoints."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, cast

from fastapi import APIRouter, Header, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import ValidationError as PydanticValidationError
from starlette.datastructures import UploadFile

from rag_service.api.schemas import (
    CitationResponse,
    JsonIngestionRequest,
    RetrievalRequest,
    RetrievalResponse,
)
from rag_service.container import ServiceContainer
from rag_service.domain import IncomingDocument, IngestionEvent
from rag_service.errors import PayloadTooLargeError, ValidationError
from rag_service.services.parsers import normalized_content_type

router = APIRouter()


def _container(request: Request) -> ServiceContainer:
    return cast(ServiceContainer, request.app.state.container)


@router.post("/v1/ingestions", tags=["rag"])
async def create_ingestion(
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    container = _container(request)
    documents, namespace = await _read_ingestion_request(request, container.settings.max_upload_bytes)
    job, _created = await container.ingestion.submit(documents, namespace=namespace, idempotency_key=idempotency_key)
    return StreamingResponse(
        _sse_events(container, job.id, last_event_id or "0-0"),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Ingestion-Job-ID": job.id,
        },
    )


@router.post("/v1/retrievals", response_model=RetrievalResponse, tags=["rag"])
async def retrieve(request: Request, payload: RetrievalRequest) -> RetrievalResponse:
    result = await _container(request).retrieval.retrieve(payload.query, payload.namespace, payload.top_k)
    citations = [
        CitationResponse(
            citation_id=index,
            chunk_id=chunk.chunk_id,
            document_id=chunk.document_id,
            filename=chunk.filename,
            page=chunk.page,
            score=chunk.score,
            text_snippet=chunk.text[:500],
            metadata=chunk.metadata,
        )
        for index, chunk in enumerate(result.citations, start=1)
    ]
    return RetrievalResponse(
        request_id=request.state.request_id,
        answer=result.answer,
        citations=citations,
        usage=result.usage,
    )


operations = APIRouter(include_in_schema=False)


@operations.get("/healthz")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@operations.get("/readyz")
async def readiness(request: Request) -> JSONResponse:
    ready = await _container(request).readiness()
    return JSONResponse({"status": "ready" if ready else "not_ready"}, status_code=200 if ready else 503)


@operations.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


async def _read_ingestion_request(request: Request, max_upload_bytes: int) -> tuple[list[IncomingDocument], str]:
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > max_upload_bytes * 11:
        raise PayloadTooLargeError("Request exceeds the configured total upload size")
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("application/json"):
        try:
            payload = JsonIngestionRequest.model_validate(await request.json())
        except (PydanticValidationError, json.JSONDecodeError) as error:
            raise ValidationError("Invalid JSON ingestion request") from error
        json_documents = [
            IncomingDocument(
                filename=item.filename,
                content_type=normalized_content_type(item.filename, item.content_type),
                content=item.content.encode("utf-8"),
                metadata=item.metadata,
            )
            for item in payload.documents
        ]
        return json_documents, payload.namespace
    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        namespace = str(form.get("namespace") or "default")
        metadata = _parse_metadata(form.get("metadata"))
        uploads = [item for item in form.getlist("files") if isinstance(item, UploadFile)]
        if not uploads:
            raise ValidationError("Multipart ingestion requires one or more files fields")
        documents: list[IncomingDocument] = []
        for upload in uploads:
            content = await upload.read(max_upload_bytes + 1)
            if len(content) > max_upload_bytes:
                raise PayloadTooLargeError(f"{upload.filename or 'upload'} exceeds the upload size limit")
            filename = upload.filename or "upload"
            documents.append(
                IncomingDocument(
                    filename=filename,
                    content_type=normalized_content_type(filename, upload.content_type),
                    content=content,
                    metadata=metadata,
                )
            )
        return documents, namespace
    raise ValidationError("Use application/json or multipart/form-data for ingestion")


def _parse_metadata(raw_metadata: Any) -> dict[str, Any]:
    if raw_metadata is None or raw_metadata == "":
        return {}
    try:
        value = json.loads(str(raw_metadata))
    except json.JSONDecodeError as error:
        raise ValidationError("metadata must be a JSON object") from error
    if not isinstance(value, dict):
        raise ValidationError("metadata must be a JSON object")
    return value


async def _sse_events(container: ServiceContainer, job_id: str, last_event_id: str) -> AsyncIterator[str]:
    async for event_id, event in container.stream_events(job_id, last_event_id):
        yield _format_sse(event_id, event)


def _format_sse(event_id: str, event: IngestionEvent) -> str:
    payload = {
        "job_id": event.job_id,
        "timestamp": event.timestamp.isoformat(),
        "message": event.message,
        "document_id": event.document_id,
        "data": event.data or {},
    }
    return f"id: {event_id}\nevent: {event.kind}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n"
