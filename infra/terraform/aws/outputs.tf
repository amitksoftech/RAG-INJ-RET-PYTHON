output "cluster_name" { value = module.eks.cluster_name }
output "region" { value = var.region }
output "bucket_name" { value = aws_s3_bucket.sources.bucket }
output "postgres_host" { value = aws_db_instance.postgres.address }
output "redis_host" { value = aws_elasticache_replication_group.redis.primary_endpoint_address }
output "workload_role_arn" { value = aws_iam_role.workload.arn }
output "secret_name" { value = aws_secretsmanager_secret.application.name }
