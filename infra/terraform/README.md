# Multi-cloud infrastructure

Each directory is an independent Terraform root for a private Kubernetes deployment.

- AWS: EKS, RDS PostgreSQL, ElastiCache, S3, Secrets Manager.
- GCP: GKE, Cloud SQL, Memorystore, Cloud Storage, Secret Manager.
- Azure: AKS, PostgreSQL Flexible Server, Azure Cache for Redis, Blob Storage, Key Vault.

Before `apply`, configure an encrypted remote state backend with restricted access. Terraform creates secret containers only; operators populate `DATABASE_URL`, `REDIS_URL`, object-storage credentials, and OpenRouter configuration directly in the cloud secret manager. Do not pass those values through `.tfvars` or commit them.

Use `terraform init`, `terraform plan`, then a deliberately approved `terraform apply` in one cloud directory. Apply the matching Kustomize overlay after replacing the service-account workload identity placeholder with Terraform output.
