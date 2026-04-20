# AWS DevOps Automation Portal

A full-stack web application for provisioning and managing AWS EC2 infrastructure through a browser UI. Users fill out a form, click Deploy, and watch Terraform and Ansible run live — no CLI required.

---

## What it does

**Phase 1 — Provision infrastructure**

- User opens the portal, fills in region, instance type, OS, packages, and key pair name.
- Backend generates Terraform HCL and an Ansible playbook on the fly.
- Terraform provisions EC2 instances, security groups, and outputs public IPs.
- Ansible SSHes into each instance and installs the selected packages (Docker, Nginx, Git, Python3, Node.js, k3s).
- Every log line streams live to the browser via Server-Sent Events.
- Deployment history is stored in SQLite and viewable in the History tab.

**Phase 2 — Day-2 instance management**

- Every provisioned instance is tracked in a local inventory (SQLite).
- The Instances tab lists all tracked instances with their state, IP, and region.
- Users can select a running instance, pick additional packages, and apply them without re-running Terraform.
- Configuration jobs stream live logs the same way deployments do.
- A Reconcile button syncs instance states with AWS (via boto3 `describe_instances`).

**Jenkins integration**

- The portal can run deployments locally (default) or delegate to a Jenkins pipeline (`DEPLOYMENT_RUNNER_MODE=jenkins`).
- In Jenkins mode, the portal triggers a parameterized build, streams the Jenkins console output live, and shows a direct link to the build.
- The Jenkins pipeline supports both Linux agents and Windows agents (via WSL).

---

## Architecture

```
Browser (React + Vite)
    │
    │  JSON + Server-Sent Events
    ▼
FastAPI backend (Python)
    ├── POST /api/deploy          — trigger a deployment
    ├── GET  /api/deploy/{id}/stream  — live log stream (SSE)
    ├── GET  /api/history         — past deployments
    ├── GET  /api/instances       — tracked EC2 instances
    ├── POST /api/instances/{id}/configure  — day-2 Ansible run
    └── POST /api/instances/reconcile       — sync state with AWS
         │
         ├── local mode: Terraform (Windows .exe or Linux binary)
         │               Ansible  (Linux/WSL)
         │
         └── jenkins mode: Jenkins REST API → parameterized pipeline
                           Jenkins console streamed back to browser
```

---

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | React 18, Vite, Tailwind CSS, lucide-react |
| Backend | Python 3.12, FastAPI, uvicorn, SQLite |
| Infrastructure | Terraform (AWS provider ~> 5.0) |
| Configuration | Ansible |
| CI/CD | Jenkins (declarative pipeline) |
| Cloud | AWS EC2, Security Groups, Key Pairs |
| AWS SDK | boto3 (instance state reconciliation) |

---

## Project structure

```
control_tower/
├── devops-portal/
│   ├── backend/
│   │   ├── main.py                        FastAPI entry point
│   │   ├── .env.example                   Environment variable template
│   │   ├── requirements.txt
│   │   ├── database/db.py                 SQLite schema + CRUD helpers
│   │   ├── generators/
│   │   │   ├── terraform_gen.py           Dynamic HCL generation
│   │   │   └── ansible_gen.py             Dynamic playbook generation
│   │   ├── executor/runner.py             Async subprocess runner (Windows+WSL aware)
│   │   ├── routes/
│   │   │   ├── deploy.py                  Deployment endpoints + SSE stream
│   │   │   ├── history.py                 History endpoints
│   │   │   └── instances.py              Instance management endpoints
│   │   ├── services/
│   │   │   ├── local_executor.py          Terraform + Ansible runner
│   │   │   ├── jenkins_executor.py        Jenkins API client + log streamer
│   │   │   ├── deployment_execution.py    Mode dispatcher (local vs jenkins)
│   │   │   ├── instance_configurator.py   Day-2 single-host Ansible runner
│   │   │   └── aws_reconciler.py          boto3 EC2 state sync
│   │   ├── models/schemas.py              Pydantic request/response models
│   │   └── scripts/run_portal_deployment.py  Jenkins agent entry point
│   ├── frontend/
│   │   └── src/
│   │       ├── App.jsx                    Main layout, nav, SSE wiring
│   │       └── components/
│   │           ├── InfraForm.jsx          Deployment form
│   │           ├── LogsPanel.jsx          Live terminal output
│   │           ├── DeploymentHistory.jsx  History table
│   │           ├── Instances.jsx          Instance management tab
│   │           └── StatusBadge.jsx        Status indicator
│   └── docker-compose.yml
├── jenkins/
│   └── JenkinsFile                        Declarative pipeline (Linux + Windows/WSL)
├── terraform/                             Org-level Terraform (Control Tower)
├── docs/
│   ├── demo-runbook.md                    Step-by-step commands to run the demo
│   ├── jenkins-aws-setup.md               Jenkins + AWS one-time configuration
│   ├── phase-2-instance-management.md     Architecture notes for Phase 2
│   ├── post-phase-2-configuration.md      Post-deploy configuration checklist
│   └── changes.md                         Detailed implementation log
└── README.md
```

---

## Running locally

See [docs/demo-runbook.md](docs/demo-runbook.md) for the exact terminal commands.

**Three terminals:**

```powershell
# Terminal 1 — Jenkins WSL agent (required for Jenkins mode)
java -jar agent.jar -url http://localhost:8080/ -secret <secret> -name "wsl-agent" -webSocket -workDir "C:\ProgramData\Jenkins\agent"

# Terminal 2 — Backend
cd devops-portal/backend
uvicorn main:app --reload --port 8000

# Terminal 3 — Frontend
cd devops-portal/frontend
npm run dev
```

Open **http://localhost:5173**.

---

## Configuration

Copy `devops-portal/backend/.env.example` to `.env` and fill in:

```env
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_DEFAULT_REGION=ap-south-1

# For Jenkins mode:
DEPLOYMENT_RUNNER_MODE=jenkins
JENKINS_BASE_URL=http://localhost:8080
JENKINS_JOB_NAME=devops-portal-deploy
JENKINS_USER=<your Jenkins username>
JENKINS_API_TOKEN=<token from Jenkins → Configure → API Token>
```

Leave `DEPLOYMENT_RUNNER_MODE=local` to run Terraform and Ansible directly from the backend process instead.

---

## Jenkins setup

See [docs/jenkins-aws-setup.md](docs/jenkins-aws-setup.md) for the full walkthrough.

Key steps:
1. Create a Jenkins pipeline job pointed at `jenkins/JenkinsFile` in this repo.
2. Add an `aws-portal-credentials` Jenkins credential (Username + Password = Access Key ID + Secret).
3. Add a `portal-ssh-key` Jenkins SSH credential (your EC2 key pair PEM).
4. On Windows: connect a WSL-enabled agent node so the pipeline can run Ansible.

---

## AWS permissions required

The IAM identity used by Terraform and boto3 needs at minimum:

```
ec2:RunInstances, ec2:TerminateInstances, ec2:DescribeInstances,
ec2:DescribeInstanceStatus, ec2:CreateSecurityGroup, ec2:AuthorizeSecurityGroupIngress,
ec2:CreateKeyPair, ec2:DeleteKeyPair, ec2:DescribeKeyPairs,
ec2:DescribeSecurityGroups, ec2:DeleteSecurityGroup
```

---

## Git workflow

| Branch | Purpose |
|--------|---------|
| `main` | Production — merges only via PR |
| `develop` | Integration branch |
| `feature-*` | Individual feature branches |

No direct pushes to `main`. All changes go through a pull request with at least one approval.

---

## License

For educational and demonstration purposes.
