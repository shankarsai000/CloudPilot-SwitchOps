# Dynamic variables for staging environment

variable "environment" {
  type        = string
  default     = "staging"
  description = "Target deployment tier"
}

variable "staging_instance_type" {
  type        = string
  default     = "m5.large"
  description = "Compute instance sizing tier"
}
