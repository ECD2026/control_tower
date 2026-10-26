variable "region" {
  description = "Region for the portal host"
  type        = string
  default     = "ap-south-1"
}

variable "name" {
  description = "Prefix for every resource name in this stack"
  type        = string
  default     = "devops-portal-host"
}

variable "instance_type" {
  description = "Portal host size. t3.small (2 vCPU / 2 GiB + swap) runs the whole stack."
  type        = string
  default     = "t3.small"
}

variable "root_volume_gb" {
  description = "Root EBS volume size (Docker images + Prometheus data)"
  type        = number
  default     = 30
}

variable "github_repo" {
  description = "owner/name of the repository the host deploys from"
  type        = string
  default     = "ECD2026/control_tower"
}

variable "git_ref" {
  description = "Branch or commit the host checks out on first boot"
  type        = string
  default     = "main"
}

variable "github_deploy_subjects" {
  description = <<-EOT
    OIDC `sub` claims allowed to assume the release role. portal-release.yml
    deploys from the `portal-production` GitHub environment, so the claim is
    repo:<owner>/<repo>:environment:portal-production. Protect that
    environment in GitHub settings to require approval for releases.
  EOT
  type        = list(string)
  default     = ["repo:ECD2026/control_tower:environment:portal-production"]
}

variable "ssm_prefix" {
  description = "SSM Parameter Store prefix holding the portal's configuration and secrets"
  type        = string
  default     = "/devops-portal"
}
