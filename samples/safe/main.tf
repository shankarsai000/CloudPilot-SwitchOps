# CloudPilot SwitchOps Demonstration Infrastructure: Hardened Safe Baseline
# Employs defense-in-depth, encrypted storage, least privilege, and cost-efficient sizing.

terraform {
  required_version = ">= 1.5.0"
}

provider "aws" {
  region = "us-east-1"
}

# Cost-effective, rightsized compute (t3.micro)
resource "aws_instance" "prod_web" {
  ami           = "ami-0c55b159cbfafe1f0"
  instance_type = "t3.micro"

  tags = {
    Name        = "prod-web-server"
    Environment = "production"
  }
}

# Cost-effective gp3 storage, encrypted with KMS
resource "aws_ebs_volume" "prod_storage" {
  availability_zone = "us-east-1a"
  size              = 20
  type              = "gp3"
  encrypted         = true

  tags = {
    Name        = "prod-storage"
    Environment = "production"
  }
}

# Hardened RDS instance: encrypted at rest, Multi-AZ high availability
resource "aws_db_instance" "prod_database" {
  allocated_storage   = 20
  engine              = "postgres"
  instance_class      = "db.t3.micro"
  username            = "app_admin"
  password            = "${var.db_secret_vault_reference}"
  storage_encrypted   = true
  multi_az            = true
  skip_final_snapshot = false

  tags = {
    Name        = "prod-postgres-db"
    Environment = "production"
  }
}

# Private S3 Bucket with public access block
resource "aws_s3_bucket" "prod_assets" {
  bucket = "cloudpilot-prod-assets-vault"
  acl    = "private"

  tags = {
    Name        = "prod-assets"
    Environment = "production"
  }
}

resource "aws_s3_bucket_public_access_block" "prod_assets_pab" {
  bucket                  = "cloudpilot-prod-assets-vault"
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Hardened Security Group: Ingress restricted strictly to HTTPS and internal VPN CIDR
resource "aws_security_group" "prod_ingress_sg" {
  name        = "prod-ingress-sg"
  description = "Production ingress security group"
  vpc_id      = "vpc-0a1b2c3d4e5f6g7h8"

  ingress {
    description = "HTTPS web traffic from internet"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "SSH administrative access from internal corporate bastion"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["10.0.1.0/24"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
