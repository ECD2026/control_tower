# Monitoring Setup Configuration Guide

This document outlines all the configuration steps required to get the Prometheus + Grafana monitoring stack running with the DevOps Portal.

---

## 1. Prerequisites

Ensure you have the following installed and running:
- Docker & Docker Compose
- Python 3.12+ (backend)
- Node.js 18+ (frontend)
- Terraform 1.8+
- Ansible

---

## 2. Backend Environment Configuration

### 2.1 Create/Update `.env` file

In `devops-portal/backend/`, create or update your `.env` file with the following monitoring-related variables:

```bash
# Monitoring Integration (new)
GRAFANA_PUBLIC_URL=http://localhost:3000
GRAFANA_DASHBOARD_UID=instance-overview
PROMETHEUS_TARGETS_PATH=/app/monitoring/prometheus/targets/instances.json
PORTAL_MONITORING_SG_ID=sg-xxxxxxxx
```

#### Environment Variable Details

| Variable | Default | Description |
|----------|---------|-------------|
| `GRAFANA_PUBLIC_URL` | `http://localhost:3000` | Public/accessible URL for Grafana. Change for remote/production deployments. |
| `GRAFANA_DASHBOARD_UID` | `instance-overview` | Grafana dashboard UID (unique identifier). Must match the provisioned dashboard. |
| `PROMETHEUS_TARGETS_PATH` | `/app/monitoring/prometheus/targets/instances.json` | File path where Prometheus file_sd targets are written (inside container). |
| `PORTAL_MONITORING_SG_ID` | `` (empty) | **AWS Security Group ID** that is allowed to scrape exporters (ports 9100, 8080). Leave empty to skip exporter port ingress rules. |

### 2.2 Full `.env` Template

Copy this complete template and fill in your values:

```bash
# AWS Credentials
AWS_ACCESS_KEY_ID=your_access_key_here
AWS_SECRET_ACCESS_KEY=your_secret_key_here
AWS_DEFAULT_REGION=ap-south-1

# App Settings
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
DB_PATH=deployments.db
DEPLOYMENT_RUNNER_MODE=local

# Jenkins Integration (optional)
JENKINS_BASE_URL=https://jenkins.example.com
JENKINS_JOB_NAME=devops-portal/deploy
JENKINS_USER=portal-bot
JENKINS_API_TOKEN=replace_me
JENKINS_VERIFY_TLS=true
JENKINS_POLL_INTERVAL_SECONDS=3
JENKINS_REQUEST_TIMEOUT_SECONDS=15

# Ansible Settings
ANSIBLE_HOST_KEY_CHECKING=False
SSH_KEY_DIR=~/.ssh

# Monitoring Integration
GRAFANA_PUBLIC_URL=http://localhost:3000
GRAFANA_DASHBOARD_UID=instance-overview
PROMETHEUS_TARGETS_PATH=/app/monitoring/prometheus/targets/instances.json
PORTAL_MONITORING_SG_ID=sg-xxxxxxxx
```

---

## 3. AWS Security Group Setup

### 3.1 Create a Monitoring Security Group

This SG will be used to restrict access to exporter ports on deployed instances.

#### Via AWS Console:

1. Go to **EC2 → Security Groups**
2. Click **Create security group**
3. Name it: `devops-portal-monitoring`
4. Description: `Allow Prometheus to scrape exporters`
5. VPC: Select your desired VPC (same as where instances will run)
6. Add **Inbound Rules**:
   - Type: `Custom TCP`
   - Port Range: `9100` (node_exporter)
   - Source: `CIDR` or `Security Group` (see note below)
   - Type: `Custom TCP`
   - Port Range: `8080` (cAdvisor)
   - Source: `CIDR` or `Security Group`

7. Click **Create security group**
8. Copy the Security Group ID (format: `sg-xxxxxxxx`)

#### Via AWS CLI:

```bash
# Create SG
aws ec2 create-security-group \
  --group-name devops-portal-monitoring \
  --description "Allow Prometheus to scrape exporters" \
  --vpc-id vpc-xxxxxxxx \
  --region ap-south-1

# Authorize inbound for node_exporter (9100)
aws ec2 authorize-security-group-ingress \
  --group-id sg-xxxxxxxx \
  --protocol tcp \
  --port 9100 \
  --cidr 10.0.0.0/8 \
  --region ap-south-1

# Authorize inbound for cAdvisor (8080)
aws ec2 authorize-security-group-ingress \
  --group-id sg-xxxxxxxx \
  --protocol tcp \
  --port 8080 \
  --cidr 10.0.0.0/8 \
  --region ap-south-1
```

