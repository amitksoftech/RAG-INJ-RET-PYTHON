"""FastAPI application factory and process entry point."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Histogram
from starlette.middleware.base import BaseHTTPMiddleware

from rag_service.api.routes import operations, router
from rag_service.config import Settings, get_settings
from rag_service.container import ServiceContainer
from rag_service.errors import AppError
from rag_service.logging import configure_logging, log_extra, request_id_context

logger = logging.getLogger(__name__)
REQUEST_COUNT = Counter("rag_http_requests_total", "HTTP requests", ["method", "route", "status"])
REQUEST_SECONDS = Histogram("rag_http_request_duration_seconds", "HTTP request duration", ["method", "route"])


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        token = request_id_context.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            request_id_context.reset(token)
        response.headers["X-Request-ID"] = request_id
        route = request.scope.get("route")
        route_name = getattr(route, "path", "unmatched")
        REQUEST_COUNT.labels(request.method, route_name, str(response.status_code)).inc()
        REQUEST_SECONDS.labels(request.method, route_name).observe(time.perf_counter() - started)
        return response


def create_app(settings: Settings | None = None, container: ServiceContainer | None = None) -> FastAPI:
    runtime_settings = settings or get_settings()
    service_container = container or ServiceContainer(runtime_settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        configure_logging(runtime_settings.log_level)
        await service_container.startup()
        logger.info("application_started", extra=log_extra(environment=runtime_settings.app_env))
        try:
            yield
        finally:
            await service_container.shutdown()
            logger.info("application_stopped")

    app = FastAPI(
        title="RAG Service",
        version="0.1.0",
        docs_url="/docs" if runtime_settings.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if runtime_settings.docs_enabled else None,
        lifespan=lifespan,
    )
    app.state.container = service_container
    app.add_middleware(RequestContextMiddleware)
    if runtime_settings.allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(runtime_settings.allowed_origins),
            allow_credentials=False,
            allow_methods=["POST", "GET"],
            allow_headers=["Content-Type", "Idempotency-Key", "Last-Event-ID", "X-Request-ID"],
        )

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, error: AppError) -> JSONResponse:
        logger.warning("application_error", extra=log_extra(code=error.code, path=request.url.path))
        return JSONResponse(
            status_code=error.status_code,
            content={
                "error": {"code": error.code, "message": error.message, "details": error.details},
                "request_id": request.state.request_id,
            },
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, error: Exception) -> JSONResponse:
        logger.exception("unhandled_error", extra=log_extra(path=request.url.path))
        return JSONResponse(
            status_code=500,
            content={
                "error": {"code": "internal_error", "message": "Internal server error", "details": {}},
                "request_id": request.state.request_id,
            },
        )

    app.include_router(router)
    app.include_router(operations)
    return app


app = create_app()
