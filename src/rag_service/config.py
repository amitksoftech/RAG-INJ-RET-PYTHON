"""Typed application configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings. Secrets are intentionally never logged."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "rag-service"
    app_env: Literal["development", "test", "staging", "production"] = "development"
    log_level: str = "INFO"
    api_docs_enabled: bool = True
    api_prefix: str = "/v1"

    database_url: str = "postgresql+asyncpg://rag:rag@localhost:5432/rag"
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "rag_chunks"

    s3_endpoint_url: str | None = "http://localhost:9000"
    s3_bucket: str = "rag-sources"
    s3_access_key: str = "minioadmin"
    s3_secret_key: SecretStr = SecretStr("minioadmin")
    s3_region: str = "us-east-1"

    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_api_key: SecretStr | None = None
    openrouter_chat_model: str | None = None
    openrouter_embedding_model: str | None = None
    embedding_dimensions: int = Field(default=1536, ge=1)

    max_upload_bytes: int = Field(default=25 * 1024 * 1024, ge=1)
    max_documents_per_job: int = Field(default=10, ge=1)
    chunk_size_chars: int = Field(default=1200, ge=100)
    chunk_overlap_chars: int = Field(default=200, ge=0)
    embedding_batch_size: int = Field(default=64, ge=1)
    event_retention_seconds: int = Field(default=86400, ge=60)
    min_retrieval_score: float = Field(default=0.2, ge=-1.0, le=1.0)
    max_context_characters: int = Field(default=12000, ge=1000)
    provider_timeout_seconds: float = Field(default=60.0, gt=0)
    allowed_origins: tuple[str, ...] = ()

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> tuple[str, ...]:
        if value is None or value == "":
            return ()
        if isinstance(value, str):
            return tuple(origin.strip() for origin in value.split(",") if origin.strip())
        if isinstance(value, (list, tuple)):
            return tuple(str(origin) for origin in value)
        raise ValueError("ALLOWED_ORIGINS must be a comma-separated string")

    @property
    def docs_enabled(self) -> bool:
        return self.api_docs_enabled and self.app_env != "production"

    def provider_is_configured(self) -> bool:
        return bool(self.openrouter_api_key and self.openrouter_chat_model and self.openrouter_embedding_model)


@lru_cache
def get_settings() -> Settings:
    return Settings()
