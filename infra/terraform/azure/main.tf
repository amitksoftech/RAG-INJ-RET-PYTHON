terraform {
  required_version = ">= 1.8.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}

provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
}

data "azurerm_client_config" "current" {}

resource "azurerm_resource_group" "main" {
  name     = "${var.name}-rg"
  location = var.location
}

resource "azurerm_virtual_network" "main" {
  name                = "${var.name}-vnet"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  address_space       = ["10.60.0.0/16"]
}

resource "azurerm_subnet" "aks" {
  name                 = "aks"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.60.0.0/20"]
}

resource "azurerm_subnet" "postgres" {
  name                 = "postgres"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.60.16.0/24"]
  delegation {
    name = "postgres"
    service_delegation {
      name    = "Microsoft.DBforPostgreSQL/flexibleServers"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

resource "azurerm_private_dns_zone" "postgres" {
  name                = "${var.name}.postgres.database.azure.com"
  resource_group_name = azurerm_resource_group.main.name
}

resource "azurerm_private_dns_zone_virtual_network_link" "postgres" {
  name                  = "postgres-vnet"
  private_dns_zone_name = azurerm_private_dns_zone.postgres.name
  virtual_network_id    = azurerm_virtual_network.main.id
  resource_group_name   = azurerm_resource_group.main.name
}

resource "azurerm_kubernetes_cluster" "main" {
  name                      = var.name
  location                  = azurerm_resource_group.main.location
  resource_group_name       = azurerm_resource_group.main.name
  dns_prefix                = var.name
  oidc_issuer_enabled       = true
  workload_identity_enabled = true
  default_node_pool {
    name           = "primary"
    vm_size        = var.node_vm_size
    node_count     = 2
    vnet_subnet_id = azurerm_subnet.aks.id
  }
  identity { type = "SystemAssigned" }
}

# Password authentication is disabled; assign the Entra administrator out-of-band before application use.
resource "azurerm_postgresql_flexible_server" "postgres" {
  name                         = "${var.name}-postgres"
  resource_group_name          = azurerm_resource_group.main.name
  location                     = azurerm_resource_group.main.location
  version                      = "16"
  delegated_subnet_id          = azurerm_subnet.postgres.id
  private_dns_zone_id          = azurerm_private_dns_zone.postgres.id
  storage_mb                   = 65536
  sku_name                     = var.postgres_sku
  backup_retention_days        = 7
  geo_redundant_backup_enabled = false
  authentication {
    active_directory_auth_enabled = true
    password_auth_enabled         = false
    tenant_id                     = data.azurerm_client_config.current.tenant_id
  }
  depends_on = [azurerm_private_dns_zone_virtual_network_link.postgres]
}

resource "azurerm_redis_cache" "redis" {
  name                = "${var.name}-redis"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  capacity            = 1
  family              = "C"
  sku_name            = "Standard"
  minimum_tls_version = "1.2"
}

resource "azurerm_storage_account" "sources" {
  name                          = replace("${var.name}sources", "-", "")
  resource_group_name           = azurerm_resource_group.main.name
  location                      = azurerm_resource_group.main.location
  account_tier                  = "Standard"
  account_replication_type      = "LRS"
  min_tls_version               = "TLS1_2"
  public_network_access_enabled = false
}

resource "azurerm_storage_container" "sources" {
  name                  = "rag-sources"
  storage_account_id    = azurerm_storage_account.sources.id
  container_access_type = "private"
}

resource "azurerm_key_vault" "main" {
  name                       = "${var.name}-kv"
  location                   = azurerm_resource_group.main.location
  resource_group_name        = azurerm_resource_group.main.name
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  purge_protection_enabled   = true
  soft_delete_retention_days = 30
  enable_rbac_authorization  = true
}

resource "azurerm_user_assigned_identity" "workload" {
  name                = "${var.name}-workload"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
}

resource "azurerm_federated_identity_credential" "workload" {
  name                = "rag-service"
  resource_group_name = azurerm_resource_group.main.name
  parent_id           = azurerm_user_assigned_identity.workload.id
  audience            = ["api://AzureADTokenExchange"]
  issuer              = azurerm_kubernetes_cluster.main.oidc_issuer_url
  subject             = "system:serviceaccount:rag-system:rag-service"
}

resource "azurerm_role_assignment" "key_vault" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.workload.principal_id
}

resource "azurerm_role_assignment" "storage" {
  scope                = azurerm_storage_account.sources.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_user_assigned_identity.workload.principal_id
}
