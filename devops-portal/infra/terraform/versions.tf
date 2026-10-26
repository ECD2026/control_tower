# Hosting for the DevOps portal itself (not the instances users deploy).
#
# State is local on purpose: this stack is applied once by an operator (see
# docs/demo-runbook.md). Day-to-day releases go through
# .github/workflows/portal-release.yml, which only talks to SSM.
terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.60"
    }
  }
}

provider "aws" {
  region = var.region

  # Every resource in this stack is tagged so it is easy to tell apart from
  # the instances that portal users deploy (Component=workload).
  default_tags {
    tags = {
      Project   = "devops-portal"
      Component = "portal-host"
      ManagedBy = "terraform"
      Stack     = "devops-portal/infra/terraform"
    }
  }
}
