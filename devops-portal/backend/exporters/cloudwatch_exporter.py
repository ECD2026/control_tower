"""
Multi-account CloudWatch exporter for portal-managed EC2 instances.

Run:  python -m exporters.cloudwatch_exporter      (from devops-portal/backend)
Serves Prometheus metrics on :9106 (CLOUDWATCH_EXPORTER_PORT).

Why not the stock prom/cloudwatch-exporter image? It reads one AWS credential
chain per process and a static list of metrics/dimensions. Portal users each
bring their own AWS keys, and instances come and go, so this exporter:

  1. reads the portal DB for every non-terminated instance and the credential
     that owns it,
  2. every CLOUDWATCH_REFRESH_SECONDS (default 60) issues batched
     GetMetricData calls per (credential, region),
  3. serves the latest datapoint of each metric from an in-memory snapshot,
     so Prometheus scrapes are fast and never hit the AWS API directly.

Metric names follow the official exporter's convention,
aws_<namespace>_<metric_snake_case>_<statistic>, e.g.
aws_ec2_cpuutilization_average, so existing dashboards/queries carry over.
Labels: instance_id, name, region, instance_type, deployment_id, owner,
account_id.
"""

import logging
import os
import re
import sys
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Allow `python exporters/cloudwatch_exporter.py` as well as `-m`.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from prometheus_client import start_http_server  # noqa: E402
from prometheus_client.core import (  # noqa: E402
    CounterMetricFamily,
    GaugeMetricFamily,
    REGISTRY,
)

from database.db import get_credential, init_db, list_instances  # noqa: E402
from services.aws_clients import session_for_credential  # noqa: E402

logger = logging.getLogger("cloudwatch-exporter")

# (CloudWatch metric name, statistic). All in the AWS/EC2 namespace with the
# InstanceId dimension. EBS* metrics are published for Nitro instance types;
# CPUCredit* only for burstable (t2/t3/t4g) types - missing ones are skipped.
EC2_METRICS: List[Tuple[str, str]] = [
    ("CPUUtilization", "Average"),
    ("CPUUtilization", "Maximum"),
    ("NetworkIn", "Sum"),
    ("NetworkOut", "Sum"),
    ("NetworkPacketsIn", "Sum"),
    ("NetworkPacketsOut", "Sum"),
    ("EBSReadBytes", "Sum"),
    ("EBSWriteBytes", "Sum"),
    ("EBSReadOps", "Sum"),
    ("EBSWriteOps", "Sum"),
    ("StatusCheckFailed", "Maximum"),
    ("StatusCheckFailed_Instance", "Maximum"),
    ("StatusCheckFailed_System", "Maximum"),
    ("CPUCreditBalance", "Average"),
    ("CPUCreditUsage", "Sum"),
]

LABELS = ["instance_id", "name", "region", "instance_type", "deployment_id", "owner", "account_id"]

# GetMetricData accepts at most 500 queries per request.
MAX_QUERIES_PER_CALL = 500


def snake_case(name: str) -> str:
    """Same conversion as the official exporter: CPUUtilization -> cpuutilization."""
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name).lower()


def metric_name(metric: str, stat: str) -> str:
    return f"aws_ec2_{snake_case(metric)}_{stat.lower()}"


class Snapshot:
    """Latest values, swapped atomically after each refresh."""

    def __init__(self) -> None:
        # metric family name -> list of (label values, value)
        self.values: Dict[str, List[Tuple[List[str], float]]] = defaultdict(list)
        self.instances: List[Tuple[List[str], str]] = []  # (labels, state)
        self.refreshed_at: float = 0.0
        self.duration: float = 0.0