**Note on source CIDR/SG:**
- **For local docker-compose demo**: Use `0.0.0.0/0` or your machine's IP (less secure, fine for dev).
- **For production**: Use the CIDR of your VPC or the security group of the Prometheus server.

### 3.2 Set the SG ID in `.env`

Once you have the security group ID (e.g., `sg-abc12345`), update your `.env`:

```bash
PORTAL_MONITORING_SG_ID=sg-abc12345
```

---

## 4. Docker Compose Configuration

### 4.1 Verify Volume Mounts

The `docker-compose.yml` includes monitoring configuration volumes. Ensure the `./monitoring/` directory structure exists:

```
devops-portal/
├── monitoring/
│   ├── prometheus/
│   │   ├── prometheus.yml
│   │   └── targets/
│   │       └── instances.json
│   └── grafana/
│       ├── provisioning/
│       │   ├── datasources/
│       │   │   └── prometheus.yml
│       │   └── dashboards/
│       │       └── dashboards.yml
│       └── dashboards/
│           └── instance-overview.json
├── docker-compose.yml
└── backend/
    └── .env
```

This structure was created during implementation. Verify:

```bash
ls -R devops-portal/monitoring/
```

### 4.2 Environment Variables in Compose

The `docker-compose.yml` passes monitoring env vars to the backend service. Verify these lines exist in `docker-compose.yml`:

```yaml
services:
  backend:
    environment:
      - GRAFANA_PUBLIC_URL=${GRAFANA_PUBLIC_URL:-http://localhost:3000}
      - GRAFANA_DASHBOARD_UID=${GRAFANA_DASHBOARD_UID:-instance-overview}
      - PROMETHEUS_TARGETS_PATH=${PROMETHEUS_TARGETS_PATH:-/app/monitoring/prometheus/targets/instances.json}
      - PORTAL_MONITORING_SG_ID=${PORTAL_MONITORING_SG_ID:-}
```

---

## 5. Grafana Configuration

### 5.1 Auto-Provisioned Components

The following are automatically provisioned when Grafana starts:

✅ **Datasource**: Prometheus at `http://prometheus:9090`
✅ **Dashboard**: `instance-overview` with CPU, Memory, Disk, Network panels
✅ **Anonymous Viewer**: Enabled for embed mode (no login required)

### 5.2 Manual Tweaks (Optional)

If you need to adjust Grafana settings after startup:

1. Access Grafana at `http://localhost:3000`
2. Admin credentials (default): `admin` / `admin`
3. Customize:
   - **Datasources** → Prometheus → verify URL is `http://prometheus:9090`
   - **Dashboards** → instance-overview → edit panels as needed
   - **Organization** → Settings → enable/disable anonymous access

### 5.3 Embedding Configuration (for iframe mode)

If you plan to use iframe embedding (frontend feature flag `EMBED_GRAFANA = true`):

1. Go to **Admin** → **Settings** → **Security**
2. Ensure:
   - `allow_embedding = true`
   - `cookie_samesite = none` (for cross-origin iframe)
3. Go to **Admin** → **Settings** → **Auth** → **Anonymous**
4. Ensure:
   - `enabled = true`
   - `org_role = Viewer`

These are already set in the `docker-compose.yml` via env vars:
```yaml
environment:
  - GF_SECURITY_ALLOW_EMBEDDING=true
  - GF_SECURITY_COOKIE_SAMESITE=none
  - GF_AUTH_ANONYMOUS_ENABLED=true
  - GF_AUTH_ANONYMOUS_ORG_ROLE=Viewer
```

---

## 6. Prometheus Configuration

### 6.1 Static Configuration

The `monitoring/prometheus/prometheus.yml` file is pre-configured with:

```yaml
global:
  scrape_interval: 30s

scrape_configs:
  - job_name: node
    file_sd_configs:
      - files: ['/etc/prometheus/targets/instances.json']
        refresh_interval: 15s
```

