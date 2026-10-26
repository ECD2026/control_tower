# Demo Runbook — DevOps Portal

Everything needed to stand the portal up and walk through the demo:
login → credentials → deploy (GitHub Actions) → pause / resume / restart /
configure → monitor in Grafana → clean up.

How it works under the hood: [architecture.md](architecture.md).

---

## Part A — One-time setup on AWS

Run from the repo root on a machine with the **AWS CLI** (an admin of the
target account) and the **GitHub CLI** (admin on the repo) logged in. In Git
Bash on Windows, export `MSYS_NO_PATHCONV=1` first so `/devops-portal/...`
paths are not rewritten.

### A1. Secrets → SSM Parameter Store + GitHub

```bash
# Recommended: a fine-grained PAT on this repo only
# (Actions: read & write, Contents: read). Falls back to `gh auth token`.
export PORTAL_GITHUB_TOKEN=github_pat_xxx

# local until portal-deploy.yml is on the default branch (see A4)
PORTAL_RUNNER_MODE=local bash devops-portal/infra/scripts/bootstrap-secrets.sh ap-south-1 ECD2026/control_tower
```

This creates `/devops-portal/{encryption_key, jwt_secret, workflow_key,
grafana_admin_password, github_token, runner_mode, allow_signup}` and the
`PORTAL_WORKFLOW_KEY` repository secret. It is safe to re-run; existing keys
are kept.

### A2. Portal host (EC2 + Elastic IP)

```bash
cd devops-portal/infra/terraform
terraform init
terraform apply -var git_ref=main      # or a feature branch to try it out
# restrict who can reach the portal (plain HTTP):
#   terraform apply -var 'http_ingress_cidrs=["<your-ip>/32"]'
terraform output
```

| Output | Use |
|---|---|
| `portal_url` | `http://ec2-x-x-x-x.ap-south-1.compute.amazonaws.com` — open this |
| `instance_id` | SSM target for the release workflow |
| `github_release_role_arn` | release workflow role |

First boot takes ~10 minutes: Docker install, image builds, `docker compose
up`. Follow it with:

```bash
aws ssm start-session --target <instance_id> --region ap-south-1
sudo tail -f /var/log/devops-portal-bootstrap.log
```

### A3. Release pipeline variables

```bash
gh variable set PORTAL_AWS_REGION       --body ap-south-1              --repo ECD2026/control_tower
gh variable set PORTAL_HOST_INSTANCE_ID --body "$(terraform output -raw instance_id)" --repo ECD2026/control_tower
gh variable set PORTAL_RELEASE_ROLE_ARN --body "$(terraform output -raw github_release_role_arn)" --repo ECD2026/control_tower
```

From then on every merge to `main` that touches `devops-portal/**` is tested
and rolled out by `portal-release.yml`. To deploy another ref by hand:
**Actions → Portal Release → Run workflow → ref**.

### A4. Switch deployments to GitHub Actions

Once `.github/workflows/portal-deploy.yml` is on `main`:

```bash
aws ssm put-parameter --region ap-south-1 --name /devops-portal/runner_mode \
  --value github_actions --type String --overwrite
gh workflow run portal-release.yml --repo ECD2026/control_tower   # redeploy to apply
```

---

## Part B — Running locally (optional)

```bash
cd devops-portal
echo "DEPLOYMENT_RUNNER_MODE=local" > .env       # Terraform + Ansible run in the backend container
docker compose up -d --build
# → http://localhost   (set PORTAL_HTTP_PORT=8088 in .env if port 80 is taken)
```

For frontend development with hot reload, run `npm run dev` in
`devops-portal/frontend` against the containers. The backend, Prometheus and
Grafana ports are bound to `127.0.0.1`.

Backend tests: `cd devops-portal/backend && python -m pytest -q`.

---

## Part C — Demo flow

Open the portal URL. The sidebar on the left has **Overview, Deploy,
Instances, Monitoring, Deployments** and **Settings → Credentials**.

### 1. Sign in

**Create account** with an email and a password (8+ characters). Overview
shows a *Getting started* checklist.

### 2. Upload AWS credentials and a key pair (Credentials)

1. **Add credentials** → display name, **access key ID**, **secret access key**,
   default region (`ap-south-1`).
2. SSH key pair: **Generate new** (download the `.pem` when prompted), or
   **Upload .pem** of an existing EC2 key pair. Give it a name such as `demo-key`.
3. **Verify & save**. The portal checks the keys with AWS STS and shows
   the AWS account ID. Bad keys are rejected with AWS's message.

> The IAM user needs EC2 (instances, security groups, key pairs) and
> `cloudwatch:GetMetricData`. Use a dedicated demo user, e.g.
> `devops-portal-demo`, not root keys.

### 3. Deploy (Deploy)

