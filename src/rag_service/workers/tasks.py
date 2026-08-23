"""Dramatiq tasks. Each task builds an isolated service container."""

from __future__ import annotations

import asyncio

import dramatiq
from dramatiq.brokers.redis import RedisBroker

from rag_service.config import get_settings
from rag_service.container import ServiceContainer

settings = get_settings()
dramatiq.set_broker(RedisBroker(url=settings.redis_url))  # type: ignore[no-untyped-call]


@dramatiq.actor(max_retries=5, min_backoff=1000, max_backoff=60000, time_limit=900000)
def process_ingestion_job(job_id: str) -> None:
    asyncio.run(_process(job_id))


async def _process(job_id: str) -> None:
    container = ServiceContainer(get_settings())
    await container.startup()
    try:
        await container.ingestion.process(job_id)
    finally:
        await container.shutdown()
