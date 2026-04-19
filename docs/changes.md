# Detailed Change Log

## 2026-04-19 (later, same day)

### Jenkins credential wiring + configuration docs

- Updated `jenkins/JenkinsFile`:
  - Added an `environment {}` block that names the expected Jenkins credential
    IDs (`aws-portal-credentials`, `portal-ssh-key`).
  - Wrapped the "Run Portal Deployment" stage in `withCredentials([...])` so
    the pipeline now binds:
    - `usernamePassword(AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)` from
      the Jenkins credential store.
    - `sshUserPrivateKey(PORTAL_SSH_KEY_FILE)` so the PEM is materialised as
      a file only for the duration of the build.
  - Added a new `Validate Inputs` stage that fails fast if
    `KEY_PAIR_NAME` is missing.
  - Added a shell preamble that copies the SSH key to
    `$WORKSPACE/.ssh-portal/<KEY_PAIR_NAME>.pem` (chmod 600) so the portal's
    existing path convention (`$SSH_KEY_DIR/<key>.pem`) keeps working.
  - Added `post → always → archiveArtifacts` for `main.tf`, `setup.yml`, and
    `inventory.ini`, and `post → cleanup` to remove the temp SSH directory.
  - Exposed `AWS_DEFAULT_REGION=${params.REGION}` so the AWS provider picks
    the right endpoint.
- Added `docs/jenkins-aws-setup.md`: a walkthrough of every Jenkins UI and
  AWS configuration step required before a portal-triggered build can
  succeed. Covers agent prereqs, IAM policy, Jenkins credential creation,
  SSH key import from `C:\Users\Asus\Downloads\automatic.pem`, Jenkins job
  setup, API token creation, CSRF crumb, backend env wiring, a smoke-test
  procedure, and a troubleshooting matrix.

### Phase 2 — Day-2 instance management

Goal: allow users to open the portal, pick an existing EC2 instance by ID,
select additional packages, and have Ansible apply them without touching
Terraform or re-running the full deployment.

Implementation details — see `docs/phase-2-instance-management.md` for the
architectural view. Summary of changes:

- `devops-portal/backend/database/db.py`:
  - Added `instances` and `instance_configurations` tables (created
    idempotently in `init_db`).
  - Added CRUD helpers: `save_instance`, `save_instances`, `list_instances`,
    `get_instance`, `update_instance_state`, `mark_instance_missing`,
    `save_instance_configuration`, `update_instance_configuration_status`,
    `get_instance_configuration`, `list_instance_configurations`.
- `devops-portal/backend/generators/terraform_gen.py`: added
  `instance_private_ips` output for future reconciliation.
- `devops-portal/backend/generators/ansible_gen.py`:
  - Refactored shared package / system-update / custom-command task
    generation into private helpers.
  - Added `generate_ansible_for_host(instance, packages, custom_commands)`
    which emits a single-host playbook targeting `hosts: target`.
- `devops-portal/backend/services/local_executor.py`: after `terraform apply`,
  parse `instance_ids` / `instance_private_ips` and persist per-instance
  rows via `save_instances(deployment_id, [...])`. Accepts optional
  `deployment_id` for backwards compatibility.
- `devops-portal/backend/services/deployment_execution.py`: pass
  `deployment_id` to the local executor so the new persistence can happen.
- `devops-portal/backend/services/instance_configurator.py` (new): single-host
  Ansible orchestrator — generates the playbook + inventory, probes SSH with
  a 300 s deadline, runs `ansible-playbook`, streams logs through an async
  callback.
- `devops-portal/backend/services/aws_reconciler.py` (new): calls boto3
  `ec2:DescribeInstances` per region to sync local state; missing instances
  are flagged `terminated`. Falls back to the default boto3 credential chain
  if no explicit access keys are in the environment.
- `devops-portal/backend/routes/instances.py` (new): exposes
  `/api/instances`, `/api/instances/{id}`, `/api/instances/{id}/configure`,
  `/api/instances/configurations/{id}/stream`,
  `/api/instances/configurations/{id}/status`, `/api/instances/reconcile`.
  SSE pattern mirrors the deploy route so the frontend reuses `LogsPanel`.
- `devops-portal/backend/main.py`: register the new instances router.
- `devops-portal/backend/requirements.txt`: add `boto3==1.34.84`.
- `devops-portal/frontend/src/components/Instances.jsx` (new): the new
  "Instances" tab. Lists tracked instances, lets the user select one and pick
  packages / custom commands, streams the configuration logs, and surfaces a
  Reconcile button that shows which states changed.
- `devops-portal/frontend/src/App.jsx`: registered the new nav tab between
  Deploy and History.
- Documentation:
  - `docs/phase-2-instance-management.md` — architecture + data model +
    change list.
  - `docs/post-phase-2-configuration.md` — outstanding config the user has
    to do before Phase 2 can run against a real instance.
  - `docs/README.md` — updated index.

Verification:

- `python -m compileall devops-portal/backend` — clean.
- `from main import app` — imports successfully; all seven new
  `/api/instances*` routes are registered.
- `npm run build` in `devops-portal/frontend` — built `dist/` successfully
  (1510 modules transformed, no errors).

## 2026-04-19

### DevOps Portal Jenkins redesign slice

- Created the `docs/` folder to track architecture and implementation details.
- Documented the target redesign for moving DevOps Portal execution from the
  API process to Jenkins.
- Refactored the backend to support pluggable execution modes so the portal can
  preserve the current local flow while adding a Jenkins-backed execution path.
- Added backend service modules for:
  - local execution
  - Jenkins execution
  - execution type definitions
  - execution-mode dispatch
- Moved deployment route responsibilities toward coordination and state
  tracking instead of embedding all Terraform and Ansible logic directly in the
  route file.
- Added backend database support for:
  - `execution_mode`
  - `external_ref`
  - `external_url`
- Added a Jenkins-compatible CLI runner at
  `devops-portal/backend/scripts/run_portal_deployment.py`.
- Added a parameterized Jenkins pipeline in `jenkins/JenkinsFile` that runs the
  portal deployment flow from Jenkins.
- Updated backend configuration examples and Docker Compose passthrough for
  Jenkins-related environment variables.
- Fixed execution portability so the deployment runner can use:
  - Windows + WSL for local Windows development
  - native Linux tools for Jenkins agents
- Updated the frontend to display execution mode and Jenkins build links when
  available.
- Verification completed:
  - `python -m compileall devops-portal/backend`
  - backend import smoke test via `from main import app`
  - `npm run build` in `devops-portal/frontend`
