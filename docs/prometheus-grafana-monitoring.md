# Prometheus + Grafana Monitoring Integration

Plan for adding per-instance monitoring to the DevOps Portal so users can click an
instance in the **Instances** tab and jump straight into a pre-filtered Grafana
dashboard without leaving the portal.

---

## 1. Goals

1. Scrape host-level metrics (CPU, memory, disk, network) from every EC2
   instance the portal provisions.
2. Scrape Docker / container metrics when Docker is installed on the instance.
3. Surface dashboards from the portal UI via a **"Monitor"** button on each
   selected instance — opening the Grafana view filtered to that instance's ID.
4. Keep the stack self-hosted and runnable via `docker-compose` alongside the
   existing backend/frontend services.

---

## 2. High-Level Architecture

```
┌────────────────────────┐    scrape     ┌────────────────────────────┐
│ EC2 instance           │◄──────────────┤  Prometheus                │
│  ├─ node_exporter :9100│               │  (service discovery via    │
│  └─ cadvisor     :8080│               │   file_sd → instances.json)│
└────────────────────────┘               └──────────────┬─────────────┘
                                                        │
                                                        │ PromQL
                                                        ▼
                                          ┌────────────────────────────┐
                                          │  Grafana                   │
                                          │  - dashboards provisioned  │
                                          │  - var: instance_id        │
                                          └──────────────┬─────────────┘
                                                        │ iframe /
                                                        │ redirect
                                                        ▼
                                          ┌────────────────────────────┐
                                          │  DevOps Portal frontend    │
                                          │  (Instances.jsx)           │
                                          └────────────────────────────┘
```

Key choices:

- **Pull model** (Prometheus scrapes exporters on each EC2 instance). Matches
  how Prometheus is normally operated and avoids building a custom push bridge.
- **File-based service discovery** (`file_sd_configs`) written by the backend
  whenever instances change. Simpler than EC2 SD and works even when instances
  run outside AWS in the future.
- **Grafana "Generic OAuth / anonymous read" mode** for the embed so the iframe
  doesn't require the user to sign in separately. (Swap to full SSO later.)

---

## 3. Components To Add

### 3.1 Exporter installation on each instance

Extend the existing Ansible configuration (or the `configure_instance` SSH
runner in [services/instance_configurator.py](devops-portal/backend/services))
to install, on every provisioned instance:

- `node_exporter` (systemd service, port `9100`).
- `cadvisor` as a Docker container (port `8080`) **only if** Docker is among the
  selected packages.

