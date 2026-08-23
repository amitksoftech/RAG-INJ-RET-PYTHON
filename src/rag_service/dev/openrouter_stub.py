"""Deterministic OpenRouter-compatible stub for offline Compose integration tests."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI

app = FastAPI(docs_url=None, redoc_url=None)


@app.post("/api/v1/embeddings")
async def embeddings(payload: dict[str, Any]) -> dict[str, Any]:
    values = payload.get("input", [])
    inputs = [values] if isinstance(values, str) else values
    dimensions = int(payload.get("dimensions", 1536))
    return {
        "data": [
            {"object": "embedding", "index": index, "embedding": [0.01] * dimensions} for index, _ in enumerate(inputs)
        ],
        "model": payload.get("model", "mock/embed"),
        "object": "list",
        "usage": {"prompt_tokens": len(inputs), "total_tokens": len(inputs)},
    }


@app.post("/api/v1/chat/completions")
async def chat_completions(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "mock-chat-completion",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "Mock grounded answer [1]."}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 5, "total_tokens": 6},
        "model": payload.get("model", "mock/chat"),
    }
