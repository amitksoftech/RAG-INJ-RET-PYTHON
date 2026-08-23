variable "project_id" {
  type = string
}

variable "name" {
  type    = string
  default = "rag-service"
}

variable "region" {
  type    = string
  default = "asia-south1"
}

variable "node_machine_type" {
  type    = string
  default = "e2-standard-4"
}

variable "postgres_tier" {
  type    = string
  default = "db-custom-2-7680"
}
