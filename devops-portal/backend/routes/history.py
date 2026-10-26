"""
Deployment history routes (scoped to the logged-in user):
  GET /api/history        - 50 most recent deployments
  GET /api/history/{id}   - full record with config and logs
  DELETE /api/history/{id} - delete one finished deployment record
  DELETE /api/history      - delete all of the user's finished records
"""

import json
from fastapi import APIRouter, Depends, HTTPException

from database.db import delete_deployments, get_all_deployments, get_deployment
from services.auth import get_current_user

router = APIRouter()


@router.get("/history")
async def list_deployments(user: dict = Depends(get_current_user)):
    rows = get_all_deployments(user["id"])
    result = []
    for row in rows:
        config = json.loads(row.get("config") or "{}")
        result.append(
            {
                "id": row["id"],
                "name": config.get("name") or "",
                "status": row["status"],
                "mode": config.get("mode", "deploy"),
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
async def get_deployment_detail(deployment_id: str, user: dict = Depends(get_current_user)):
    rec = get_deployment(deployment_id, user["id"])
    if not rec:
        raise HTTPException(status_code=404, detail="Deployment not found")
    rec["config"] = json.loads(rec.get("config") or "{}")
    # The public key is not secret, but there's no reason to echo it back.
    rec["config"].pop("ssh_public_key", None)
    rec["logs"] = json.loads(rec.get("logs") or "[]")
    return rec


@router.delete("/history")
async def clear_history(user: dict = Depends(get_current_user)):
    return {"deleted": delete_deployments(user["id"])}


@router.delete("/history/{deployment_id}")
async def delete_deployment_record(deployment_id: str, user: dict = Depends(get_current_user)):
    rec = get_deployment(deployment_id, user["id"])
    if not rec:
        raise HTTPException(status_code=404, detail="Deployment not found")
    if rec["status"] in ("pending", "running"):
        raise HTTPException(status_code=409, detail="Deployment is still in progress")
    delete_deployments(user["id"], deployment_id)
    return {"deleted": 1}
