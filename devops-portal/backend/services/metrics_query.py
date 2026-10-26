"""
Tiny Prometheus HTTP API client used to show live numbers in the portal UI
(the full time-series views are the embedded Grafana dashboards).

PROMETHEUS_URL is the in-cluster address, e.g. http://prometheus:9090/prometheus
(Prometheus is served under /prometheus so nginx can proxy it as-is).
"""

import json
import os
import urllib.parse
import urllib.request
from typing import Dict, Optional

# metric key -> PromQL template. {id} is substituted with the instance id.
# The CloudWatch series come from exporters/cloudwatch_exporter.py; the node_*
# ones only exist when node_exporter is installed on the instance.
INSTANCE_QUERIES: Dict[str, str] = {
    "cpu_percent": 'aws_ec2_cpuutilization_average{{instance_id="{id}"}}',
    "network_in_bytes": 'aws_ec2_network_in_sum{{instance_id="{id}"}}',
    "network_out_bytes": 'aws_ec2_network_out_sum{{instance_id="{id}"}}',
    "status_check_failed": 'aws_ec2_status_check_failed_maximum{{instance_id="{id}"}}',
    "cpu_credit_balance": 'aws_ec2_cpucredit_balance_average{{instance_id="{id}"}}',
    "memory_percent": (
        '100 * (1 - node_memory_MemAvailable_bytes{{instance_id="{id}"}}'
        ' / node_memory_MemTotal_bytes{{instance_id="{id}"}})'
    ),
    "disk_percent": (
        '100 * (1 - node_filesystem_avail_bytes{{instance_id="{id}",mountpoint="/"}}'
        ' / node_filesystem_size_bytes{{instance_id="{id}",mountpoint="/"}})'
    ),
    "node_exporter_up": 'up{{job="node",instance_id="{id}"}}',
}


def _base_url() -> str:
    return os.getenv("PROMETHEUS_URL", "http://localhost:9090/prometheus").rstrip("/")


def query_scalar(promql: str, timeout: float = 5.0) -> Optional[float]:
    """Run an instant query and return the first sample's value (or None)."""
    url = f"{_base_url()}/api/v1/query?" + urllib.parse.urlencode({"query": promql})
    with urllib.request.urlopen(url, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    results = payload.get("data", {}).get("result", [])
    if not results:
        return None
    try:
        return float(results[0]["value"][1])
    except (KeyError, IndexError, ValueError):
        return None


def instance_snapshot(instance_id: str) -> dict:
    """Latest value of each INSTANCE_QUERIES metric; None where no data yet."""
    values: Dict[str, Optional[float]] = {}
    error = None
    for key, template in INSTANCE_QUERIES.items():
        try:
            values[key] = query_scalar(template.format(id=instance_id))
        except Exception as exc:  # Prometheus down/unreachable - report once
            error = f"Prometheus unavailable: {exc}"
            break
    return {"metrics": values, "error": error}
