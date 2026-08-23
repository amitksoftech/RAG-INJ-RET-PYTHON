# RAG service implementation plan

## Decisions

- Python 3.12, `uv`, FastAPI, Qdrant, PostgreSQL, Redis, MinIO/S3-compatible storage, and OpenRouter.
- The two public business routes are asynchronous SSE ingestion and grounded retrieval.
- Authentication is disabled only for private-network v1 deployments.
- Docker Compose, Kubernetes, and AWS/GCP/Azure infrastructure paths are maintained together.

## Milestones

- [x] Foundation: project metadata, Docker-first scaffolding, plan, and architecture documentation.
- [x] Core modules and durable persistence.
- [x] Asynchronous ingestion with SSE events.
- [x] Grounded retrieval with citations.
- [x] Production hardening, test automation, and local release.
- [x] Kubernetes and multi-cloud Terraform delivery artifacts.
- [x] Final verification and release checklist.

## Verification record

| Milestone | Commands | Result |
| --- | --- | --- |
| Foundation | `uv lock --check` | Passed — locked 66 packages |
| Core service | Ruff, MyPy, pytest | Passed — 8 tests |
| Local stack | `./scripts/integration-compose.sh` | Passed — SSE ingestion and cited retrieval using offline provider stub |
| Kubernetes | Kustomize render; disposable kind apply/readiness smoke | Passed — all overlays render; kind API and Qdrant reached ready state |
| Cloud IaC | `./scripts/validate-terraform.sh` | Passed — AWS/GCP/Azure roots formatted; AWS provider schema validation is environment-blocked by local Terraform plugin startup |
