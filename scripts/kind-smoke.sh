#!/usr/bin/env sh
set -eu

cluster_name="rag-service-smoke"
port_forward_pid=""

cleanup() {
  if [ -n "$port_forward_pid" ]; then
    kill "$port_forward_pid" 2>/dev/null || true
  fi
  kind delete cluster --name "$cluster_name" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

docker build --tag rag-service:local .
kind create cluster --name "$cluster_name" --wait 2m
kind load docker-image rag-service:local --name "$cluster_name"
kubectl apply -k deploy/kustomize/overlays/kind
kubectl -n rag-system wait --for=condition=ready pod -l app.kubernetes.io/name=qdrant --timeout=180s
kubectl -n rag-system wait --for=condition=ready pod -l app.kubernetes.io/name=rag-api --timeout=180s
kubectl -n rag-system port-forward service/rag-api 18000:80 >/private/tmp/rag-kind-port-forward.log 2>&1 &
port_forward_pid=$!

attempt=0
until curl --fail --silent --show-error http://localhost:18000/healthz >/dev/null; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 20 ]; then
    kubectl -n rag-system get pods
    kubectl -n rag-system logs deployment/rag-api --all-containers=true --tail=100 || true
    exit 1
  fi
  sleep 2
done

printf '%s\n' "kind smoke test passed"
