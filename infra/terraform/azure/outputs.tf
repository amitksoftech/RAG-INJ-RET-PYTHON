output "cluster_name" { value = azurerm_kubernetes_cluster.main.name }
output "resource_group" { value = azurerm_resource_group.main.name }
output "storage_account" { value = azurerm_storage_account.sources.name }
output "postgres_host" { value = azurerm_postgresql_flexible_server.postgres.fqdn }
output "redis_host" { value = azurerm_redis_cache.redis.hostname }
output "workload_client_id" { value = azurerm_user_assigned_identity.workload.client_id }
output "key_vault_uri" { value = azurerm_key_vault.main.vault_uri }
