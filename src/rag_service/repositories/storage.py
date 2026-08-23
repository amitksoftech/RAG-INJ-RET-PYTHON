"""S3-compatible raw-document storage adapter."""

from __future__ import annotations

import asyncio
from typing import cast

import boto3  # type: ignore[import-untyped]
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from rag_service.config import Settings


class ObjectStorage:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key.get_secret_value(),
            region_name=settings.s3_region,
        )

    async def ensure_bucket(self) -> None:
        def ensure() -> None:
            try:
                self._client.head_bucket(Bucket=self._settings.s3_bucket)
            except ClientError as error:
                status = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
                if status != 404:
                    raise
                self._client.create_bucket(Bucket=self._settings.s3_bucket)

        await asyncio.to_thread(ensure)

    async def put(self, key: str, content: bytes, content_type: str) -> None:
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self._settings.s3_bucket,
            Key=key,
            Body=content,
            ContentType=content_type,
        )

    async def get(self, key: str) -> bytes:
        def fetch() -> bytes:
            response = self._client.get_object(Bucket=self._settings.s3_bucket, Key=key)
            return cast(bytes, response["Body"].read())

        return await asyncio.to_thread(fetch)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._client.delete_object, Bucket=self._settings.s3_bucket, Key=key)
