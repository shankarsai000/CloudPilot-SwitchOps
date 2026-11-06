variable "aws_region" {
  type        = string
  default     = "us-east-1"
  description = "Target deployment region"
}

variable "environment" {
  type        = string
  default     = "staging"
  description = "Target operational environment"
}
