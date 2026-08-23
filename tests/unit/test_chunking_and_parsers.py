from __future__ import annotations

import uuid

import pytest

from rag_service.errors import UnsupportedDocumentError
from rag_service.services.chunking import chunk_text
from rag_service.services.parsers import normalized_content_type, parse_document


def test_chunking_is_deterministic_and_keeps_page_metadata() -> None:
    document_id = str(uuid.uuid4())
    text = "[Page 1]\n" + "alpha " * 60 + "\n[Page 2]\n" + "beta " * 60
    first = chunk_text(
        text=text,
        document_id=document_id,
        namespace="default",
        base_metadata={"filename": "notes.pdf"},
        size=120,
        overlap=20,
    )
    second = chunk_text(
        text=text,
        document_id=document_id,
        namespace="default",
        base_metadata={"filename": "notes.pdf"},
        size=120,
        overlap=20,
    )

    assert [chunk.chunk_id for chunk in first] == [chunk.chunk_id for chunk in second]
    assert first[0].metadata["page"] == 1
    assert any(chunk.metadata.get("page") == 2 for chunk in first)


def test_text_parser_and_extension_inference() -> None:
    assert normalized_content_type("notes.md", "application/octet-stream") == "text/markdown"
    parsed = parse_document("notes.txt", "text/plain", b"hello\nworld")
    assert parsed.text == "hello\nworld"


def test_scanned_pdf_is_explicitly_unsupported(monkeypatch: pytest.MonkeyPatch) -> None:
    class EmptyPage:
        def extract_text(self) -> None:
            return None

    class EmptyReader:
        pages = [EmptyPage()]

    monkeypatch.setattr("rag_service.services.parsers.PdfReader", lambda _: EmptyReader())
    with pytest.raises(UnsupportedDocumentError, match="scanned PDF"):
        parse_document("scan.pdf", "application/pdf", b"%PDF-1.4\n")
