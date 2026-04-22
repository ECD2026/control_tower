# Phase 2 — Day-2 Instance Management

## Goal

Phase 1 gave the portal a way to *create* infrastructure through either a local
runner or Jenkins. Phase 2 closes the loop: once an EC2 instance has been
provisioned, the user can return to the portal later and add more packages to
that specific instance through the GUI, without touching Terraform or
re-running the full deployment.

The portal becomes the single source of truth for:

- which instances have been created
- which packages they already carry
- what day-2 configuration jobs have been run against each instance

## Architecture overview

```
┌─────────────────────────────────────────────────────────────┐
│  Frontend — new "Instances" tab                            │
│    - list managed instances                                │
│    - select an instance, pick packages / custom commands   │
│    - live log stream during day-2 Ansible run              │
│    - "Reconcile" button to resync with AWS                 │
└─────────────────────┬───────────────────────────────────────┘
                      │ HTTP + SSE
┌─────────────────────▼───────────────────────────────────────┐
│  Backend — routes/instances.py                             │
│    GET  /api/instances                                     │
│    GET  /api/instances/{id}                                │
│    POST /api/instances/{id}/configure                      │
│    GET  /api/instances/configurations/{cfg}/stream         │
│    GET  /api/instances/configurations/{cfg}/status         │
│    POST /api/instances/reconcile                           │
└───────┬────────────────────┬────────────────────────┬───────┘
        │                    │                        │
        ▼                    ▼                        ▼
┌───────────────┐  ┌────────────────────┐  ┌──────────────────┐
│ SQLite tables │  │ instance_configurator │ aws_reconciler   │
│  instances    │  │   (ansible_gen +   │  │ (boto3 EC2       │
│  instance_    │  │    single-host     │  │  describe_       │
│  configurations│ │    runner)         │  │  instances)      │
└───────────────┘  └────────────────────┘  └──────────────────┘
```

## Data model

Two new SQLite tables were added in `devops-portal/backend/database/db.py`:

### `instances`

| Column          | Type  | Notes                                                     |
| --------------- | ----- | --------------------------------------------------------- |
| `id`            | TEXT  | EC2 instance ID (primary key)                             |
| `deployment_id` | TEXT  | FK to `deployments.id`                                    |
| `public_ip`     | TEXT  | Used as the SSH target                                    |
| `private_ip`    | TEXT  | Kept for future reconciliation                             |
| `ssh_user`      | TEXT  | `ec2-user` or `ubuntu`                                    |
| `key_pair_name` | TEXT  | Must match a PEM in `$SSH_KEY_DIR`                        |
| `os_type`       | TEXT  | `amazon_linux` or `ubuntu`                                |
| `region`        | TEXT  | AWS region the instance lives in                          |
| `instance_type` | TEXT  | EC2 size                                                  |
| `state`         | TEXT  | `running` / `stopped` / `terminated` / `unknown`          |
| `tags`          | TEXT  | JSON blob of EC2 tags                                     |
| `created_at`    | TEXT  | First time the portal saw the instance                    |
| `updated_at`    | TEXT  | Last mutation                                             |
| `last_seen_at`  | TEXT  | Last reconcile that confirmed the instance still exists   |

### `instance_configurations`

| Column            | Type  | Notes                                                       |
| ----------------- | ----- | ----------------------------------------------------------- |
| `id`              | TEXT  | UUID of the configure job                                   |
| `instance_id`     | TEXT  | FK to `instances.id`                                        |
| `status`          | TEXT  | `pending` / `running` / `success` / `failed`                |
| `packages`        | TEXT  | JSON array of packages requested                            |
| `custom_commands` | TEXT  | Newline-separated shell commands                            |
| `logs`            | TEXT  | JSON array of log lines streamed during the run             |
| `created_at`      | TEXT  | When the job was accepted                                   |
| `updated_at`      | TEXT  | Last status update                                          |

Both tables are created idempotently in `init_db()`.

## Flow: initial deployment now persists inventory

`services/local_executor.py` still runs Terraform the same way as before, but
after a successful `apply` it now:

1. Parses the new `instance_ids` and `instance_private_ips` Terraform outputs
   (added in `generators/terraform_gen.py`).
2. Builds a per-instance dict containing the public IP, SSH user, key pair,
   OS type, region, instance type, tags, and default state `running`.
3. Calls `save_instances(deployment_id, [...])`, which upserts each row in
   `instances`. Repeated deployments with the same instance IDs update in
   place rather than duplicating rows.

The existing Ansible bootstrap still runs — Phase 2 only adds persistence, it
does not change the first-boot configuration path.

> The Jenkins executor does not yet persist instance rows, because the Jenkins
> runner script (`scripts/run_portal_deployment.py`) delegates to
> `run_local_deployment`. When Phase 2 is triggered from a Jenkins-mode
> deployment, rows will still land in SQLite — but only if the Jenkins agent
> and the portal backend share the same DB path. For production, move this to
> a shared Postgres or RDS-hosted SQLite; the code uses `DB_PATH` so the
> change is just env-var wiring.

## New generator: single-host playbook

`generators/ansible_gen.py` was refactored so the package-install logic now
lives in small helpers (`_build_package_tasks`, `_build_system_update_task`,
`_build_custom_command_tasks`). Both entry points use them:

- `generate_ansible(request)` — unchanged behavioural contract; still targets
  `hosts: servers` and produces the full bootstrap playbook.
- `generate_ansible_for_host(instance, packages, custom_commands)` — new.
  Targets `hosts: target`, skips the k3s/docker-image bootstrap (those are
  first-boot concerns), and only emits package installs + custom commands.

