# CloudPilot SwitchOps Demonstration Infrastructure: Staging Environment
# Contains realistic cloud infrastructure with deliberate architectural trade-offs.

terraform {
  required_version = ">= 1.5.0"
}

provider "aws" {
  region = "us-east-1"
}

# Web Server EC2 instance - Oversized compute for staging (FIN-001)
resource "aws_instance" "staging_web" {
  ami           = "ami-0c55b159cbfafe1f0"
  instance_type = "m5.large"

  tags = {
    Name        = "staging-web-server"
    Environment = "staging"
  }
}

# Persistent data volume - Costly io2 provisioned IOPS (FIN-005) & unencrypted (SEC-008)
resource "aws_ebs_volume" "staging_db_storage" {
  availability_zone = "us-east-1a"
  size              = 100
  type              = "io2"
  encrypted         = false

  tags = {
    Name        = "staging-db-storage"
    Environment = "staging"
  }
}

# Staging Relational Database - Continuously active (FIN-003), unencrypted (SEC-009), Single-AZ (REL-003)
resource "aws_db_instance" "staging_postgres" {
  allocated_storage   = 50
  engine              = "postgres"
  instance_class      = "db.m5.large"
  username            = "staging_admin"
  password            = "hardcoded_admin_master_password_987"
  storage_encrypted   = false
  multi_az            = false
  skip_final_snapshot = true

  tags = {
    Name        = "staging-postgres-db"
    Environment = "staging"
  }
}

# Asset S3 Bucket - Missing public access block configuration (SEC-007)
resource "aws_s3_bucket" "staging_public_assets" {
  bucket = "cloudpilot-staging-public-assets"
  acl    = "public-read"

  tags = {
    Name        = "staging-public-assets"
    Environment = "staging"
  }
}

# Security Group - Unrestricted SSH and Database ingress from 0.0.0.0/0 (SEC-003)
resource "aws_security_group" "staging_perimeter_sg" {
  name        = "staging-perimeter-sg"
  description = "Staging application perimeter security group"
  vpc_id      = "vpc-0a1b2c3d4e5f6g7h8"

  ingress {
    description = "SSH administrative access from public internet"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "Direct PostgreSQL listener access from public internet"
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# Application Load Balancer
resource "aws_lb" "staging_ingress_alb" {
  name               = "staging-ingress-alb"
  internal           = false
  load_balancer_type = "application"
  subnets            = ["subnet-12345", "subnet-67890"]
}
