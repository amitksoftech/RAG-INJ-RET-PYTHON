"""Pydantic models defining the public API contract."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class TextDocumentRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=512)
    content: str = Field(min_length=1)
    content_type: str = "text/plain"
    metadata: dict[str, Any] = Field(default_factory=dict)


class JsonIngestionRequest(BaseModel):
    documents: list[TextDocumentRequest] = Field(min_length=1, max_length=10)
    namespace: str = Field(default="default", min_length=1, max_length=128)


class RetrievalRequest(BaseModel):
    query: str = Field(min_length=1, max_length=10000)
    namespace: str = Field(default="default", min_length=1, max_length=128)
    top_k: int = Field(default=5, ge=1, le=20)

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must not be blank")
        return value.strip()


class CitationResponse(BaseModel):
    citation_id: int
    chunk_id: str
    document_id: str
    filename: str
    page: int | None
    score: float
    text_snippet: str
    metadata: dict[str, Any]


class RetrievalResponse(BaseModel):
    request_id: str
    answer: str
    citations: list[CitationResponse]
    usage: dict[str, Any]
