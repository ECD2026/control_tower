# DevOps Automation Portal

A full-stack web application for provisioning AWS infrastructure and configuring servers automatically using Terraform and Ansible.

## Project Overview

Users fill out a form specifying infrastructure requirements (region, instance type, security groups), OS configuration (packages, custom commands), and deployment settings (Docker image, Kubernetes). The portal:

1. **Generates** Terraform HCL and Ansible YAML dynamically
2. **Executes** `terraform init/plan/apply` with real-time log streaming
3. **Updates** Ansible inventory with EC2 public IPs automatically
4. **Runs** Ansible playbooks to configure the launched instances
5. **Stores** deployment history in SQLite for reference

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Frontend (React + Vite)                                │
│  - Dark DevOps-themed dashboard                         │
│  - Form: Infrastructure / Configuration / Deployment    │
│  - Live terminal-style logs (SSE)                       │
│  - Deployment history table                             │
└──────────┬──────────────────────────────────────────────┘
           │
           │ JSON payload
           │
┌──────────▼──────────────────────────────────────────────┐
│  Backend (FastAPI)                                      │
│  ├─ POST /api/plan        (terraform plan only)         │
│  ├─ POST /api/deploy      (full provisioning)           │
│  ├─ GET  /api/deploy/{id}/stream  (SSE logs)           │
│  ├─ GET  /api/history     (deployment records)          │
│  └─ Generators:                                         │
│     ├─ terraform_gen.py   (dynamic HCL)                │
│     ├─ ansible_gen.py     (dynamic YAML)               │
│     └─ executor/runner.py (async subprocess)            │
└──────────┬──────────────────────────────────────────────┘
           │
           ├─→ terraform init/plan/apply
           ├─→ ansible-playbook -i inventory setup.yml
           └─→ AWS EC2 provisioning
```

## Directory Structure

```
devops-portal/
├── backend/
│   ├── main.py                   # FastAPI app entry point
│   ├── requirements.txt           # Python dependencies
│   ├── .env.example               # Environment template
│   ├── Dockerfile                 # Docker image for backend
│   ├── models/
│   │   └── schemas.py             # Pydantic models (DeploymentRequest, etc.)
│   ├── generators/
│   │   ├── terraform_gen.py       # HCL generation (10 AWS regions)
│   │   └── ansible_gen.py         # YAML playbook generation
│   ├── routes/
│   │   ├── deploy.py              # /api/plan, /api/deploy, /api/deploy/{id}/stream
│   │   └── history.py             # /api/history, /api/history/{id}
│   ├── database/
│   │   └── db.py                  # SQLite deployment tracking
│   └── executor/
│       └── runner.py              # Async subprocess runner
├── frontend/
│   ├── package.json               # Node.js dependencies
│   ├── vite.config.js             # Vite dev server config
│   ├── tailwind.config.js          # Tailwind CSS theme
│   ├── postcss.config.js           # PostCSS plugins
│   ├── index.html                  # HTML entry point
│   ├── nginx.conf                  # Production Nginx config
│   ├── Dockerfile                  # Docker image for frontend
│   └── src/
│       ├── main.jsx                # React root
│       ├── App.jsx                 # Main layout & state management
│       ├── index.css               # Tailwind directives
│       └── components/
│           ├── InfraForm.jsx       # 3-section deployment form
│           ├── LogsPanel.jsx       # Terminal-style log viewer
│           ├── StatusBadge.jsx     # Status indicator component
│           └── DeploymentHistory.jsx # Deployment table
├── docker-compose.yml              # Multi-container orchestration
└── CLAUDE.md                        # This file
```

## Getting Started

### Prerequisites

- **Backend**: Python 3.12+, Terraform, Ansible
- **Frontend**: Node.js 18+, npm
- **AWS**: Valid credentials (Access Key ID + Secret), a pre-created Key Pair

### Local Development

**1. Install backend dependencies:**

```bash
cd devops-portal/backend
pip install -r requirements.txt
```

**2. Install frontend dependencies:**

```bash
cd devops-portal/frontend
npm install
```

**3. Start the backend:**

```bash
cd devops-portal/backend
export AWS_ACCESS_KEY_ID=your_key
export AWS_SECRET_ACCESS_KEY=your_secret
uvicorn main:app --reload --port 8000
```

**4. In a new terminal, start the frontend:**

```bash
cd devops-portal/frontend
npm run dev
```

The frontend opens at **http://localhost:5173**, automatically proxying `/api/` calls to the backend on `http://localhost:8000`.

### Docker Deployment

**1. Build and run with docker-compose:**

```bash
cd devops-portal
cat > .env << EOF
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
AWS_DEFAULT_REGION=us-east-1
EOF

docker-compose up --build
```

- Frontend: **http://localhost:5173**
- Backend: **http://localhost:8000**

**2. To stop:**

```bash
docker-compose down
```

## API Endpoints

### Deployment

#### `POST /api/plan`
Generate a Terraform plan without applying.

**Request:**
```json
{
  "provider": "aws",
  "region": "us-east-1",
  "instance_type": "t2.micro",
  "instances": 1,
  "key_pair_name": "my-key",
  "security_group_ports": [22, 80, 443],
  "os_type": "amazon_linux",
  "packages": ["docker", "nginx"],
  "custom_commands": "echo 'Setup complete'",
  "docker_image": "",
  "kubernetes": false,
  "replicas": 1
}
```

