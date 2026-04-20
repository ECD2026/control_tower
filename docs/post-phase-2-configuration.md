# Post-Phase-2 Configuration

The code changes from `docs/phase-2-instance-management.md` are already in the
repository. This document lists the configuration you still have to do — on
your machine, on your Jenkins agent, or in AWS — before the new "Instances"
tab and the `/api/instances/*` endpoints will actually work end-to-end.

Nothing in this document needs a code change; everything is a one-time
environmental step.

---

## 1. Install the new Python dependency

`boto3` was added to `devops-portal/backend/requirements.txt`. Reinstall on
whichever machines run the backend:

```bash
cd devops-portal/backend
pip install -r requirements.txt
```

If you run the backend through `docker-compose`:

```bash
cd devops-portal
docker-compose build backend
docker-compose up -d backend
```

Smoke test:

```bash
python -c "import boto3; print(boto3.__version__)"
```

If this is skipped, `POST /api/instances/reconcile` will 500 with
`boto3 is not installed in the backend environment`. The configure endpoint
does **not** need boto3 — it only uses SSH + Ansible — but reconciliation
does.

---

## 2. Ensure AWS credentials are visible to the backend

Reconciliation asks AWS "are these instance IDs still alive?" The backend
resolves credentials in this order:

1. `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` environment variables on the
   backend process.
2. The default boto3 credential chain — `~/.aws/credentials`, instance
   profile, SSO, etc.

Pick one, and make sure the IAM identity has at least:

```
ec2:DescribeInstances
ec2:DescribeInstanceStatus
```

For local development, the simplest path is:

```bash
export AWS_ACCESS_KEY_ID=AKIA...
export AWS_SECRET_ACCESS_KEY=...
export AWS_DEFAULT_REGION=ap-south-1
uvicorn main:app --reload --port 8000
```

Under `docker-compose`, the compose file already forwards `AWS_ACCESS_KEY_ID`
and `AWS_SECRET_ACCESS_KEY` from the shell `.env`, so no change is required
there.

If you are running the Jenkins-backed flow but the portal backend is on your
laptop, note that reconciliation runs **inside the backend process**, not
inside Jenkins. The backend therefore needs its own read-only AWS credentials
in addition to the `aws-portal-credentials` you configured in Jenkins.

The region used for each reconciliation call comes from the stored
`instances.region` column, which is populated at deployment time. No config
action required unless you deploy into a region the backend can't reach.

---

## 3. Make sure the SSH key is available to the configure endpoint

`POST /api/instances/{id}/configure` runs Ansible over SSH from the backend
host (not from Jenkins). It resolves the private key as
`$SSH_KEY_DIR/<instance.key_pair_name>.pem` with the same convention the
local executor uses.

For your setup:

- **Key pair name on the instance**: `automatic` (this is what AWS records
  once Terraform creates the instance with `key_name = "automatic"`).
- **PEM file on disk**: `C:\Users\Asus\Downloads\automatic.pem`.

Do one of the following, depending on how the backend runs:

### 3.1 Backend on Windows (native uvicorn)

The local executor routes SSH through WSL when `sys.platform == "win32"`, so
the key path must be valid *inside WSL*. Copy the PEM into your WSL home:

```bash
wsl -- bash -lc "mkdir -p ~/.ssh && cp /mnt/c/Users/Asus/Downloads/automatic.pem ~/.ssh/automatic.pem && chmod 600 ~/.ssh/automatic.pem"
```

If `SSH_KEY_DIR` is not set, the backend defaults to `/home/asus/.ssh`
(see `services/instance_configurator.py:21`). If your WSL username is not
`asus`, either:

- symlink `/home/asus` to your real WSL home, or
- set `SSH_KEY_DIR` explicitly, e.g. `SSH_KEY_DIR=/home/<youruser>/.ssh`.

### 3.2 Backend on Linux / macOS

```bash
mkdir -p ~/.ssh
cp /path/to/automatic.pem ~/.ssh/automatic.pem
chmod 600 ~/.ssh/automatic.pem
```

No env var needed — the default is `~/.ssh`.

### 3.3 Backend inside `docker-compose`

`docker-compose.yml` already mounts `~/.ssh:/root/.ssh:ro` into the backend
container and sets `SSH_KEY_DIR=/root/.ssh`. You just have to ensure your
host's `~/.ssh/automatic.pem` exists and is `chmod 600`. Rebuild with:

```bash
docker-compose up -d backend
```

### 3.4 Verification

After any of the options above:

```bash
curl http://localhost:8000/api/instances
```

Pick an instance ID that has `"state": "running"` and try:

