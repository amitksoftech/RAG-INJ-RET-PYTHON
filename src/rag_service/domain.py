"""Domain models shared by application services and adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class IncomingDocument:
    filename: str
    content_type: str
    content: bytes
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    text: str
    page_count: int | None = None


@dataclass(frozen=True, slots=True)
class TextChunk:
    chunk_id: str
    document_id: str
    namespace: str
    index: int
    text: str
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class VectorPoint:
    chunk: TextChunk
    vector: list[float]


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    chunk_id: str
    document_id: str
    namespace: str
    text: str
    score: float
    filename: str
    page: int | None
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class IngestionEvent:
    kind: str
    job_id: str
    timestamp: datetime
    message: str
    document_id: str | None = None
    data: dict[str, Any] | None = None