This uses **file-based service discovery** (file_sd). The backend writes instance targets to `instances.json` automatically.

### 6.2 Target Discovery Flow

1. Backend detects instance state change (deploy, start, stop, delete, reconcile)
2. Backend calls `rewrite_targets()` → writes `instances.json`
3. Prometheus reads the new targets within ~15s
4. Prometheus scrapes `http://<instance_ip>:9100` for node_exporter metrics

**Targets file format** (`instances.json`):
```json
[
  {
    "targets": ["54.123.45.67:9100"],
    "labels": {
      "instance_id": "i-0abc123def456",
      "region": "ap-south-1",
      "os_type": "amazon_linux"
    }
  }
]
```

---

## 7. Terraform Generator Configuration

### 7.1 Monitoring Security Group Ingress Rules

When you deploy infrastructure, Terraform will:

1. Read `PORTAL_MONITORING_SG_ID` from env
2. **Skip** ports 9100 and 8080 from public ingress rules (not exposed to `0.0.0.0/0`)
3. Add ingress rules **from** the monitoring SG only (if `PORTAL_MONITORING_SG_ID` is set)

Generated Terraform will include:
```hcl
variable "monitoring_sg_id" {
  description = "Security group ID allowed to scrape monitoring exporters"
  type        = string
  default     = "sg-abc12345"  # from env
}

resource "aws_security_group" "devops_portal_sg" {
  # ... normal ports (22, 80, 443) with 0.0.0.0/0 ...
  
  # NEW: Monitoring ingress (restricted to monitoring SG)
  ingress {
    description     = "Monitoring port 8080 from Prometheus SG"
    from_port       = 8080
    to_port         = 8080
    protocol        = "tcp"
    security_groups = [var.monitoring_sg_id]
  }

  ingress {
    description     = "Monitoring port 9100 from Prometheus SG"
    from_port       = 9100
    to_port         = 9100
    protocol        = "tcp"
    security_groups = [var.monitoring_sg_id]
  }
}
```

### 7.2 If You Don't Have a Monitoring SG

If you leave `PORTAL_MONITORING_SG_ID` empty:
- Monitoring ports (9100, 8080) will **not** be opened to any source
- Exporters will run but won't be reachable from Prometheus
- Instance details tab will still work; Monitor button will be disabled

**Recommendation**: Set up the monitoring SG (Section 3) before deploying instances.

---

## 8. Deployment Package Selection

### 8.1 Instance Creation (Deploy Tab)

In the **Deploy** form:

1. **Packages to Install** section includes:
   - ✅ **Node Exporter** (📈 icon) — **recommended, set by default**
   - **cAdvisor** (📊 icon) — optional, only needed if Docker monitoring desired

2. **Default behavior**:
   - `node_exporter` is **auto-selected** by default
   - Instances created with `node_exporter` get tagged `monitoring: "enabled"`
   - Targets are written to Prometheus automatically

### 8.2 Day-2 Instance Configuration (Instances Tab)

To add/update packages on a running instance:

1. Select an instance
2. In **Packages to install**, toggle desired packages
3. Click **Apply configuration**
4. If `node_exporter` is in the list:
   - It installs via Ansible
   - Instance is tagged `monitoring: "enabled"`
   - Targets file is rewritten
   - Prometheus picks up the instance within ~15s

---

## 9. Monitoring Enablement & Instance Tags

### 9.1 How Monitoring Gets Enabled

- **New deployments**: If `node_exporter` is selected, instance is auto-tagged `monitoring: "enabled"`
- **Day-2 config**: If you apply `node_exporter` package to a running instance, tag is auto-set
- **Manual tagging**: (Advanced) Direct DB update or future UI toggle

### 9.2 Instance Tags (Database)

Tags are stored as JSON in the `instances.tags` column. Example:

```json
{
  "Name": "devops-portal-server-1",
  "Environment": "devops-portal",
  "ManagedBy": "DevOpsAutomationPortal",
  "monitoring": "enabled"
}
```

---

## 10. Quick Start Checklist

