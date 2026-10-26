"""
GET /api/overview - counts and recent activity for the dashboard landing page.
"""

from collections import Counter

from fastapi import APIRouter, Depends

from database.db import get_all_deployments, list_credentials, list_instances
from services.auth import get_current_user
from services.deployment_execution import get_execution_mode

router = APIRouter()


@router.get("/overview")
async def overview(user: dict = Depends(get_current_user)):
    instances = list_instances(user_id=user["id"])
    deployments = get_all_deployments(user["id"])
    states = Counter(inst.get("state", "unknown") for inst in instances)
    return {
        "execution_mode": get_execution_mode(),
        "credentials": len(list_credentials(user["id"])),
        "instances": {
            "total": sum(v for k, v in states.items() if k != "terminated"),
            "running": states.get("running", 0),
            "stopped": states.get("stopped", 0),
            "transitioning": states.get("pending", 0) + states.get("stopping", 0),
            "terminated": states.get("terminated", 0),
        },
        "deployments": {
            "total": len(deployments),
            "success": sum(1 for d in deployments if d["status"] == "success"),
            "failed": sum(1 for d in deployments if d["status"] == "failed"),
            "running": sum(1 for d in deployments if d["status"] in ("running", "pending")),
        },
        "recent_deployments": [
            {
                "id": d["id"],
                "status": d["status"],
                "region": d["region"],
                "instance_type": d["instance_type"],
                "instances": d["instances"],
                "created_at": d["created_at"],
            }
            for d in deployments[:5]
        ],
    }
