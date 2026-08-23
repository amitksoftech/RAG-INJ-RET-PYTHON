#!/usr/bin/env sh
set -eu

for directory in infra/terraform/aws infra/terraform/gcp infra/terraform/azure; do
  terraform -chdir="$directory" fmt -check -recursive
done
