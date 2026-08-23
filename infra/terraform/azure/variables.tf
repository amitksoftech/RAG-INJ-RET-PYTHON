variable "subscription_id" {
  type = string
}

variable "name" {
  type    = string
  default = "ragservice"
}

variable "location" {
  type    = string
  default = "centralindia"
}

variable "node_vm_size" {
  type    = string
  default = "Standard_D4s_v5"
}

variable "postgres_sku" {
  type    = string
  default = "GP_Standard_D2s_v3"
}
