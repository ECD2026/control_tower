# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

**Aws_Organisational_Unit-Control-Tower** is an infrastructure-as-code (IaC) project for managing AWS organizational units and Control Tower configuration. The project uses Terraform as the primary infrastructure tool, with GitHub Actions for CI/CD automation. The DevOps portal (`devops-portal/`) is documented in `docs/architecture.md`.

**Current Status:** The DevOps portal is deployed on AWS; AWS Control Tower / OU management is not implemented yet.

## Key Architecture

- **DevOps portal** (`/devops-portal/`): React + FastAPI app. From its dashboard users deploy and manage EC2 instances with Terraform + Ansible, run by `.github/workflows/portal-deploy.yml` (see `docs/architecture.md`)
- **Portal host infra** (`devops-portal/infra/terraform/`): the EC2 host, Elastic IP, IAM roles and SSM config the portal itself runs on. State is in S3 (`devops-portal-tfstate-818651033439`, S3 lockfile)
- **Pipeline roles** (`devops-portal/infra/github-deploy-role.yaml`): CloudFormation stack `devops-portal-github-infra` with the state bucket and the OIDC roles `portal-infra.yml` assumes. Deployed by hand, outside the Terraform stack it serves
- **AWS**: account 818651033439, region `ap-south-1`. GitHub Actions authenticates through OIDC only; no AWS keys are stored in GitHub

## CI/CD (GitHub Actions)

| Workflow | Trigger | Does |
|---|---|---|
| `portal-infra.yml` | PR / push to `main` touching `devops-portal/infra/terraform/**`, manual | Plan on PRs (read-only role), plan + apply on `main` (environment `portal-infra`). Fails if a plan destroys or replaces a resource unless run by hand with `allow_replace` |
| `portal-release.yml` | PR / push to `main` touching `devops-portal/**`, manual | Tests (pytest, vite build, terraform validate), then redeploys the host over SSM (environment `portal-production`) |
| `portal-deploy.yml` | `workflow_dispatch` from the portal backend | Terraform + Ansible for one user deployment, with that user's sealed AWS keys |

Repository variables: `PORTAL_INFRA_ROLE_ARN`, `PORTAL_INFRA_PLAN_ROLE_ARN`, `PORTAL_HTTP_INGRESS_CIDRS`, `PORTAL_RELEASE_ROLE_ARN`, `PORTAL_AWS_REGION`, `PORTAL_HOST_INSTANCE_ID`. Secret: `PORTAL_WORKFLOW_KEY`. Setup: `docs/demo-runbook.md` Part A.

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

```bash
# Portal host stack (admin credentials; CI normally does this)
cd devops-portal/infra/terraform
terraform init
terraform fmt -recursive && terraform validate
terraform plan -out=tfplan
terraform apply tfplan

# Portal locally
cd devops-portal && docker compose up -d --build
cd devops-portal/backend && python -m pytest -q
```

## Security & Compliance Notes

- **Secrets**: Never commit `.tfvars`, `.env` or `.tfstate` files (gitignored). Portal secrets live in SSM Parameter Store under `/devops-portal/` and never enter Terraform state
- **Roles**: the infra apply role may only touch `devops-portal-host-*` IAM roles, the four non-secret `/devops-portal/*` parameters and EC2 in `ap-south-1`; the plan role is read-only; the release role may only run SSM commands on the host
- **PR Checklist**: All PRs must verify no hardcoded secrets and pass Terraform validation

## References

- Terraform AWS Provider: https://registry.terraform.io/providers/hashicorp/aws/latest/docs
- GitHub OIDC: Uses OpenID Connect for keyless AWS authentication
