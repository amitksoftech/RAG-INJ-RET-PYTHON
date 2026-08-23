from __future__ import annotations

from typing import Any

import pytest

from rag_service.config import Settings
from rag_service.domain import RetrievedChunk
from rag_service.services.retrieval import RetrievalService


class FakeProvider:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        assert texts == ["What is the policy?"]
        return [[0.1, 0.2]]

    async def answer(self, prompt: str) -> tuple[str, dict[str, Any]]:
        assert "[1]" in prompt and "[2]" in prompt
        return "The policy requires approval [2] and nothing else [99].", {"total_tokens": 11}


class FakeVectors:
    async def search(self, vector: list[float], namespace: str, limit: int) -> list[RetrievedChunk]:
        assert vector == [0.1, 0.2]
        assert namespace == "default"
        assert limit == 5
        return [
            RetrievedChunk("c1", "d1", "default", "First source", 0.91, "one.md", None, {}),
            RetrievedChunk("c2", "d2", "default", "Second source", 0.87, "two.md", 2, {}),
        ]


@pytest.mark.asyncio
async def test_retrieval_removes_invalid_citations_and_returns_server_sources() -> None:
    settings = Settings(embedding_dimensions=2, min_retrieval_score=0.2)
    service = RetrievalService(settings, FakeVectors(), FakeProvider())  # type: ignore[arg-type]

    result = await service.retrieve("What is the policy?", "default", 5)

    assert "[99]" not in result.answer
    assert [citation.chunk_id for citation in result.citations] == ["c2"]
    assert result.usage["total_tokens"] == 11


@pytest.mark.asyncio
async def test_retrieval_returns_no_context_without_chat_call() -> None:
    class EmptyVectors:
        async def search(self, vector: list[float], namespace: str, limit: int) -> list[RetrievedChunk]:
            return []

    service = RetrievalService(Settings(embedding_dimensions=2), EmptyVectors(), FakeProvider())  # type: ignore[arg-type]
    result = await service.retrieve("What is the policy?", "default", 5)
    assert result.answer == "I don't know based on the indexed documents."
    assert result.citations == []
