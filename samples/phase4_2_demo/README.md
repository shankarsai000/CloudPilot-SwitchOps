# Phase 4.2 Demonstration Scenario: Bounded Infrastructure Optimization

This directory contains a dedicated, synthetic infrastructure scenario for testing and demonstrating the **Phase 4.2 End-to-End Human-Approved Execution Workflow**.

## Architecture & Resources

- `infrastructure/main.tf`: Terraform HCL definition containing an oversized compute resource (`aws_instance.demo_web_service` set to `t3.large`).
- `infrastructure/variables.tf`: Configuration variables for region and environment.
- `docker-compose.yml`: Multi-service application with Docker Compose configuration.

## Safety & Isolation Guarantee

This scenario is completely synthetic and isolated from live cloud accounts:
1. **Zero Cloud Provider Write APIs:** No AWS, GCP, or Azure credentials are used or required.
2. **Local Sandbox Execution:** When an optimization proposal is approved, mutations are executed within a sandboxed temporary directory (`.cloudpilot/workspaces/exec-*`).
3. **Immutability of Baseline:** Files in this directory remain 100% read-only and unmodified during demonstration execution.
