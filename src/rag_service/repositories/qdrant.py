"""Qdrant vector-store adapter."""

from __future__ import annotations

from qdrant_client import AsyncQdrantClient, models

from rag_service.config import Settings
from rag_service.domain import RetrievedChunk, VectorPoint


class VectorStore:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = AsyncQdrantClient(url=settings.qdrant_url, check_compatibility=False)

    async def ensure_collection(self) -> None:
        try:
            collection = await self._client.get_collection(self._settings.qdrant_collection)
            vectors = collection.config.params.vectors
            if isinstance(vectors, models.VectorParams) and vectors.size != self._settings.embedding_dimensions:
                raise RuntimeError(
                    "Qdrant collection dimension does not match EMBEDDING_DIMENSIONS; reindex is required"
                )
        except Exception as error:
            if error.__class__.__name__ not in {"UnexpectedResponse", "ResponseHandlingException"}:
                raise
            await self._client.create_collection(
                collection_name=self._settings.qdrant_collection,
                vectors_config=models.VectorParams(
                    size=self._settings.embedding_dimensions,
                    distance=models.Distance.COSINE,
                ),
            )
            await self._client.create_payload_index(
                self._settings.qdrant_collection,
                field_name="namespace",
                field_schema=models.PayloadSchemaType.KEYWORD,
            )

    async def close(self) -> None:
        await self._client.close()

    async def upsert(self, points: list[VectorPoint]) -> None:
        if not points:
            return
        records = [
            models.PointStruct(
                id=point.chunk.chunk_id,
                vector=point.vector,
                payload={
                    "document_id": point.chunk.document_id,
                    "namespace": point.chunk.namespace,
                    "chunk_index": point.chunk.index,
                    "chunk_text": point.chunk.text,
                    "filename": point.chunk.metadata.get("filename", "unknown"),
                    "page": point.chunk.metadata.get("page"),
                    "metadata": point.chunk.metadata,
                },
            )
            for point in points
        ]
        await self._client.upsert(self._settings.qdrant_collection, points=records, wait=True)

    async def delete_document(self, document_id: str) -> None:
        await self._client.delete(
            self._settings.qdrant_collection,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[models.FieldCondition(key="document_id", match=models.MatchValue(value=document_id))]
                )
            ),
            wait=True,
        )

    async def search(self, vector: list[float], namespace: str, limit: int) -> list[RetrievedChunk]:
        response = await self._client.query_points(
            collection_name=self._settings.qdrant_collection,
            query=vector,
            query_filter=models.Filter(
                must=[models.FieldCondition(key="namespace", match=models.MatchValue(value=namespace))]
            ),
            limit=limit,
            with_payload=True,
        )
        chunks: list[RetrievedChunk] = []
        for point in response.points:
            payload = point.payload or {}
            page_raw = payload.get("page")
            chunks.append(
                RetrievedChunk(
                    chunk_id=str(point.id),
                    document_id=str(payload["document_id"]),
                    namespace=str(payload["namespace"]),
                    text=str(payload["chunk_text"]),
                    score=float(point.score),
                    filename=str(payload.get("filename", "unknown")),
                    page=int(page_raw) if page_raw is not None else None,
                    metadata=dict(payload.get("metadata", {})),
                )
            )
        return chunks
