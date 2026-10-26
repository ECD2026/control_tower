output "portal_url" {
  description = "Open this in a browser"
  value       = "https://${aws_cloudfront_distribution.portal.domain_name}"
}

output "instance_id" {
  description = "Portal host - connect with `aws ssm start-session --target <id>`"
  value       = aws_instance.host.id
}

output "origin_public_dns" {
  description = "EC2 origin (only reachable from CloudFront)"
  value       = aws_eip.host.public_dns
}

output "security_group_id" {
  value = aws_security_group.host.id
}

output "github_release_role_arn" {
  description = "Set as the PORTAL_RELEASE_ROLE_ARN repository variable"
  value       = aws_iam_role.github_release.arn
}
