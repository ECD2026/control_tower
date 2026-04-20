import json
import os
from pathlib import Path

from database.db import list_instances


##DEFAULT_TARGETS_PATH = (
    #Path(__file__).resolve().parents[2]
    #/ "monitoring"
    #/ "prometheus"
   # / "targets"
  #  / "instances.json"
##)


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
    return str(tags.get("monitoring", "")).lower() == "enabled"


def rewrite_targets() -> None:
    """Dump running monitored instances to Prometheus file_sd targets file."""
    targets = []

    for inst in list_instances(state="running"):
        if not _monitoring_enabled(inst.get("tags")):
            continue
        host = inst.get("public_ip") or inst.get("private_ip")
        if not host:
            continue
        targets.append(
            {
                "targets": [f"{host}:9100"],
                "labels": {
                    "instance_id": inst.get("id", ""),
                    "region": inst.get("region", ""),
                    "os_type": inst.get("os_type", ""),
                },
            }
        )

    path = _targets_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(targets, indent=2), encoding="utf-8")