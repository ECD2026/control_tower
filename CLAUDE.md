# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Aws_Organisational_Unit-Control-Tower** is an infrastructure-as-code (IaC) project for managing AWS organizational units and Control Tower configuration. The project uses Terraform as the primary infrastructure tool, with GitHub Actions for CI/CD automation. Docker and Jenkins support are scaffolded for future use.

**Current Status:** Sprint-1 focused on repository setup. Actual infrastructure code implementation is in progress.

## Key Architecture

- **Terraform** (`/terraform/`): Infrastructure definitions for AWS Control Tower and organizational units
  - `main.tf`: Primary Terraform configuration
  - `modules/`: Reusable Terraform modules
  - `environments/`: Environment-specific configurations (likely dev/staging/prod)
- **CI/CD**: GitHub Actions workflow (`.github/workflows/deploy.yml`) automatically deploys Terraform changes on push to `main`
- **AWS Authentication**: GitHub Actions uses OpenID Connect (OIDC) for AWS credential assume role (arn:aws:iam::053020126202:role/GitHubTerraformRole), region: ap-south-1
- **Docker** (`/docker/`): Container support (currently scaffolded)
- **Jenkins** (`/jenkins/`): Jenkins pipeline support (currently scaffolded)

## Git Workflow & Branching Strategy

- **main** → Production branch (auto-deploys via GitHub Actions)
- **develop** → Integration branch (for testing before production)
- **feature/\*** → Developer feature branches
- **Rules:**
  - No direct push to `main` or `develop`
  - All changes must go through Pull Requests
  - Minimum 1 approval required before merge
  - PR template enforces: code testing, no hardcoded secrets, Terraform validation

## Common Commands

### Terraform Operations

```bash
# Validate Terraform syntax
terraform validate

# Format Terraform code (standardize style)
terraform fmt -recursive

# Plan infrastructure changes (dry-run)
terraform plan -out=tfplan

# Apply infrastructure changes
terraform apply tfplan

# Destroy infrastructure (use with caution)
terraform destroy
```

### Working with Environments

The `terraform/environments/` directory should contain environment-specific variables. When running Terraform:

```bash
terraform plan -var-file=environments/<environment>.tfvars -out=tfplan
terraform apply -var-file=environments/<environment>.tfvars tfplan
```

### GitHub Workflow

Changes to `main` branch automatically trigger the GitHub Actions deployment workflow. The workflow:
1. Checks out code
2. Configures AWS credentials via OIDC
3. Runs Terraform (validate, plan, apply) in `ap-south-1` region

## Security & Compliance Notes

- **Secrets**: Never commit `.tfvars` or `.tfvars.json` files (gitignored) — these contain sensitive data
- **Terraform state**: `.tfstate` files are ignored locally but should be stored remotely (likely AWS S3 with locking)
- **AWS Role**: The GitHub Actions role should only have minimum required permissions for your Control Tower setup
- **PR Checklist**: All PRs must verify no hardcoded secrets and pass Terraform validation

## File Structure Notes

- Empty placeholder files currently exist in `/docker/`, `/jenkins/`, and `/terraform/modules/` and `/terraform/environments/` — populate these as implementation progresses
- `.terraform/` directories and lock files are gitignored (created locally during runs)
- `.github/.github/` appears to be a duplicate directory structure (may warrant cleanup)

## References

- AWS Control Tower Docs: Configure organizational units, security controls, and landing zones
- Terraform AWS Provider: https://registry.terraform.io/providers/hashicorp/aws/latest/docs
- GitHub OIDC: Uses OpenID Connect for keyless AWS authentication
