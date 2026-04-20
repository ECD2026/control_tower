# Docs

This folder tracks design and implementation details for changes made in this
repository.

Current documents:

- `devops-portal-jenkins-redesign.md`: architecture and rollout notes for
  moving the DevOps Portal toward Jenkins-backed execution.
- `jenkins-aws-setup.md`: step-by-step Jenkins + AWS configuration the user
  has to perform before Phase 1 (Jenkins execution) can run end-to-end.
- `phase-2-instance-management.md`: architecture and implementation notes for
  the day-2 per-instance package management feature.
- `post-phase-2-configuration.md`: additional configuration required on the
  user's end after the Phase 2 code changes.
- `demo-runbook.md`: step-by-step terminal commands to start all services and
  walk through the demo end-to-end.
- `changes.md`: detailed implementation log for repository updates made during
  this work.
- `prometheus-grafana-monitoring.md`: plan for adding Prometheus + Grafana
  monitoring with a per-instance "Monitor" action wired into the Instances
  tab.
- `monitoring-setup-config.md`: **step-by-step configuration guide** for setting
  up Prometheus + Grafana monitoring, including AWS security group creation,
  environment variables, Terraform integration, and troubleshooting.
