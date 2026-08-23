#!/usr/bin/env sh
set -eu

environment_file=".env"
if [ ! -f "$environment_file" ]; then
  environment_file=".env.example"
fi

export OPENROUTER_BASE_URL="http://openrouter-mock:8080/api/v1"
export OPENROUTER_API_KEY="compose-test-key"
export OPENROUTER_CHAT_MODEL="mock/chat"
export OPENROUTER_EMBEDDING_MODEL="mock/embed"

cleanup() {
  docker compose --env-file "$environment_file" --profile test down --volumes --remove-orphans
}
trap cleanup EXIT INT TERM

docker compose --env-file "$environment_file" --profile test up --build --detach

attempt=0
until curl --fail --silent --show-error http://localhost:8000/healthz >/dev/null; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 30 ]; then
    docker compose --env-file "$environment_file" --profile test logs
    exit 1
  fi
  sleep 2
done

sse_response="$(curl --fail --silent --show-error --no-buffer \
  --header "Content-Type: application/json" \
  --header "Idempotency-Key: compose-integration" \
  --data '{"documents":[{"filename":"integration.md","content":"# Integration\nThe policy requires approval."}]}' \
  http://localhost:8000/v1/ingestions)"
case "$sse_response" in
  *"event: completed"*) ;;
  *)
    docker compose --env-file "$environment_file" --profile test logs
    exit 1
    ;;
esac

retrieval_response="$(curl --fail --silent --show-error \
  --header "Content-Type: application/json" \
  --data '{"query":"What does the policy require?"}' \
  http://localhost:8000/v1/retrievals)"
case "$retrieval_response" in
  *"Mock grounded answer"*) ;;
  *)
    docker compose --env-file "$environment_file" --profile test logs
    exit 1
    ;;
esac

printf '%s\n' "Compose integration test passed"