## New service: `instance_configurator`

`services/instance_configurator.py` orchestrates a day-2 run:

1. Resolves `$SSH_KEY_DIR/<key_pair_name>.pem` exactly the way the local
   executor does — same fallback logic for Windows + WSL.
2. Generates `setup.yml` and `inventory.ini` in a dedicated temp directory so
   multiple configure jobs can run in parallel without clobbering each other.
3. Probes SSH on the instance's public IP (300-second deadline, 5 s
   back-off).
4. Runs `ansible-playbook` and streams every output line through the `log`
   callback — same contract the deploy route uses for its SSE stream.
5. Raises on any failure; the route layer catches and marks the
   `instance_configurations` row as `failed`.

## New route: `routes/instances.py`

| Method | Path                                                       | Purpose                                               |
| ------ | ---------------------------------------------------------- | ----------------------------------------------------- |
| GET    | `/api/instances`                                           | List persisted instances, optional `?state=running`.  |
| GET    | `/api/instances/{instance_id}`                             | Detail + recent configuration runs.                   |
| POST   | `/api/instances/{instance_id}/configure`                   | Enqueue a day-2 run. Body: `{ packages, custom_commands }`. |
| GET    | `/api/instances/configurations/{config_id}/stream`         | SSE live log stream (same format as deployments).     |
| GET    | `/api/instances/configurations/{config_id}/status`         | Quick status poll.                                    |
| POST   | `/api/instances/reconcile`                                 | Trigger an AWS sync. Body optional: `{ instance_ids }`. |

The SSE stream uses the same in-memory `asyncio.Queue` + SQLite replay pattern
as the existing `/api/deploy/{id}/stream` endpoint, so the frontend can reuse
`LogsPanel` verbatim.

Guardrails in the configure endpoint:

- 404 when the instance is not known locally.
- 409 when the instance's last-known state is not `running`.
- 400 when both `packages` and `custom_commands` are empty.

## AWS reconciler

`services/aws_reconciler.py`:

- Groups every tracked instance by `region`.
- For each region, opens a boto3 EC2 client (using `AWS_ACCESS_KEY_ID` and
  `AWS_SECRET_ACCESS_KEY` if present — otherwise it relies on the default
  boto3 credential chain, e.g. an instance profile or `~/.aws/credentials`).
- Calls `describe_instances(InstanceIds=...)` and maps each EC2 state to the
  portal's four-state model (`running` / `stopped` / `terminated` /
  `unknown`). Missing instances are marked `terminated`.
- Returns a summary `{ checked, updated, transitions, started_at, finished_at }`
  so the frontend can display a before/after breakdown.

Reconciliation is **on-demand only**. There is no background scheduler in
this phase — if you want periodic sync, wire up an external cron or the
`/loop` skill to hit `POST /api/instances/reconcile`.

## Frontend: the Instances tab

`frontend/src/components/Instances.jsx` is a new component wired into
`App.jsx` as a third tab next to Deploy and History:

- **Left pane**: table of instances with id / region / state / public IP /
  created-at. Click a row to select it.
- **Right pane**: when a row is selected, shows its deployment/key-pair/ssh
  metadata, a package multi-select (`Docker`, `Kubernetes`, `Nginx`, `Git`,
  `Python3`, `Node.js`), and a custom-commands textarea.
- **Apply configuration** button posts to the configure endpoint, opens an
  `EventSource` against the configuration's SSE stream, and reuses `LogsPanel`
  to show live output.
- **Reconcile** button hits `POST /api/instances/reconcile` and renders the
  returned summary inline.
- **Refresh** button re-fetches `GET /api/instances`.

The Apply button is disabled when the selected instance is not `running`, when
both package list and custom commands are empty, or while a job is in flight.

## Files changed in Phase 2

Added:

- `devops-portal/backend/routes/instances.py`
- `devops-portal/backend/services/instance_configurator.py`
- `devops-portal/backend/services/aws_reconciler.py`
- `devops-portal/frontend/src/components/Instances.jsx`
- `docs/phase-2-instance-management.md`  *(this file)*
- `docs/jenkins-aws-setup.md`

Modified:

- `devops-portal/backend/main.py` — register the instances router
- `devops-portal/backend/database/db.py` — new tables + CRUD helpers
- `devops-portal/backend/generators/ansible_gen.py` — shared helpers + new
  `generate_ansible_for_host`
- `devops-portal/backend/generators/terraform_gen.py` — emit private IPs
- `devops-portal/backend/services/local_executor.py` — persist instance rows
  after `apply`
- `devops-portal/backend/services/deployment_execution.py` — pass
  `deployment_id` to the local executor
- `devops-portal/backend/requirements.txt` — add `boto3`
- `devops-portal/frontend/src/App.jsx` — new "Instances" nav tab
- `jenkins/JenkinsFile` — inject AWS + SSH credentials, archive artifacts

## Verification

- `python -m compileall devops-portal/backend` → clean.
- `from main import app` → imports successfully.
- `app.routes` lists every new `/api/instances/*` endpoint.
- `npm run build` in `devops-portal/frontend` → builds to `dist/` without
  errors (1510 modules transformed).

## What is intentionally out of scope

- Background scheduling of reconciliation.
- Ansible fact collection to show which packages are *actually* installed
  (vs. what the portal requested).
- Instance termination / stop controls in the GUI.
- Pagination on `GET /api/instances` — currently returns every row ordered
  by `created_at` DESC.

Phase 3 can pick those up alongside approval gates and environment policies.
