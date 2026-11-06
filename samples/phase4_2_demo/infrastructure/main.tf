# CloudPilot SwitchOps Demonstration Scenario: Staging Compute Infrastructure
# Synthetic demonstration scenario for Phase 4.2 End-to-End Human-Approved Execution

terraform {
  required_version = ">= 1.5.0"
}

provider "aws" {
  region = var.aws_region
}

# Web Server EC2 instance - Oversized compute allocation (FIN-001)
# Recommended bounded optimization: downscale from m5.large to t3.small
resource "aws_instance" "demo_web_service" {
  ami           = "ami-0c55b159cbfafe1f0"
  instance_type = "m5.large"

  tags = {
    Name        = "demo-web-service"
    Environment = var.environment
    ManagedBy   = "CloudPilot-SwitchOps"
  }
}