class CloudWatchCollector:
    def __init__(self) -> None:
        self._snapshot = Snapshot()
        self._lock = threading.Lock()
        self.api_requests: Dict[Tuple[str, str], int] = defaultdict(int)
        self.api_errors: Dict[Tuple[str, str], int] = defaultdict(int)

    # ---------- refresh (background thread) ----------

    def refresh(self) -> None:
        started = time.time()
        snapshot = Snapshot()

        groups: Dict[Tuple[Optional[str], str], List[dict]] = defaultdict(list)
        for inst in list_instances(exclude_terminated=True):
            groups[(inst.get("credential_id"), inst.get("region") or "us-east-1")].append(inst)

        for (credential_id, region), instances in groups.items():
            credential = get_credential(credential_id) if credential_id else None
            account_id = (credential or {}).get("account_id") or ""
            labels_by_id = {
                inst["id"]: [
                    inst["id"],
                    inst.get("name") or "",
                    region,
                    inst.get("instance_type") or "",
                    inst.get("deployment_id") or "",
                    inst.get("user_id") or "",
                    account_id,
                ]
                for inst in instances
            }
            for inst in instances:
                snapshot.instances.append((labels_by_id[inst["id"]], inst.get("state", "unknown")))

            # Stopped instances publish no datapoints; skip the API cost.
            active_ids = [
                i["id"] for i in instances if i.get("state") in ("running", "pending", "stopping")
            ]
            if not active_ids:
                continue
            try:
                self._fetch_group(credential, region, active_ids, labels_by_id, snapshot)
            except Exception:
                self.api_errors[(account_id, region)] += 1
                logger.exception("CloudWatch fetch failed for account=%s region=%s",
                                 account_id or "default", region)

        snapshot.refreshed_at = time.time()
        snapshot.duration = snapshot.refreshed_at - started
        with self._lock:
            self._snapshot = snapshot

    def _fetch_group(
        self,
        credential: Optional[dict],
        region: str,
        instance_ids: List[str],
        labels_by_id: Dict[str, List[str]],
        snapshot: Snapshot,
    ) -> None:
        client = session_for_credential(credential, region).client("cloudwatch")
        account_id = (credential or {}).get("account_id") or ""
        end = datetime.now(timezone.utc)
        # 20 minutes covers basic (5-minute) monitoring plus CloudWatch's
        # ingestion delay; we keep only the newest datapoint per series.
        start = end - timedelta(minutes=20)

        queries = []
        index: Dict[str, Tuple[str, str]] = {}  # query id -> (family, instance_id)
        for n, instance_id in enumerate(instance_ids):
            for m, (metric, stat) in enumerate(EC2_METRICS):
                query_id = f"q{n}_{m}"
                index[query_id] = (metric_name(metric, stat), instance_id)
                queries.append(
                    {
                        "Id": query_id,
                        "MetricStat": {
                            "Metric": {
                                "Namespace": "AWS/EC2",
                                "MetricName": metric,
                                "Dimensions": [{"Name": "InstanceId", "Value": instance_id}],
                            },
                            # 60s works for detailed monitoring; CloudWatch
                            # simply returns 5-minute points for basic.
                            "Period": 60,
                            "Stat": stat,
                        },
                        "ReturnData": True,
                    }
                )

        for offset in range(0, len(queries), MAX_QUERIES_PER_CALL):
            batch = queries[offset:offset + MAX_QUERIES_PER_CALL]
            next_token = None
            while True:
                kwargs = {
                    "MetricDataQueries": batch,
                    "StartTime": start,
                    "EndTime": end,
                    "ScanBy": "TimestampDescending",
                }
                if next_token:
                    kwargs["NextToken"] = next_token
                self.api_requests[(account_id, region)] += 1
                response = client.get_metric_data(**kwargs)
                for result in response.get("MetricDataResults", []):
                    values = result.get("Values") or []
                    if not values:
                        continue
                    family, instance_id = index[result["Id"]]
                    # TimestampDescending -> values[0] is the newest point.
                    snapshot.values[family].append((labels_by_id[instance_id], float(values[0])))
                next_token = response.get("NextToken")
                if not next_token:
                    break

    # ---------- collect (Prometheus scrape) ----------

    def collect(self):
        with self._lock:
            snapshot = self._snapshot

        for metric, stat in EC2_METRICS:
            family_name = metric_name(metric, stat)
            family = GaugeMetricFamily(
                family_name,
                f"CloudWatch metric {metric} Dimensions: [InstanceId] Statistic: {stat}",
                labels=LABELS,
            )
            for labels, value in snapshot.values.get(family_name, []):
                family.add_metric(labels, value)
            yield family

        info = GaugeMetricFamily(
            "aws_ec2_instance_info",
            "Portal-managed EC2 instance, 1 per instance; `state` is the portal state",
            labels=LABELS + ["state"],
        )
        running = GaugeMetricFamily(
            "aws_ec2_instance_running",
            "1 when the instance is running, 0 when paused/stopped or transitioning",
            labels=LABELS,
        )
        for labels, state in snapshot.instances:
            info.add_metric(labels + [state], 1)
            running.add_metric(labels, 1 if state == "running" else 0)
        yield info
        yield running

        requests = CounterMetricFamily(
            "cloudwatch_requests",
            "GetMetricData API calls made by this exporter",
            labels=["account_id", "region"],
        )
        for (account_id, region), count in list(self.api_requests.items()):
            requests.add_metric([account_id, region], count)
        yield requests

        errors = CounterMetricFamily(
            "cloudwatch_exporter_errors",
            "Refresh failures per account/region (bad keys, throttling, ...)",
            labels=["account_id", "region"],
        )
        for (account_id, region), count in list(self.api_errors.items()):
            errors.add_metric([account_id, region], count)
        yield errors

        yield GaugeMetricFamily(
            "cloudwatch_exporter_last_refresh_timestamp_seconds",
            "Unix time of the last completed CloudWatch refresh",
            value=snapshot.refreshed_at,
        )
        yield GaugeMetricFamily(
            "cloudwatch_exporter_refresh_duration_seconds",
            "How long the last CloudWatch refresh took",
            value=snapshot.duration,
        )


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    init_db()  # make sure tables exist if the exporter starts first

    port = int(os.getenv("CLOUDWATCH_EXPORTER_PORT", "9106"))
    interval = int(os.getenv("CLOUDWATCH_REFRESH_SECONDS", "60"))

    collector = CloudWatchCollector()
    REGISTRY.register(collector)
    start_http_server(port)
    logger.info("Serving CloudWatch metrics on :%d (refresh every %ds)", port, interval)

    while True:
        try:
            collector.refresh()
        except Exception:
            logger.exception("Refresh loop failed")
        time.sleep(interval)


if __name__ == "__main__":
    main()