Add two new entries to `PACKAGE_OPTIONS` in
[Instances.jsx:10-17](devops-portal/frontend/src/components/Instances.jsx#L10-L17):

```js
{ id: 'node_exporter', label: 'Node Exporter' },
{ id: 'cadvisor',      label: 'cAdvisor' },
```

Also add them to the default list so every new instance ships with
`node_exporter` preinstalled (monitoring should be opt-out, not opt-in).

### 3.2 Security group

Update the Terraform generator to open ports `9100` and `8080` **only** to the
Prometheus server's private IP / security group — never `0.0.0.0/0`.

- Add a new variable `monitoring_sg_id` to Terraform.
- Generator reads it from env (`PORTAL_MONITORING_SG_ID`) and appends an
  ingress rule sourced from that SG.

### 3.3 Prometheus service

New directory `monitoring/prometheus/`:

```
monitoring/
├── prometheus/
│   ├── prometheus.yml           # static base config
│   └── targets/                 # file_sd targets dir (written by backend)
│       └── instances.json       # generated
├── grafana/
│   ├── provisioning/
│   │   ├── datasources/prometheus.yml
│   │   └── dashboards/dashboards.yml
│   └── dashboards/
│       └── instance-overview.json
└── docker-compose.monitoring.yml
```

`prometheus.yml` skeleton:

```yaml
global:
  scrape_interval: 30s

scrape_configs:
  - job_name: node
    file_sd_configs:
      - files: ['/etc/prometheus/targets/instances.json']
        refresh_interval: 15s
    relabel_configs:
      - source_labels: [__address__]
        regex: '(.*):.*'
        target_label: instance_host
      - source_labels: [instance_id]
        target_label: instance
```

`instances.json` (written by the backend) looks like:

```json
[
  {
    "targets": ["54.12.34.56:9100"],
    "labels": {
      "instance_id": "i-0abc...",
      "region": "ap-south-1",
      "os_type": "amazon_linux"
    }
  }
]
```

### 3.4 Grafana service

Provision:

- A Prometheus datasource pointing at `http://prometheus:9090`.
- One main dashboard `instance-overview.json` with a **template variable**
  `instance` (values from `label_values(node_uname_info, instance)`), so every
  panel auto-filters by the selected instance.
- Anonymous viewer role enabled (`GF_AUTH_ANONYMOUS_ENABLED=true`,
  `GF_AUTH_ANONYMOUS_ORG_ROLE=Viewer`).
- Embedding enabled (`GF_SECURITY_ALLOW_EMBEDDING=true`,
  `GF_SECURITY_COOKIE_SAMESITE=none`).

### 3.5 docker-compose additions

Extend [devops-portal/docker-compose.yml](devops-portal/docker-compose.yml)
(or add `docker-compose.monitoring.yml` and merge via `-f`):

```yaml
services:
  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./monitoring/prometheus:/etc/prometheus
      - prom-data:/prometheus
    ports: ['9090:9090']

  grafana:
    image: grafana/grafana:latest
    environment:
      - GF_AUTH_ANONYMOUS_ENABLED=true
      - GF_AUTH_ANONYMOUS_ORG_ROLE=Viewer
      - GF_SECURITY_ALLOW_EMBEDDING=true
    volumes:
      - ./monitoring/grafana/provisioning:/etc/grafana/provisioning
      - ./monitoring/grafana/dashboards:/var/lib/grafana/dashboards
      - graf-data:/var/lib/grafana
    ports: ['3000:3000']

volumes:
  prom-data:
  graf-data:
```

---

## 4. Backend Changes

### 4.1 Target file writer

New module `backend/services/prometheus_targets.py` with:

```python
def rewrite_targets() -> None:
    """Dump all running instances to monitoring/prometheus/targets/instances.json."""
```

Call `rewrite_targets()` from:

- `configure_instance` after a successful `node_exporter` install.
- `start_instance`, `stop_instance`, `delete_instance` in
  [routes/instances.py](devops-portal/backend/routes/instances.py).
- `reconcile_instances` once per run.

Only include instances whose `state == "running"` and where monitoring is
enabled (flag stored in the `instances.tags` JSON column, e.g.
`{"monitoring": "enabled"}`).

### 4.2 New endpoint: monitoring URL resolver

`GET /api/instances/{instance_id}/monitoring` →

```json
{
  "enabled": true,
  "grafana_url": "http://localhost:3000/d/instance-overview/instance-overview?var-instance=i-0abc&kiosk",
  "prometheus_url": "http://localhost:9090/graph?g0.expr=up{instance_id=\"i-0abc\"}"
}
```

Base URL and dashboard UID configurable via env
(`GRAFANA_PUBLIC_URL`, `GRAFANA_DASHBOARD_UID`).

### 4.3 Config

Add to `.env.example`:

```
GRAFANA_PUBLIC_URL=http://localhost:3000
GRAFANA_DASHBOARD_UID=instance-overview
PROMETHEUS_TARGETS_PATH=/app/monitoring/prometheus/targets/instances.json
PORTAL_MONITORING_SG_ID=sg-xxxxxxxx
```

---

## 5. Frontend Changes

All changes are in
[Instances.jsx](devops-portal/frontend/src/components/Instances.jsx).

### 5.1 "Monitor" action button

In the action row at
[Instances.jsx:342-376](devops-portal/frontend/src/components/Instances.jsx#L342-L376),
add a 4th button:

```jsx
<button
  type="button"
  onClick={() => openMonitoring(selected)}
  disabled={selected.state !== 'running'}
  className="btn-ghost justify-center py-2"
  title="Open Grafana dashboard for this instance"
>
  <Activity size={14} />
  Monitor
</button>
```

Switch the grid from `grid-cols-3` to `grid-cols-4`.

### 5.2 `openMonitoring` behaviour — two modes

Configurable via a small toggle at the top of the component
(`const EMBED_GRAFANA = true`):

**Mode A — In-page embed (recommended):**
Replace the right-hand "Configure" pane (or add a tab) with an `<iframe>`
pointing at the Grafana URL returned by the new API. Pass
`&kiosk=tv&theme=dark` to hide Grafana's chrome so it blends into the portal.

**Mode B — Redirect / new tab:**
`window.open(grafana_url, '_blank')`. Simpler, no iframe/CSP concerns, but
leaves the portal.

Start with **Mode B** behind a feature flag while validating the Grafana
provisioning, then switch the default to **Mode A** once embedding works.

### 5.3 State additions

```js
const [monitoring, setMonitoring] = useState(null) // { grafana_url, enabled }

const openMonitoring = async (inst) => {
  const res = await fetch(`${API}/api/instances/${inst.id}/monitoring`)
  if (!res.ok) return
  const data = await res.json()
  if (EMBED_GRAFANA) setMonitoring(data)
  else window.open(data.grafana_url, '_blank', 'noopener')
}
```

When `monitoring` is set, render a collapsible Grafana panel above the Output
logs. Include a close button that clears `monitoring`.

---

## 6. Rollout Plan

| Phase | Scope | Deliverable |
| ----- | ----- | ----------- |
| **M1** | Stack up | `docker-compose up` starts Prometheus + Grafana with empty targets; Grafana loads the provisioned dashboard. |
| **M2** | Agents | `node_exporter` + `cadvisor` roles added to Ansible; new packages selectable from UI; SG opens 9100/8080 to the Prometheus SG only. |
| **M3** | Discovery | Backend writes `instances.json` on configure/start/stop/delete/reconcile. Prometheus auto-picks up new targets within 15s. |
| **M4** | UI | "Monitor" button wired to `/api/instances/{id}/monitoring` in redirect mode. |
| **M5** | Embed | Iframe embed, kiosk mode, CSP tuning, anonymous viewer auth. |
| **M6** | Hardening | Alerts (Alertmanager), retention policy, Grafana behind auth proxy, TLS. |

---

## 7. Open Questions

1. **Where does Prometheus live?** Same box as the portal backend, or its own
   EC2 instance? Same-box is fine for the demo; prod should separate them.
2. **Remote access to exporters** — do we route scrapes via the instance's
   public IP, or set up a VPN / VPC peering so Prometheus reaches private IPs?
   Public IP is simpler; private is safer.
3. **Authentication** — anonymous Grafana is a demo shortcut. For real use,
   wire Grafana to the same identity provider as the portal (OIDC / proxy
   auth) and drop the anonymous role.
4. **Retention** — default 15d is probably enough; revisit once we see disk
   usage.
5. **Multi-region scrape latency** — Prometheus in `ap-south-1` scraping
   instances in `us-east-1` will have 200ms+ RTT. Acceptable at 30s interval;
   reconsider at sub-15s.

---

## 8. Files Expected to Change

- New: `monitoring/` tree (Prometheus + Grafana config & dashboards).
- New: `backend/services/prometheus_targets.py`.
- Edit: [backend/routes/instances.py](devops-portal/backend/routes/instances.py)
  — add `/monitoring` endpoint; call `rewrite_targets` on state transitions.
- Edit: `backend/services/instance_configurator.py` — install exporters.
- Edit: `backend/generators/terraform_gen.py` — monitoring SG ingress.
- Edit: `backend/.env.example` — new vars.
- Edit: [frontend/src/components/Instances.jsx](devops-portal/frontend/src/components/Instances.jsx)
  — Monitor button, optional iframe panel, new package options.
- Edit: [devops-portal/docker-compose.yml](devops-portal/docker-compose.yml)
  — Prometheus + Grafana services.
- Edit: [docs/README.md](docs/README.md) — index this document.
