terraform {
  required_version = ">= 1.8.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

resource "google_project_service" "services" {
  for_each           = toset(["container.googleapis.com", "sqladmin.googleapis.com", "redis.googleapis.com", "secretmanager.googleapis.com"])
  service            = each.value
  disable_on_destroy = false
}

resource "google_compute_network" "main" {
  name                    = "${var.name}-network"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "gke" {
  name          = "${var.name}-gke"
  region        = var.region
  network       = google_compute_network.main.id
  ip_cidr_range = "10.50.0.0/20"
  secondary_ip_range {
    range_name    = "pods"
    ip_cidr_range = "10.51.0.0/16"
  }
  secondary_ip_range {
    range_name    = "services"
    ip_cidr_range = "10.52.0.0/20"
  }
}

resource "google_container_cluster" "main" {
  name                     = var.name
  location                 = var.region
  network                  = google_compute_network.main.id
  subnetwork               = google_compute_subnetwork.gke.id
  remove_default_node_pool = true
  initial_node_count       = 1
  workload_identity_config { workload_pool = "${var.project_id}.svc.id.goog" }
  ip_allocation_policy {
    cluster_secondary_range_name  = "pods"
    services_secondary_range_name = "services"
  }
  depends_on = [google_project_service.services]
}

resource "google_container_node_pool" "primary" {
  name       = "primary"
  cluster    = google_container_cluster.main.name
  location   = var.region
  node_count = 2
  node_config {
    machine_type = var.node_machine_type
    oauth_scopes = ["https://www.googleapis.com/auth/cloud-platform"]
  }
}

resource "google_compute_global_address" "private_services" {
  name          = "${var.name}-private-services"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.main.id
}

resource "google_service_networking_connection" "private_services" {
  network                 = google_compute_network.main.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_services.name]
}

resource "google_sql_database_instance" "postgres" {
  name             = "${var.name}-postgres"
  database_version = "POSTGRES_16"
  region           = var.region
  settings {
    tier              = var.postgres_tier
    availability_type = "REGIONAL"
    backup_configuration { enabled = true }
    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.main.id
    }
  }
  deletion_protection = true
  depends_on          = [google_service_networking_connection.private_services]
}

resource "google_sql_database" "rag" {
  name     = "rag"
  instance = google_sql_database_instance.postgres.name
}

resource "google_redis_instance" "redis" {
  name               = "${var.name}-redis"
  tier               = "STANDARD_HA"
  memory_size_gb     = 1
  region             = var.region
  redis_version      = "REDIS_7_2"
  authorized_network = google_compute_network.main.id
  connect_mode       = "PRIVATE_SERVICE_ACCESS"
  depends_on         = [google_service_networking_connection.private_services]
}

resource "google_storage_bucket" "sources" {
  name                        = "${var.project_id}-${var.name}-sources"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  versioning { enabled = true }
}

resource "google_secret_manager_secret" "application" {
  secret_id = "rag-service-production"
  replication {
    auto {}
  }
}

resource "google_service_account" "workload" {
  account_id   = "rag-service"
  display_name = "RAG service workload identity"
}

resource "google_service_account_iam_member" "workload_identity" {
  service_account_id = google_service_account.workload.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[rag-system/rag-service]"
}

resource "google_project_iam_member" "storage" {
  project = var.project_id
  role    = "roles/storage.objectUser"
  member  = "serviceAccount:${google_service_account.workload.email}"
}

resource "google_secret_manager_secret_iam_member" "workload" {
  secret_id = google_secret_manager_secret.application.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.workload.email}"
}
