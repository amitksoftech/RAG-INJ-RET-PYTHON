# Operations runbook

## Configuration and secrets

Set `OPENROUTER_API_KEY`, `OPENROUTER_CHAT_MODEL`, `OPENROUTER_EMBEDDING_MODEL`, and `EMBEDDING_DIMENSIONS` before live ingestion or retrieval. The embedding dimension must match the current Qdrant collection; changing it requires a new collection and full reindex.

Store production settings in the provider secret manager. The Kubernetes overlays expect a `rag-service-secrets` secret created by External Secrets Operator. Never place API keys, database passwords, or object-storage credentials in Git, manifests, or Terraform variables.

## Health and incidents

- `/healthz` verifies process liveness.
- `/readyz` verifies PostgreSQL, Redis, MinIO/S3, and Qdrant connectivity.
- `/metrics` is for private Prometheus scraping only.
- JSON logs include request and job IDs. They do not log raw documents or secrets.

If an ingestion stream reports `failed`, retain its job ID, inspect the structured worker logs, and use the same idempotency key to inspect/replay retained progress. A worker retry uses deterministic point IDs and will not duplicate vectors.

## Backup and recovery

- Enable PostgreSQL point-in-time recovery and test database restore procedures.
- Back up Qdrant persistent volumes/snapshots and retain the associated raw source bucket; source data enables reindexing after vector loss.
- Enable bucket versioning, encryption, and lifecycle retention appropriate to document policy.
- Run Alembic migrations before rolling API or worker images. Roll back application images only after confirming migration compatibility.

## Public exposure gate

This version intentionally has no authentication. Keep the API behind private ingress/security groups. Before public exposure, add API-key authentication, bind namespaces to authenticated tenants, set ingress TLS/rate limits, and review OpenRouter data-handling requirements.
