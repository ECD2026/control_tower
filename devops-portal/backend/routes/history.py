"""
Deployment history routes.
"""

import json
from fastapi import APIRouter, HTTPException

from database.db import get_all_deployments, get_deployment

router = APIRouter()


@router.get("/history")
async def list_deployments():
    rows = get_all_deployments()
    result = []
    for row in rows:
        result.append(
            {
                "id": row["id"],
                "status": row["status"],
                "execution_mode": row.get("execution_mode", "local"),
                "external_ref": row.get("external_ref"),
                "external_url": row.get("external_url"),
                "provider": row["provider"],
                "region": row["region"],
                "instance_type": row["instance_type"],
                "instances": row["instances"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        )
    return result


@router.get("/history/{deployment_id}")
async def get_deployment_detail(deployment_id: str):
    rec = get_deployment(deployment_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Deployment not found")
    rec["config"] = json.loads(rec.get("config") or "{}")
    rec["logs"] = json.loads(rec.get("logs") or "[]")
    return rec