**Response:**
```json
{
  "deployment_id": "uuid-string",
  "status": "pending",
  "work_dir": "/tmp/devops_xxxxx"
}
```

#### `POST /api/deploy`
Full provisioning: Terraform apply + Ansible configuration.

Same request/response as `/api/plan`.

#### `GET /api/deploy/{deployment_id}/stream`
Server-Sent Events stream of live logs.

```javascript
const es = new EventSource(`/api/deploy/uuid/stream`);
es.onmessage = (e) => {
  if (e.data === '__DONE__') {
    es.close();
  } else {
    console.log(e.data); // log line
  }
};
```

#### `GET /api/deploy/{deployment_id}/status`
Quick status check.

**Response:**
```json
{
  "deployment_id": "uuid",
  "status": "running"  // idle | pending | running | success | failed
}
```

### History

#### `GET /api/history`
List the 50 most recent deployments.

**Response:**
```json
[
  {
    "id": "uuid",
    "status": "success",
    "provider": "aws",
    "region": "us-east-1",
    "instance_type": "t2.micro",
    "instances": 1,
    "created_at": "2026-04-07T12:34:56.789Z",
    "updated_at": "2026-04-07T12:35:10.123Z"
  }
]
```

#### `GET /api/history/{deployment_id}`
Detailed deployment record with full config and logs.

**Response:**
```json
{
  "id": "uuid",
  "status": "success",
  "provider": "aws",
  "config": { /* full DeploymentRequest */ },
  "logs": [
    "[12:34:56] Starting deployment…",
    "[TERRAFORM] Apply complete!"
  ],
  "created_at": "...",
  "updated_at": "..."
}
```

## Code Patterns & Architecture Decisions

### Backend

**Async Execution with SSE Streaming:**
- Background tasks use `asyncio` for subprocess execution
- Logs are queued in `asyncio.Queue` as they arrive
- SSE generator reads from queue and yields to client
- Client-side `EventSource` receives logs in real-time

**Dynamic Code Generation:**
- `terraform_gen.py`: Builds valid HCL based on form inputs
  - 10 AWS regions with pre-mapped AMI IDs (Amazon Linux 2, Ubuntu 22.04)
  - Security group rules generated from port list
  - Instance count via count meta-argument
- `ansible_gen.py`: Builds YAML playbooks
  - Conditional package install (apt for Ubuntu, yum for Amazon Linux)
  - Special handling for Docker, k3s, Nginx
  - Inline Kubernetes deployment if k3s + docker_image

**SQLite Persistence:**
- Lightweight, single-file database (no server needed)
- Stores deployment request + status + logs for audit trail
- Queries paginated to last 50 deployments

### Frontend

**State Management:**
- Single `App.jsx` holds all state: `formData`, `logs`, `status`, `deploymentId`
- Form state is a flat object (no Redux/Zustand for simplicity)
- SSE connection is a `useRef` (not re-created on render)

**Live Log Panel:**
- Logs array indexed by line
- Auto-scroll to bottom on new line
- Colour classification: `[ERROR]` (red), `[TERRAFORM]` (purple), success keywords (green)
- Terminal-style font (JetBrains Mono) and dark background

**UI Theme:**
- Dark DevOps aesthetic (slate-900, gray tones, green/blue accents)
- Tailwind CSS utilities
- Status badges with animated dots (pulse on pending/running)

## Security Considerations

1. **AWS Credentials**: Passed as environment variables, never in code or logs
2. **SSH Keys**: Referenced by name only; actual keys live in `~/.ssh/`
3. **Terraform State**: Stored locally (demo) or should be moved to S3 with locking
4. **Ansible Inventory**: Generated temporarily, includes host IPs but no secrets
5. **API Validation**: Pydantic models validate all input before processing

## Testing & Debugging

### Backend Tests

```bash
# Check Terraform generation
python3 -c "from generators.terraform_gen import generate_terraform
from models.schemas import DeploymentRequest
req = DeploymentRequest(...)
print(generate_terraform(req))"
```

### Frontend Development

```bash
# Enable React DevTools (browser extension)
npm run dev

# Check console for EventSource errors
# Check Network tab for /api/deploy/{id}/stream (streaming response)
```

### Common Issues

| Issue | Solution |
|-------|----------|
| "Key Pair Name is required" | Fill the form field before clicking deploy |
| "SSE stream timeout" | Check backend logs; ensure `uvicorn` is running |
| `terraform init` hangs | Verify AWS credentials; check terraform path |
| Ansible fails with "permission denied" | Ensure `~/.ssh/key-pair.pem` exists with 600 permissions |
| `node_modules` committed | Add to `.gitignore` and `git rm -r --cached node_modules/` |

## Future Enhancements

- [ ] Multi-cloud support (GCP, Azure)
- [ ] Terraform state backend (S3 + DynamoDB lock)
- [ ] Ansible vault for secrets
- [ ] Grafana/Prometheus monitoring integration
- [ ] CI/CD triggers (GitHub Actions, GitLab CI)
- [ ] Rollback / destroy infrastructure UI
- [ ] Cost estimation before deploy
- [ ] Slack/email notifications

## Contributing

1. Create a feature branch from `develop`
2. Test locally (both backends running)
3. Ensure code is formatted and linted
4. Open a PR to `develop` with description of changes
5. Get 1 approval before merging to `develop`, then to `main`

## License

MIT
