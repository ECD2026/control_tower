"""
API-level tests for auth, credentials, deployments and instance isolation.

AWS is never contacted: STS verification and the deployment runner are
monkeypatched. Run from devops-portal/backend:

    pip install pytest httpx
    python -m pytest -q
"""

import importlib
import json
import sys
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # Fresh DB + keys per test; modules read DB_PATH at import time.
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("PORTAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("PORTAL_WORKFLOW_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("PORTAL_JWT_SECRET", "test-secret")
    monkeypatch.setenv("PROMETHEUS_TARGETS_PATH", str(tmp_path / "targets.json"))
    monkeypatch.setenv("RECONCILE_INTERVAL_SECONDS", "0")
    monkeypatch.setenv("DEPLOYMENT_RUNNER_MODE", "local")

    for name in list(sys.modules):
        if name.split(".")[0] in {"database", "services", "routes", "main", "models", "generators"}:
            del sys.modules[name]
    main = importlib.import_module("main")

    import routes.credentials as credentials_routes

    monkeypatch.setattr(
        credentials_routes,
        "verify_access_keys",
        lambda key, secret, region: {
            "account_id": "123456789012",
            "arn": "arn:aws:iam::123456789012:user/test",
        },
    )

    from fastapi.testclient import TestClient

    with TestClient(main.app) as test_client:
        yield test_client


def _register(client, email="alice@example.com"):
    res = client.post("/api/auth/register", json={"email": email, "password": "correct-horse"})
    assert res.status_code == 200, res.text
    return res.json()


def _add_credential(client, generate=True):
    res = client.post(
        "/api/credentials",
        json={
            "name": "sandbox",
            "access_key_id": "AKIAABCDEFGHIJKLMNOP",
            "secret_access_key": "x" * 40,
            "default_region": "ap-south-1",
            "key_pair_name": "portal-key",
            "generate_key_pair": generate,
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_auth_flow(client):
    assert client.get("/api/auth/me").status_code == 401
    user = _register(client)
    assert client.get("/api/auth/me").json()["email"] == user["email"]
    assert client.get("/api/auth/verify").status_code == 204

    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401
    bad = client.post("/api/auth/login", json={"email": user["email"], "password": "wrong-pass"})
    assert bad.status_code == 401
    good = client.post("/api/auth/login", json={"email": user["email"], "password": "correct-horse"})
    assert good.status_code == 200


def test_credentials_are_encrypted_and_masked(client):
    _register(client)
    cred = _add_credential(client)
    assert cred["access_key_id"].startswith("AKIA") and "*" in cred["access_key_id"]
    assert "OPENSSH PRIVATE KEY" in cred["generated_private_key"]
    assert cred["ssh_public_key"].startswith("ssh-ed25519 ")

    listed = client.get("/api/credentials").json()
    assert len(listed) == 1
    assert "generated_private_key" not in listed[0]
    assert "secret_access_key" not in json.dumps(listed)

    from database.db import get_credential

    row = get_credential(cred["id"])
    assert "x" * 40 not in row["secret_access_key_enc"]


def test_uploaded_pem_derives_public_key(client):
    _register(client)
    from services.aws_clients import generate_ssh_key_pair

    private_pem, public_key = generate_ssh_key_pair()
    res = client.post(
        "/api/credentials",
        json={
            "name": "uploaded",
            "access_key_id": "AKIAABCDEFGHIJKLMNOP",
            "secret_access_key": "y" * 40,
            "key_pair_name": "my-key",
            "ssh_private_key": private_pem,
        },
    )
    assert res.status_code == 201, res.text
    assert res.json()["ssh_public_key"] == public_key
    assert "generated_private_key" not in res.json()


def test_plan_requires_credential_and_uses_it(client, monkeypatch):
    _register(client)
    assert client.post("/api/plan", json={"region": "ap-south-1"}).status_code == 400

    cred = _add_credential(client)
    seen = {}

    async def fake_run(**kwargs):
        from services.execution_types import ExecutionResult

        seen.update(kwargs)
        return ExecutionResult(status="success", execution_mode="local")

    import routes.deploy as deploy_routes

    monkeypatch.setattr(deploy_routes, "run_requested_deployment", fake_run)
    res = client.post(
        "/api/plan",
        json={"credential_id": cred["id"], "region": "ap-south-1", "name": "Web Tier"},
    )
    assert res.status_code == 200, res.text
    deployment_id = res.json()["deployment_id"]

    # The request is rewritten server-side with the credential's key pair.
    assert seen["request"].key_pair_name == "portal-key"
    assert seen["request"].deployment_id == deployment_id
    assert seen["credential"]["id"] == cred["id"]

    history = client.get("/api/history").json()
    assert history[0]["id"] == deployment_id and history[0]["mode"] == "plan"
    assert client.get(f"/api/deploy/{deployment_id}/status").json()["status"] == "success"


def test_users_cannot_see_each_others_instances(client):
    alice = _register(client, "alice@example.com")
    from database.db import save_deployment, save_instance

    save_deployment("dep-1", {"region": "ap-south-1"}, user_id=alice["id"])
    save_instance({"id": "i-alice", "deployment_id": "dep-1", "region": "ap-south-1"})
    assert [i["id"] for i in client.get("/api/instances").json()] == ["i-alice"]

    client.post("/api/auth/logout")
    _register(client, "bob@example.com")
    assert client.get("/api/instances").json() == []
    assert client.get("/api/instances/i-alice").status_code == 404
    assert client.post("/api/instances/i-alice/stop").status_code == 404


def test_delete_history_is_per_user_and_keeps_running(client):
    alice = _register(client, "alice@example.com")
    from database.db import save_deployment, save_instance, update_deployment_status

    for dep in ("done-1", "done-2", "live-1"):
        save_deployment(dep, {"region": "ap-south-1"}, user_id=alice["id"])
    update_deployment_status("done-1", "success")
    update_deployment_status("done-2", "failed")
    update_deployment_status("live-1", "running")
    save_instance({"id": "i-alice", "deployment_id": "done-1", "region": "ap-south-1"})

    client.post("/api/auth/logout")
    _register(client, "bob@example.com")
    assert client.delete("/api/history/done-1").status_code == 404
    assert client.delete("/api/history").json() == {"deleted": 0}

    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "alice@example.com", "password": "correct-horse"})
    assert client.delete("/api/history/live-1").status_code == 409
    assert client.delete("/api/history/done-1").json() == {"deleted": 1}
    assert client.delete("/api/history").json() == {"deleted": 1}
    assert [h["id"] for h in client.get("/api/history").json()] == ["live-1"]
    assert [i["id"] for i in client.get("/api/instances").json()] == ["i-alice"]


def test_terraform_naming_and_tags():
    from generators.terraform_gen import generate_terraform
    from models.schemas import DeploymentRequest

    tf = generate_terraform(
        DeploymentRequest(
            deployment_id="0123456789abcdef",
            name="Web Tier",
            region="ap-south-1",
            key_pair_name="portal-key",
            ssh_public_key="ssh-ed25519 AAAATEST user",
            packages=["node_exporter"],
        )
    )
    assert 'name_prefix = "devops-portal-01234567-sg-"' in tf
    assert 'key_name_prefix = "devops-portal-01234567-portal-key-"' in tf
    assert 'Name        = "web-tier-${count.index + 1}"' in tf
    assert 'PortalDeploymentId = "0123456789abcdef"' in tf
    assert 'monitoring  = "enabled"' in tf
    assert "monitoring = true" in tf


def test_workflow_bundle_roundtrip(monkeypatch, tmp_path):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("PORTAL_WORKFLOW_KEY", key)
    from services import crypto

    crypto._workflow_fernet.cache_clear()
    sealed = crypto.seal_for_workflow({"aws_access_key_id": "AKIA1", "aws_secret_access_key": "s"})
    assert "AKIA1" not in sealed
    assert crypto.open_workflow_bundle(sealed, key)["aws_secret_access_key"] == "s"


def test_exporter_metric_names_match_official_exporter():
    from exporters.cloudwatch_exporter import metric_name

    assert metric_name("CPUUtilization", "Average") == "aws_ec2_cpuutilization_average"
    assert metric_name("NetworkIn", "Sum") == "aws_ec2_network_in_sum"
    assert metric_name("StatusCheckFailed_System", "Maximum") == (
        "aws_ec2_status_check_failed_system_maximum"
    )
    assert metric_name("CPUCreditBalance", "Average") == "aws_ec2_cpucredit_balance_average"
