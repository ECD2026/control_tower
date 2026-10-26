# Docs

This folder tracks design and implementation details for changes made in this
repository.

Start here:

- `architecture.md`: **how the portal works** — components, request flows
  (login, credentials, GitHub Actions deployments, instance actions,
  monitoring), security model, naming/tagging, hosting and release.
- `demo-runbook.md`: one-time AWS setup, local run, and the step-by-step demo
  walkthrough with troubleshooting.

Background and history:

- `phase-2-instance-management.md`: architecture and implementation notes for
  the day-2 per-instance package management feature.
- `post-phase-2-configuration.md`: additional configuration required on the
  user's end after the Phase 2 code changes.
- `changes.md`: detailed implementation log for repository updates made during
  this work.
- `prometheus-grafana-monitoring.md`: original plan for Prometheus + Grafana
  monitoring with a per-instance "Monitor" action.
- `monitoring-setup-config.md`: original node_exporter + security group
  monitoring guide (CloudWatch metrics now cover every instance; see
  `architecture.md` §4.5).
- `devops-portal-jenkins-redesign.md`, `jenkins-aws-setup.md`: **superseded** —
  Jenkins execution was replaced by GitHub Actions
  (`.github/workflows/portal-deploy.yml`).
