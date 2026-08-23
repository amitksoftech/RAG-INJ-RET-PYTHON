"""OpenRouter client using its OpenAI-compatible HTTP endpoints."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from rag_service.config import Settings
from rag_service.errors import NotConfiguredError, ProviderError
from rag_service.logging import log_extra

logger = logging.getLogger(__name__)


class OpenRouterClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.openrouter_base_url.rstrip("/"),
            timeout=settings.provider_timeout_seconds,
        )

    async def close(self) -> None:
        await self._client.aclose()

    def _headers(self) -> dict[str, str]:
        if not self._settings.provider_is_configured():
            raise NotConfiguredError(
                "OpenRouter configuration is incomplete; set API key, chat model, and embedding model"
            )
        assert self._settings.openrouter_api_key is not None
        return {
            "Authorization": f"Bearer {self._settings.openrouter_api_key.get_secret_value()}",
            "Content-Type": "application/json",
        }

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        self._headers()
        assert self._settings.openrouter_embedding_model is not None
        payload = {
            "model": self._settings.openrouter_embedding_model,
            "input": texts,
            "dimensions": self._settings.embedding_dimensions,
        }
        response = await self._request("/embeddings", payload)
        data = response.get("data")
        if not isinstance(data, list) or len(data) != len(texts):
            raise ProviderError("OpenRouter returned an invalid embeddings response")
        vectors: list[list[float]] = []
        for item in data:
            vector = item.get("embedding") if isinstance(item, dict) else None
            if not isinstance(vector, list) or len(vector) != self._settings.embedding_dimensions:
                raise ProviderError("OpenRouter embedding dimension does not match configured value")
            vectors.append([float(value) for value in vector])
        return vectors

    async def answer(self, prompt: str) -> tuple[str, dict[str, Any]]:
        self._headers()
        assert self._settings.openrouter_chat_model is not None
        payload = {
            "model": self._settings.openrouter_chat_model,
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Answer only from the supplied source context. Cite claims with source labels "
                        "such as [1]. If the context is insufficient, say so plainly."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        }
        response = await self._request("/chat/completions", payload)
        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise ProviderError("OpenRouter returned an invalid chat response") from error
        if not isinstance(content, str) or not content.strip():
            raise ProviderError("OpenRouter returned an empty answer")
        usage = response.get("usage")
        return content.strip(), usage if isinstance(usage, dict) else {}

    async def _request(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                response = await self._client.post(path, headers=self._headers(), json=payload)
                if response.status_code in {429, 500, 502, 503, 504} and attempt == 0:
                    await asyncio.sleep(0.25)
                    continue
                response.raise_for_status()
                result = response.json()
                if not isinstance(result, dict):
                    raise ProviderError("OpenRouter returned a non-object response")
                return result
            except (httpx.HTTPError, ValueError, ProviderError) as error:
                last_error = error
                logger.warning("openrouter_request_failed", extra=log_extra(path=path, attempt=attempt + 1))
                if attempt == 0:
                    await asyncio.sleep(0.25)
        raise ProviderError("OpenRouter request failed after retry") from last_error
