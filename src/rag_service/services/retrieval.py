"""Grounded retrieval and server-validated source citations."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from rag_service.config import Settings
from rag_service.domain import RetrievedChunk
from rag_service.providers.openrouter import OpenRouterClient
from rag_service.repositories.qdrant import VectorStore

_CITATION = re.compile(r"\[(\d+)]")


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    answer: str
    citations: list[RetrievedChunk]
    usage: dict[str, Any]


class RetrievalService:
    def __init__(self, settings: Settings, vectors: VectorStore, provider: OpenRouterClient) -> None:
        self._settings = settings
        self._vectors = vectors
        self._provider = provider

    async def retrieve(self, query: str, namespace: str, top_k: int) -> RetrievalResult:
        vector = (await self._provider.embed([query]))[0]
        chunks = await self._vectors.search(vector, namespace, top_k)
        chunks = [chunk for chunk in chunks if chunk.score >= self._settings.min_retrieval_score]
        if not chunks:
            return RetrievalResult(answer="I don't know based on the indexed documents.", citations=[], usage={})
        context_chunks = self._limit_context(chunks)
        prompt = self._build_prompt(query, context_chunks)
        answer, usage = await self._provider.answer(prompt)
        answer, cited_indexes = self._validated_citations(answer, len(context_chunks))
        citations = [context_chunks[index - 1] for index in cited_indexes]
        if not citations:
            citations = [context_chunks[0]]
        return RetrievalResult(answer=answer, citations=citations, usage=usage)

    def _limit_context(self, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        selected: list[RetrievedChunk] = []
        total = 0
        for chunk in chunks:
            if selected and total + len(chunk.text) > self._settings.max_context_characters:
                break
            selected.append(chunk)
            total += len(chunk.text)
        return selected

    @staticmethod
    def _build_prompt(query: str, chunks: list[RetrievedChunk]) -> str:
        sources = "\n\n".join(f"[{index}] {chunk.text}" for index, chunk in enumerate(chunks, start=1))
        return f"Question:\n{query}\n\nSource context:\n{sources}\n\nAnswer with source labels."

    @staticmethod
    def _validated_citations(answer: str, source_count: int) -> tuple[str, list[int]]:
        cited: list[int] = []

        def replace(match: re.Match[str]) -> str:
            index = int(match.group(1))
            if 1 <= index <= source_count:
                if index not in cited:
                    cited.append(index)
                return match.group(0)
            return ""

        return _CITATION.sub(replace, answer).strip(), cited
