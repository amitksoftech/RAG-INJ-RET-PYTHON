output "cluster_name" { value = google_container_cluster.main.name }
output "region" { value = var.region }
output "bucket_name" { value = google_storage_bucket.sources.name }
output "postgres_connection_name" { value = google_sql_database_instance.postgres.connection_name }
output "redis_host" { value = google_redis_instance.redis.host }
output "workload_service_account" { value = google_service_account.workload.email }
output "secret_id" { value = google_secret_manager_secret.application.secret_id }