```bash
curl -X POST http://localhost:8000/api/instances/<id>/configure \
     -H "Content-Type: application/json" \
     -d '{"packages":["git"], "custom_commands":""}'
```

The response includes a `configuration_id`. Open:

```
GET http://localhost:8000/api/instances/configurations/<configuration_id>/stream
```

Expected log sequence:

```
[HH:MM:SS] Work directory: /tmp/instance_cfg_...
[HH:MM:SS] setup.yml written for instance i-0abc...
[HH:MM:SS] Inventory written (1.2.3.4)
[HH:MM:SS] Waiting for SSH to become available
[SSH] ...
[HH:MM:SS] Running: ansible-playbook
[ANSIBLE] PLAY [Apply package updates to i-0abc...] ...
[HH:MM:SS] Configuration completed successfully on i-0abc...
```

If the SSH step loops for 300 s and then times out, either the PEM is not at
the expected path, the instance's security group does not allow SSH from the
backend host, or the instance is not actually `running`.

---

## 4. Security group caveat

The portal provisioning flow opens TCP 22 for `0.0.0.0/0` in the generated
security group. That is safe for demos but means anyone can knock on port 22.

For Phase 2, the backend host needs to be able to SSH into each managed
instance. If you later tighten the security group, make sure to keep at
least an ingress rule for the backend's public IP range — otherwise the
configure endpoint will stall at the SSH readiness probe.

---

## 5. Existing instances created before Phase 2

`instances` rows are only written by the local executor **going forward**.
Any EC2 instances created before the Phase 2 code landed will not show up in
the Instances tab, because no row was persisted at the time.

If you need to manage one of those legacy instances through the new tab,
backfill the row manually. Example using the SQLite CLI inside the backend
container:

```sql
INSERT INTO instances (
  id, deployment_id, public_ip, private_ip, ssh_user, key_pair_name,
  os_type, region, instance_type, state, tags, created_at, updated_at, last_seen_at
) VALUES (
  'i-0abc...', 'legacy-deployment', '1.2.3.4', NULL, 'ec2-user', 'automatic',
  'amazon_linux', 'ap-south-1', 't2.micro', 'running', '{}',
  datetime('now'), datetime('now'), datetime('now')
);
```

Then hit `POST /api/instances/reconcile` so the state column is verified
against AWS.

---

## 6. Optional — schedule reconciliation

Phase 2 only exposes a manual **Reconcile** button in the UI. If you want the
state column to stay fresh without manual clicks, add an external trigger.
Two easy options:

### 6.1 A system cron on the backend host

```cron
*/15 * * * * curl -fsS -X POST http://localhost:8000/api/instances/reconcile >/dev/null
```

### 6.2 The `/loop` skill

From a Claude Code session attached to this repo:

```
/loop 15m POST http://localhost:8000/api/instances/reconcile
```

Either keeps `instances.state` within ~15 minutes of reality.

---

## 7. Jenkins-mode note

When `DEPLOYMENT_RUNNER_MODE=jenkins` is active, the first-boot Ansible and
Terraform still run on the Jenkins agent. The Jenkins agent invokes
`scripts/run_portal_deployment.py`, which calls `run_local_deployment`, which
now calls `save_instances`. That means:

- If the Jenkins agent and the portal backend share the same `DB_PATH`
  (mounted volume, shared Postgres in a future iteration, etc.), instance
  rows will appear in the tab immediately after a Jenkins-triggered
  deployment.
- If they do not share a DB, Jenkins-provisioned instances will only show up
  after you backfill (section 5) or switch the backend to read the Jenkins
  workspace's DB.

For a single-host dev setup where both the backend and Jenkins run on the
same machine, simply point `DB_PATH` at a stable location:

```bash
export DB_PATH=/var/lib/devops-portal/deployments.db
```

and make sure the Jenkins user has write access to that path.

---

## 8. Checklist before demoing Phase 2

- [ ] `pip install -r requirements.txt` or `docker-compose build backend`
      so `boto3` is present.
- [ ] `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` exported to the backend,
      or a configured AWS profile.
- [ ] `automatic.pem` copied to `$SSH_KEY_DIR/automatic.pem`, chmod 600.
- [ ] Backend restarted so the new routes are loaded.
- [ ] Frontend rebuilt (`npm run build`) or dev server restarted.
- [ ] At least one fresh deployment run so an `instances` row exists.
- [ ] `POST /api/instances/reconcile` returns a `checked > 0` response.
- [ ] Selecting an instance in the Instances tab and clicking **Apply
      configuration** with `git` selected completes with `success`.
