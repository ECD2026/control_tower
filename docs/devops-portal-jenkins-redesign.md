# DevOps Portal Jenkins Redesign

## Goal

Move the DevOps Portal away from running Terraform and Ansible directly inside
the API process, and instead let the portal submit deployment requests to
Jenkins. Jenkins becomes the controlled execution layer, while the portal
remains the user-facing request and observability layer.

## Current State

The current backend flow in `devops-portal/backend/routes/deploy.py`:

1. Accepts deployment inputs from the frontend.
2. Generates Terraform and Ansible files in a temporary work directory.
3. Runs `terraform init`, `terraform plan`, and `terraform apply` locally.
4. Waits for SSH connectivity.
5. Runs `ansible-playbook` locally.
6. Streams logs to the frontend via SSE.

This approach is useful for local development, but it makes the API service a
privileged infrastructure executor and couples UI requests directly to
Terraform and Ansible runtimes.

## Target Architecture

### 1. Portal frontend and API

Responsibilities:

- Collect deployment inputs.
- Validate requests.
- Store deployment records and execution metadata.
- Trigger Jenkins builds.
- Stream execution status and logs back to the UI.

### 2. Jenkins pipeline

Responsibilities:

- Receive request parameters from the portal.
- Run approved Terraform and Ansible workflows.
- Archive console logs and output artifacts.
- Enforce approvals and execution policy.

### 3. Versioned infrastructure code

Responsibilities:

- Keep Terraform and Ansible logic in version control.
- Allow Jenkins to execute consistent, reviewable automation.
- Reduce the amount of fully dynamic code generation performed by the portal.

## Incremental Rollout Strategy

### Phase 1

- Add a deployment execution abstraction in the backend.
- Keep the current local executor available as a fallback.
- Add a Jenkins-backed executor that can trigger and observe builds.
- Keep the existing frontend log streaming contract intact.
- Add a Jenkins pipeline file in `jenkins/JenkinsFile`.
- Add a CLI runner in `devops-portal/backend/scripts/run_portal_deployment.py`
  so Jenkins can reuse the repository's deployment flow.

### Phase 2

- Move more infrastructure logic from generated files to versioned Terraform
  and Ansible templates.
- Shift the Jenkins job toward running repository-managed infrastructure code
  with parameters and generated variable files, rather than fully generated HCL.

### Phase 3

- Add approval gates, environment policies, artifact retention, and stronger
  auditability around production execution.

## Jenkins Integration Model

The portal will trigger a parameterized Jenkins job. The backend stores:

- execution mode (`local` or `jenkins`)
- external reference (queue/build identifier)
- external URL (build URL)

The backend then:

1. Starts the Jenkins build with request parameters.
2. Polls the Jenkins queue until a build is assigned.
3. Streams Jenkins progressive console output into the same SSE channel used by
   the current frontend.
4. Marks the deployment as `success` or `failed` based on Jenkins build result.

## Phase 1 Implementation Notes

The repository now contains the first implementation slice of this design:

- Backend execution is routed through a pluggable service layer.
- `DEPLOYMENT_RUNNER_MODE=local` keeps the existing behavior.
- `DEPLOYMENT_RUNNER_MODE=jenkins` triggers a Jenkins job and streams Jenkins
  console output back through the portal's SSE endpoint.
- Deployment records now track execution mode and external Jenkins metadata.
- The frontend surfaces execution mode and Jenkins build links when available.

## Jenkins Job Setup

Configure a Jenkins Pipeline job that points to this repository and uses:

- Script Path: `jenkins/JenkinsFile`

Agent expectations for the current pipeline:

- Linux/Unix Jenkins agent
- `python3` available
- `terraform` available on `PATH`
- outbound network access to AWS and required package registries
- SSH private key present for the selected AWS key pair

The pipeline installs Python dependencies and `ansible` into a local virtual
environment inside the workspace before running the deployment script.

## Environment Variables

### Portal backend

- `DEPLOYMENT_RUNNER_MODE`: `local` or `jenkins`
- `JENKINS_BASE_URL`
- `JENKINS_JOB_NAME`
- `JENKINS_USER`
- `JENKINS_API_TOKEN`
- `JENKINS_VERIFY_TLS`
- `JENKINS_POLL_INTERVAL_SECONDS`
- `JENKINS_REQUEST_TIMEOUT_SECONDS`

### Jenkins pipeline parameters

- `DEPLOYMENT_ID`
- `DEPLOY_MODE`
- `PROVIDER`
- `REGION`
- `INSTANCE_TYPE`
- `INSTANCE_COUNT`
- `KEY_PAIR_NAME`
- `SECURITY_GROUP_PORTS_JSON`
- `OS_TYPE`
- `PACKAGES_JSON`
- `CUSTOM_COMMANDS`
- `DOCKER_IMAGE`
- `KUBERNETES`
- `REPLICAS`

## Why Keep the Local Executor

Keeping the current execution path available during the transition helps with:

- local development
- demos without Jenkins
- phased rollout and troubleshooting

The local executor should be treated as a compatibility mode rather than the
long-term production design.
