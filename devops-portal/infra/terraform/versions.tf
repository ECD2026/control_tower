# Hosting for the DevOps portal itself (not the instances users deploy).
#
# Planned and applied by .github/workflows/portal-infra.yml. State lives in
# the bucket created by ../github-deploy-role.yaml, locked with an S3 lockfile.
# Day-to-day releases go through .github/workflows/portal-release.yml, which
# only talks to SSM.
terraform {
  required_version = ">= 1.10"

  backend "s3" {
    bucket       = "devops-portal-tfstate-818651033439"
    key          = "portal-host/terraform.tfstate"
    region       = "ap-south-1"
    encrypt      = true
    use_lockfile = true
  }

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
