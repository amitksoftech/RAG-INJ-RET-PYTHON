# RAG Service

A Docker-first Python RAG service with exactly two public business endpoints:

- `POST /v1/ingestions` queues documents and streams server-sent progress events.
- `POST /v1/retrievals` returns an OpenRouter-generated answer grounded in Qdrant results.

## Quick start

1. Copy `.env.example` to `.env` and set the three `OPENROUTER_*` values.
2. Start the stack with `docker compose up --build`.
3. Follow the streamed ingestion response with `curl -N` and then call retrieval.

Run local checks with `make check`. The implementation roadmap is in `plan.md`.

```sh
curl --no-buffer \
  --header 'Content-Type: application/json' \
  --header 'Idempotency-Key: handbook-v1' \
  --data '{"documents":[{"filename":"handbook.md","content":"Travel requires manager approval."}]}' \
  http://localhost:8000/v1/ingestions

curl --header 'Content-Type: application/json' \
  --data '{"query":"What does travel require?","namespace":"default","top_k":5}' \
  http://localhost:8000/v1/retrievals
```

The ingestion route supports `application/json` direct text and `multipart/form-data` with a repeated `files` field. Supported files are PDF, DOCX, TXT, and Markdown. The SSE stream can be resumed by resending the same `Idempotency-Key` and `Last-Event-ID`.

## Verification and deployment

- `make check` runs Ruff, MyPy, and unit/contract tests.
- `./scripts/integration-compose.sh` runs offline containerized ingestion and retrieval through a deterministic OpenRouter-compatible test service.
- `./scripts/kind-smoke.sh` builds a disposable kind cluster, applies the kind overlay, checks API health, then removes it.
- `make terraform-validate` checks formatting for all cloud roots. Run provider initialization and plans only from an approved cloud environment with an encrypted remote state backend.

Read the versioned [architecture history](docs/architecture/README.md) before deployment. Cloud deployment runbooks and secret requirements are in [operations.md](docs/operations.md).

Authentication is deliberately disabled for v1. Do not expose this service publicly until an authentication and tenant-isolation layer is enabled.
