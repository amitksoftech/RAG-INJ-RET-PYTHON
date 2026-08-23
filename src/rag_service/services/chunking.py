"""Deterministic heading/page-aware character chunking."""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterator
from typing import Any

from rag_service.domain import TextChunk

_BOUNDARY = re.compile(r"(?=^#{1,6}\s)|(?=^\[Page\s+\d+\])", re.MULTILINE)
_PAGE = re.compile(r"^\[Page\s+(\d+)\]", re.MULTILINE)


def _segments(text: str) -> Iterator[str]:
    starts = [match.start() for match in _BOUNDARY.finditer(text)]
    if not starts:
        yield text
        return
    if starts[0] != 0:
        starts.insert(0, 0)
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(text)
        segment = text[start:end].strip()
        if segment:
            yield segment


def chunk_text(
    *,
    text: str,
    document_id: str,
    namespace: str,
    base_metadata: dict[str, Any],
    size: int,
    overlap: int,
) -> list[TextChunk]:
    if overlap >= size:
        raise ValueError("chunk overlap must be smaller than chunk size")

    chunks: list[TextChunk] = []
    index = 0
    for segment in _segments(text):
        start = 0
        while start < len(segment):
            end = min(start + size, len(segment))
            if end < len(segment):
                newline = segment.rfind("\n", start, end)
                space = segment.rfind(" ", start, end)
                boundary = max(newline, space)
                if boundary > start + size // 2:
                    end = boundary
            piece = segment[start:end].strip()
            if piece:
                page_match = _PAGE.search(segment[:end])
                metadata = dict(base_metadata)
                if page_match:
                    metadata["page"] = int(page_match.group(1))
                chunk_id = str(uuid.uuid5(uuid.UUID(document_id), str(index)))
                chunks.append(
                    TextChunk(
                        chunk_id=chunk_id,
                        document_id=document_id,
                        namespace=namespace,
                        index=index,
                        text=piece,
                        metadata=metadata,
                    )
                )
                index += 1
            if end >= len(segment):
                break
            start = end - overlap
    return chunks