1. Credentials: pick the one from step 2 (the key pair fills in).
2. Name: `demo-web` → instances become `demo-web-1`, `demo-web-2`, ….
3. Region `ap-south-1`, type `t3.micro`, 1 instance, Amazon Linux.
4. Packages: keep **Node Exporter**, add **Nginx**. Keep **Detailed CloudWatch
   monitoring** on.
5. **Generate Plan** first to show the Terraform plan, then **Deploy
   Infrastructure**.
6. Live Output streams the run:
   - `[GITHUB] …` lines are the workflow's steps. **GitHub run** in the header
     opens the run on GitHub.
   - In `local` mode you see `[TERRAFORM]` and `[ANSIBLE]` lines directly.
7. On success: **View instances**.

In the EC2 console, the resources are easy to spot: instance `demo-web-1`,
SG `devops-portal-<id8>-sg-…`, key pair `devops-portal-<id8>-demo-key-…`, all
tagged `PortalDeploymentId`.

### 4. Manage the instance (Instances → Overview tab)

- **Live metrics**: CPU, network and status checks from CloudWatch, plus
  memory/disk from node_exporter. The first datapoints arrive 2–5 minutes
  after launch.
- **Pause** → the state goes *Pausing* → *Paused* (EC2 stop).
- **Resume** → *Starting* → *Running*. Point out that the public IP changed
  and the portal picked it up.
- **Restart** → EC2 reboot.

### 5. Configure (Instances → Configure tab)

Tick **Git** / **Docker**, optionally add `echo hello from the portal`,
then **Apply with Ansible**. Ansible logs stream live and end with
`PLAY RECAP … failed=0`.

### 6. Monitor

- **Instances → Monitoring tab**: the per-instance Grafana dashboard
  (CloudWatch rows plus the node_exporter OS row).
- **Monitoring** page: the fleet dashboard showing all your instances, CPU and
  network by instance, and paused count.
- **Prometheus targets** button: the `cloudwatch` and `node` jobs are *UP*.

Opening `/grafana` in a private window without logging in redirects to the
portal login. The monitoring stack is behind portal auth.

### 7. History (Deployments)

Every plan/deploy is listed with its runner and GitHub run link. Click a row
to replay its full log.

### 8. Clean up

Instances → select → **Terminate** (confirm). The reconcile loop marks it
terminated and it drops out of Prometheus targets and the fleet dashboard.

---

## Part D — Tearing the portal down

```bash
cd devops-portal/infra/terraform && terraform destroy
aws ssm delete-parameters --region ap-south-1 --names \
  /devops-portal/encryption_key /devops-portal/jwt_secret /devops-portal/workflow_key \
  /devops-portal/grafana_admin_password /devops-portal/github_token \
  /devops-portal/runner_mode /devops-portal/allow_signup
gh secret delete PORTAL_WORKFLOW_KEY --repo ECD2026/control_tower
```

Instances users deployed are **not** part of this stack. Terminate them from
the portal first, or find them by tag `Project=devops-portal,Component=workload`.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Portal URL returns 502/504 | Host still bootstrapping, or a container is down | `aws ssm start-session …` then `sudo docker compose -f /opt/devops-portal/src/devops-portal/docker-compose.yml ps`; check `/var/log/devops-portal-bootstrap.log` |
| Bootstrap log: `Missing /devops-portal/…` | A1 not run (or after the 30-min wait) | Run A1, then `sudo /opt/devops-portal/bin/host-deploy.sh main` on the host or re-run Portal Release |
| `AWS rejected these credentials` | Wrong/inactive keys | Check the IAM user's access key status |
| Deploy log: `PORTAL_WORKFLOW_KEY is not set` / `Could not decrypt credentials_blob` | Portal and repo secret differ | Re-run A1 (it re-syncs the repo secret from SSM) |
| Deploy log: GitHub API 404 on `/dispatches` | `portal-deploy.yml` is not on the default branch | Merge it to `main`, or set `runner_mode=local` (A4) |
| Deploy log: GitHub API 401/403 | Token expired or lacks Actions write | New PAT → `PORTAL_GITHUB_TOKEN=… bootstrap-secrets.sh` → redeploy |
| Live metrics show `—` | CloudWatch has no datapoints yet | Wait 2–5 min. Check `cloudwatch_exporter_errors_total` in Prometheus |
| Memory/Disk `—`, CPU fine | node_exporter not installed, or the instance is in another region than the host | Install Node Exporter (Configure tab). Cross-region instances only get CloudWatch |
| Grafana iframe shows the portal login | Session expired | Sign in again |
| Configure: `SSH did not become ready` | SG lacks port 22 or the instance is paused | Keep port 22 in the deploy form; resume the instance |
| Pause/Resume stuck on *Pausing*/*Starting* | Background poll timed out | **Sync with AWS** on the Instances page |
