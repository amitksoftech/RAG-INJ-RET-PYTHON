.PHONY: install lock lint format-check typecheck test check compose-up compose-down image kustomize terraform-validate

install:
	uv sync --all-groups

lock:
	uv lock

lint:
	uv run ruff check .

format-check:
	uv run ruff format --check .

typecheck:
	uv run mypy src

test:
	uv run pytest

check: lint format-check typecheck test

compose-up:
	docker compose up --build

compose-down:
	docker compose down --volumes --remove-orphans

image:
	docker build -t rag-service:local .

kustomize:
	kubectl kustomize deploy/kustomize/overlays/kind > /dev/null

terraform-validate:
	./scripts/validate-terraform.sh
