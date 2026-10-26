# ============================================================
# Release role for .github/workflows/portal-release.yml
#
# GitHub Actions assumes this role through OIDC (no stored AWS keys) and may
# only run SSM commands on the portal host. The account's GitHub OIDC
# provider already exists, so it is looked up rather than created.
# ============================================================

data "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"
}

resource "aws_iam_role" "github_release" {
  name        = "${var.name}-github-release"
  description = "Assumed by portal-release.yml to redeploy the portal host over SSM"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = data.aws_iam_openid_connect_provider.github.arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
        }
        StringLike = {
          "token.actions.githubusercontent.com:sub" = var.github_deploy_subjects
        }
      }
    }]
  })
}

resource "aws_iam_role_policy" "github_release" {
  name = "${var.name}-github-release"
  role = aws_iam_role.github_release.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "RunDeployScriptOnPortalHostOnly"
        Effect = "Allow"
        Action = "ssm:SendCommand"
        Resource = [
          aws_instance.host.arn,
          "arn:aws:ssm:${var.region}::document/AWS-RunShellScript",
        ]
      },
      {
        Sid      = "ReadCommandResults"
        Effect   = "Allow"
        Action   = ["ssm:GetCommandInvocation", "ssm:ListCommandInvocations"]
        Resource = "*"
      },
    ]
  })
}
