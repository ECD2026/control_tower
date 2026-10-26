"""
Writes the Prometheus file_sd targets file for node_exporter scraping.

Only running instances tagged monitoring=enabled (i.e. node_exporter was
installed) are listed. CloudWatch metrics need no target here - they are
collected by the CloudWatch exporter (exporters/cloudwatch_exporter.py) for
every non-terminated instance.

PROMETHEUS_SCRAPE_ADDRESS selects which IP Prometheus dials:
  public  (default) - Prometheus runs outside AWS (e.g. a laptop)
  private           - the portal runs on EC2 in the same VPC; required for
                      the security-group-to-security-group rule that opens
                      port 9100 only to the portal host.
"""

import json
import os
from pathlib import Path

from database.db import list_instances

DEFAULT_TARGETS_PATH = (
    Path(__file__).resolve().parents[2]
    / "monitoring"
    / "prometheus"
    / "targets"
    / "instances.json"
)


def _targets_path() -> Path:
    configured = os.getenv("PROMETHEUS_TARGETS_PATH", "").strip()
    if configured:
        return Path(configured)
    return DEFAULT_TARGETS_PATH


def _monitoring_enabled(raw_tags: str | dict | None) -> bool:
    if isinstance(raw_tags, dict):
        tags = raw_tags
    else:
        try:
            tags = json.loads(raw_tags or "{}")
        except (TypeError, ValueError):
            tags = {}
    if not isinstance(tags, dict):
        return False
    return str(tags.get("monitoring", "")).lower() == "enabled"


def _scrape_host(inst: dict) -> str | None:
    if os.getenv("PROMETHEUS_SCRAPE_ADDRESS", "public").strip().lower() == "private":
        return inst.get("private_ip") or inst.get("public_ip")
    return inst.get("public_ip") or inst.get("private_ip")


def rewrite_targets() -> None:
    """Dump running monitored instances to Prometheus file_sd targets file."""
    targets = []

    for inst in list_instances(state="running"):
        if not _monitoring_enabled(inst.get("tags")):
            continue
        host = _scrape_host(inst)
        if not host:
            continue
        targets.append(
            {
                "targets": [f"{host}:9100"],
                # Same label names as the CloudWatch exporter so Grafana can
                # join both data sources on instance_id.
                "labels": {
                    "instance_id": inst.get("id", ""),
                    "region": inst.get("region", ""),
                    "os_type": inst.get("os_type", ""),
                    "deployment_id": inst.get("deployment_id", ""),
                    "owner": inst.get("user_id") or "",
                    "name": inst.get("name") or "",
                },
            }
        )

    path = _targets_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write-then-rename so Prometheus never reads a half-written file.
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(targets, indent=2), encoding="utf-8")
    os.replace(tmp, path)
