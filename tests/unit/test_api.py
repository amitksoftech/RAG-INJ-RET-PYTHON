from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest

from rag_service.config import Settings
from rag_service.domain import IngestionEvent, RetrievedChunk
from rag_service.main import create_app
from rag_service.services.retrieval import RetrievalResult


class FakeIngestion:
    async def submit(self, documents, *, namespace: str, idempotency_key: str | None):  # type: ignore[no-untyped-def]
        assert namespace == "default"
        assert documents[0].content == b"hello"
        assert idempotency_key == "ingest-1"
        return SimpleNamespace(id="job-1"), True


class FakeRetrieval:
    async def retrieve(self, query: str, namespace: str, top_k: int) -> RetrievalResult:
        assert query == "What changed?"
        assert namespace == "default"
        assert top_k == 5
        chunk = RetrievedChunk("chunk-1", "doc-1", "default", "A source sentence.", 0.9, "a.md", None, {})
        return RetrievalResult("A sourced answer [1].", [chunk], {"total_tokens": 10})


class FakeContainer:
    settings = Settings(embedding_dimensions=2)
    ingestion = FakeIngestion()
    retrieval = FakeRetrieval()

    async def startup(self) -> None:
        return None

    async def shutdown(self) -> None:
        return None

    async def readiness(self) -> bool:
        return True

    async def stream_events(self, job_id: str, last_event_id: str = "0-0") -> AsyncIterator[tuple[str, IngestionEvent]]:
        yield "1-0", IngestionEvent("queued", job_id, datetime.now(UTC), "Queued")
        yield "2-0", IngestionEvent("completed", job_id, datetime.now(UTC), "Done")


@pytest.mark.asyncio
async def test_json_ingestion_returns_sse_events() -> None:
    container = FakeContainer()
    app = create_app(container.settings, container)  # type: ignore[arg-type]
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/ingestions",
            headers={"Idempotency-Key": "ingest-1"},
            json={"documents": [{"filename": "note.txt", "content": "hello"}]},
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: queued" in response.text
    assert "event: completed" in response.text
    assert response.headers["x-ingestion-job-id"] == "job-1"


@pytest.mark.asyncio
async def test_retrieval_returns_citations_and_request_id() -> None:
    container = FakeContainer()
    app = create_app(container.settings, container)  # type: ignore[arg-type]
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/v1/retrievals", json={"query": "What changed?"})

    body = response.json()
    assert response.status_code == 200
    assert body["citations"][0]["chunk_id"] == "chunk-1"
    assert body["request_id"] == response.headers["x-request-id"]
