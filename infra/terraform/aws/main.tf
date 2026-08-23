terraform {
  required_version = ">= 1.8.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region
  default_tags { tags = var.tags }
}

data "aws_availability_zones" "available" { state = "available" }

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name = "${var.name}-vpc"
  cidr = var.vpc_cidr
  azs  = slice(data.aws_availability_zones.available.names, 0, 3)
  private_subnets = [
    for index, _ in slice(data.aws_availability_zones.available.names, 0, 3) : cidrsubnet(var.vpc_cidr, 4, index)
  ]
  public_subnets = [
    for index, _ in slice(data.aws_availability_zones.available.names, 0, 3) : cidrsubnet(var.vpc_cidr, 4, index + 3)
  ]
  enable_nat_gateway  = true
  single_nat_gateway  = var.single_nat_gateway
  private_subnet_tags = { "kubernetes.io/role/internal-elb" = "1" }
  public_subnet_tags  = { "kubernetes.io/role/elb" = "1" }
}

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  cluster_name    = var.name
  cluster_version = var.kubernetes_version
  vpc_id          = module.vpc.vpc_id
  subnet_ids      = module.vpc.private_subnets
  enable_irsa     = true
  eks_managed_node_groups = {
    primary = {
      min_size       = 2
      max_size       = 6
      desired_size   = 2
      instance_types = [var.node_instance_type]
    }
  }
}

resource "aws_s3_bucket" "sources" { bucket_prefix = "${var.name}-sources-" }
resource "aws_s3_bucket_public_access_block" "sources" {
  bucket                  = aws_s3_bucket.sources.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_security_group" "data" {
  name_prefix = "${var.name}-data-"
  vpc_id      = module.vpc.vpc_id
  ingress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [var.vpc_cidr]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_db_subnet_group" "postgres" {
  name       = "${var.name}-postgres"
  subnet_ids = module.vpc.private_subnets
}

resource "aws_db_instance" "postgres" {
  identifier                  = "${var.name}-postgres"
  engine                      = "postgres"
  instance_class              = var.postgres_instance_class
  allocated_storage           = 50
  max_allocated_storage       = 200
  db_name                     = "rag"
  username                    = "ragadmin"
  manage_master_user_password = true
  db_subnet_group_name        = aws_db_subnet_group.postgres.name
  vpc_security_group_ids      = [aws_security_group.data.id]
  backup_retention_period     = 7
  deletion_protection         = true
  skip_final_snapshot         = false
  publicly_accessible         = false
}

resource "aws_elasticache_subnet_group" "redis" {
  name       = "${var.name}-redis"
  subnet_ids = module.vpc.private_subnets
}

resource "aws_elasticache_replication_group" "redis" {
  replication_group_id       = "${var.name}-redis"
  description                = "RAG ingestion Redis"
  node_type                  = var.redis_node_type
  port                       = 6379
  num_cache_clusters         = 2
  subnet_group_name          = aws_elasticache_subnet_group.redis.name
  security_group_ids         = [aws_security_group.data.id]
  automatic_failover_enabled = true
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
}

resource "aws_secretsmanager_secret" "application" { name = "rag-service/production" }

data "aws_iam_policy_document" "workload_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [module.eks.oidc_provider_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "${replace(module.eks.cluster_oidc_issuer_url, "https://", "")}:sub"
      values   = ["system:serviceaccount:rag-system:rag-service"]
    }
  }
}

resource "aws_iam_role" "workload" {
  name               = "${var.name}-rag-service"
  assume_role_policy = data.aws_iam_policy_document.workload_assume.json
}

data "aws_iam_policy_document" "workload" {
  statement {
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.sources.arn}/*"]
  }
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.application.arn]
  }
}

resource "aws_iam_role_policy" "workload" {
  role   = aws_iam_role.workload.id
  policy = data.aws_iam_policy_document.workload.json
}
