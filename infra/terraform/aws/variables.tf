variable "name" {
  type    = string
  default = "rag-service"
}

variable "region" {
  type    = string
  default = "ap-south-1"
}

variable "vpc_cidr" {
  type    = string
  default = "10.40.0.0/16"
}

variable "kubernetes_version" {
  type    = string
  default = "1.31"
}

variable "node_instance_type" {
  type    = string
  default = "m6i.large"
}

variable "postgres_instance_class" {
  type    = string
  default = "db.t4g.medium"
}

variable "redis_node_type" {
  type    = string
  default = "cache.t4g.small"
}

variable "single_nat_gateway" {
  type    = bool
  default = false
}

variable "tags" {
  type    = map(string)
  default = { system = "rag-service" }
}
