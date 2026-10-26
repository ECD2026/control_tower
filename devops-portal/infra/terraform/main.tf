# ============================================================
# DevOps portal host
#
#   Browser --HTTPS--> CloudFront --HTTP--> EC2 (nginx :80) --> containers
#
# - The EC2 security group only admits CloudFront's origin-facing IP ranges,
#   so the plain-HTTP origin is never reachable directly from the internet.
# - No SSH: administration is via SSM Session Manager / Run Command.
# - Secrets live in SSM Parameter Store (SecureString) under var.ssm_prefix,
#   written by infra/scripts/bootstrap-secrets.sh, read at deploy time.
# ============================================================

data "aws_caller_identity" "current" {}

data "aws_vpc" "default" {
  default = true
}

data "aws_ssm_parameter" "al2023_ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

data "aws_ec2_managed_prefix_list" "cloudfront" {
  name = "com.amazonaws.global.cloudfront.origin-facing"
}

locals {
  ssm_arn_prefix = "arn:aws:ssm:${var.region}:${data.aws_caller_identity.current.account_id}:parameter${var.ssm_prefix}"
}

# ---------- Security group ----------

resource "aws_security_group" "host" {
  name        = "${var.name}-sg"
  description = "DevOps portal host: HTTP from CloudFront only"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description     = "HTTP from CloudFront origin-facing ranges"
    from_port       = 80
    to_port         = 80
    protocol        = "tcp"
    prefix_list_ids = [data.aws_ec2_managed_prefix_list.cloudfront.id]
  }

  egress {
    description = "Outbound: AWS APIs, GitHub, package mirrors, node_exporter scrapes"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.name}-sg"
  }
}

# ---------- IAM: instance role ----------

resource "aws_iam_role" "host" {
  name        = "${var.name}-role"
  description = "DevOps portal host: SSM management + reading its own parameters"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ssm_core" {
  role       = aws_iam_role.host.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# The host itself has no EC2/CloudWatch rights: all AWS calls made for portal
# users use the credentials those users uploaded.
resource "aws_iam_role_policy" "read_config" {
  name = "${var.name}-read-config"
  role = aws_iam_role.host.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ReadPortalParameters"
        Effect   = "Allow"
        Action   = ["ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath"]
        Resource = [local.ssm_arn_prefix, "${local.ssm_arn_prefix}/*"]
      },
      {
        Sid      = "DecryptSecureStrings"
        Effect   = "Allow"
        Action   = "kms:Decrypt"
        Resource = "*"
        Condition = {
          StringEquals = { "kms:ViaService" = "ssm.${var.region}.amazonaws.com" }
        }
      },
    ]
  })
}

resource "aws_iam_instance_profile" "host" {
  name = "${var.name}-profile"
  role = aws_iam_role.host.name
}

# ---------- EC2 ----------

resource "aws_instance" "host" {
  ami                    = data.aws_ssm_parameter.al2023_ami.value
  instance_type          = var.instance_type
  iam_instance_profile   = aws_iam_instance_profile.host.name
  vpc_security_group_ids = [aws_security_group.host.id]

  metadata_options {
    http_tokens                 = "required" # IMDSv2 only
    http_put_response_hop_limit = 2          # reachable from containers
  }

  root_block_device {
    volume_size = var.root_volume_gb
    volume_type = "gp3"
    encrypted   = true
    tags = {
      Name = "${var.name}-root"
    }
  }

  user_data = templatefile("${path.module}/user_data.sh.tftpl", {
    region      = var.region
    ssm_prefix  = var.ssm_prefix
    github_repo = var.github_repo
    git_ref     = var.git_ref
    host_deploy = file("${path.module}/../scripts/host-deploy.sh")
  })
  user_data_replace_on_change = false

  # A new AMI release should not replace the running host.
  lifecycle {
    ignore_changes = [ami, user_data]
  }

  tags = {
    Name = var.name
  }
}

resource "aws_eip" "host" {
  domain   = "vpc"
  instance = aws_instance.host.id

  tags = {
    Name = "${var.name}-eip"
  }
}

# ---------- CloudFront (HTTPS front door) ----------

data "aws_cloudfront_cache_policy" "disabled" {
  name = "Managed-CachingDisabled"
}

data "aws_cloudfront_origin_request_policy" "all_viewer" {
  name = "Managed-AllViewer"
}

resource "aws_cloudfront_distribution" "portal" {
  enabled         = true
  comment         = "${var.name} - DevOps portal (HTTPS front door)"
  price_class     = "PriceClass_200"
  is_ipv6_enabled = true

  origin {
    origin_id   = "${var.name}-origin"
    domain_name = aws_eip.host.public_dns

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]
      # SSE log streams send a keepalive every 15s; leave headroom.
      origin_read_timeout      = 60
      origin_keepalive_timeout = 60
    }
  }

  # Nothing is cached: the SPA is tiny and everything else is dynamic.
  default_cache_behavior {
    target_origin_id         = "${var.name}-origin"
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods           = ["GET", "HEAD"]
    cache_policy_id          = data.aws_cloudfront_cache_policy.disabled.id
    origin_request_policy_id = data.aws_cloudfront_origin_request_policy.all_viewer.id
    compress                 = true
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = {
    Name = "${var.name}-cdn"
  }
}

# ---------- Non-secret configuration for the host ----------
# Secrets (keys, tokens) are written by infra/scripts/bootstrap-secrets.sh so
# they never land in Terraform state.

resource "aws_ssm_parameter" "public_host" {
  name        = "${var.ssm_prefix}/public_host"
  description = "Public hostname of the portal (CloudFront)"
  type        = "String"
  value       = aws_cloudfront_distribution.portal.domain_name
}

resource "aws_ssm_parameter" "monitoring_sg" {
  name        = "${var.ssm_prefix}/monitoring_sg_id"
  description = "Portal host SG; deployed instances open node_exporter to it"
  type        = "String"
  value       = aws_security_group.host.id
}

resource "aws_ssm_parameter" "monitoring_sg_region" {
  name        = "${var.ssm_prefix}/monitoring_sg_region"
  description = "Region of monitoring_sg_id (SG references are regional)"
  type        = "String"
  value       = var.region
}

resource "aws_ssm_parameter" "github_repo" {
  name        = "${var.ssm_prefix}/github_repo"
  description = "Repository whose portal-deploy.yml the portal dispatches"
  type        = "String"
  value       = var.github_repo
}