- [ ] **Section 2**: Create/update `.env` with monitoring vars
- [ ] **Section 3**: Create AWS monitoring security group, copy SG ID
- [ ] **Section 3.2**: Set `PORTAL_MONITORING_SG_ID` in `.env`
- [ ] **Section 4**: Verify `monitoring/` directory structure exists
- [ ] **Section 5**: Grafana auto-provisioning will run on first `docker-compose up`
- [ ] **Section 6**: Prometheus config is ready; no manual edits needed
- [ ] **Section 8**: When deploying, ensure `node_exporter` is selected
- [ ] Start stack: `docker-compose up -d`
- [ ] Verify Prometheus: `http://localhost:9090/targets`
- [ ] Verify Grafana: `http://localhost:3000`
- [ ] Create a test deployment; Monitor button should work after instances are running

---

## 11. Troubleshooting

### Prometheus shows "DOWN" targets

**Symptoms**: `http://localhost:9090/targets` shows instances but state is "DOWN"

**Causes & Fixes**:
1. **Exporters not installed**: Ensure `node_exporter` was in the deployment packages
2. **Security group blocks access**: Check that monitoring SG allows traffic on 9100/8080
3. **Instance IP mismatch**: Verify public/private IP in targets matches actual instance
4. **Firewall on instance**: SSH to instance, check `ss -tuln | grep 9100` — should be listening

### Grafana dashboard has no data

**Symptoms**: Dashboard shows empty graphs

**Causes & Fixes**:
1. **Prometheus datasource unreachable**: In Grafana, go to Datasources → Prometheus → Test. Should say "Data source is working"
2. **Targets not discovered yet**: Wait ~30s after deployment, targets file should update
3. **Metrics not scraped yet**: First scrape takes ~30s. Wait, then refresh dashboard

### Monitor button disabled / "Monitoring is not enabled"

**Symptoms**: Clicking Monitor shows error or button is greyed out

**Causes & Fixes**:
1. **Instance not running**: Monitor requires running state. Start the instance first.
2. **Monitoring tag not set**: Redeploy with `node_exporter` or run day-2 config with `node_exporter` package

### Docker Compose won't start

**Symptoms**: `docker-compose up` fails or containers crash

**Causes & Fixes**:
1. **Missing env vars**: Ensure `.env` exists in `backend/` with all required vars
2. **Port conflicts**: Ensure ports 3000 (Grafana), 9090 (Prometheus) are free
3. **Volume permission issues**: Run `chmod 777 monitoring/` if mount fails

---

## 12. Production Considerations

For production deployments, consider:

1. **Grafana Authentication**: Set up SSO (OIDC, SAML) instead of anonymous access
2. **Prometheus Retention**: Adjust `--storage.tsdb.retention.time` in docker-compose (default: no limit)
3. **Alertmanager**: Add alert rules in `prometheus.yml` and wire to Alertmanager service
4. **TLS/HTTPS**: Place Prometheus/Grafana behind reverse proxy (nginx, Traefik) with SSL certificates
5. **Remote Prometheus**: Move Prometheus to separate EC2 instance for scale
6. **Backup**: Configure persistent volume backups for Prometheus/Grafana data
7. **Network**: Use VPC peering or private endpoint so Prometheus reaches instances on private IPs

---

## 13. Next Steps

1. **Complete the checklist** (Section 10)
2. **Start the stack**: `docker-compose up -d`
3. **Deploy a test instance** from the Portal with `node_exporter`
4. **Monitor the instance** from the Instances tab → click "Monitor"
5. **Verify metrics** are appearing in Grafana dashboard
6. For fine-tuning, see **Troubleshooting** (Section 11)

---

## 14. File References

- Backend env template: [devops-portal/backend/.env.example](../devops-portal/backend/.env.example)
- Docker Compose config: [devops-portal/docker-compose.yml](../devops-portal/docker-compose.yml)
- Prometheus config: [devops-portal/monitoring/prometheus/prometheus.yml](../devops-portal/monitoring/prometheus/prometheus.yml)
- Grafana datasource: [devops-portal/monitoring/grafana/provisioning/datasources/prometheus.yml](../devops-portal/monitoring/grafana/provisioning/datasources/prometheus.yml)
- Grafana dashboard: [devops-portal/monitoring/grafana/dashboards/instance-overview.json](../devops-portal/monitoring/grafana/dashboards/instance-overview.json)
- Terraform generator: [devops-portal/backend/generators/terraform_gen.py](../devops-portal/backend/generators/terraform_gen.py)

---

**Last Updated**: April 20, 2026
