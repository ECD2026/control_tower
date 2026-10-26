"""
FastAPI entry point for the DevOps Automation Portal backend.

Besides the HTTP API this process runs one background task: a periodic EC2
reconcile (RECONCILE_INTERVAL_SECONDS, default 120, 0 disables) so instance
state stays correct even when someone stops/terminates an instance in the AWS
console instead of the portal.
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv

# Load .env before importing modules that read env vars at import time.
load_dotenv()

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from database.db import init_db  # noqa: E402
from routes.auth import router as auth_router  # noqa: E402
from routes.credentials import router as credentials_router  # noqa: E402
from routes.deploy import router as deploy_router  # noqa: E402
from routes.history import router as history_router  # noqa: E402
from routes.instances import router as instances_router  # noqa: E402
from routes.overview import router as overview_router  # noqa: E402
from services.aws_reconciler import reconcile_instances  # noqa: E402

logger = logging.getLogger("devops-portal")


async def _reconcile_forever(interval: int) -> None:
    while True:
        await asyncio.sleep(interval)
        try:
            await reconcile_instances()
        except Exception:
            logger.exception("Background reconcile failed")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    interval = int(os.getenv("RECONCILE_INTERVAL_SECONDS", "120"))
    task = asyncio.create_task(_reconcile_forever(interval)) if interval > 0 else None
    yield
    if task:
        task.cancel()


app = FastAPI(
    title="DevOps Automation Portal API",
    description="API for provisioning infrastructure and configuring servers automatically",
    version="2.0.0",
    lifespan=lifespan,
)

origins = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api", tags=["auth"])
app.include_router(credentials_router, prefix="/api", tags=["credentials"])
app.include_router(overview_router, prefix="/api", tags=["overview"])
app.include_router(deploy_router, prefix="/api", tags=["deployment"])
app.include_router(history_router, prefix="/api", tags=["history"])
app.include_router(instances_router, prefix="/api", tags=["instances"])


@app.get("/health")
@app.get("/api/health")
async def health():
    return {"status": "healthy", "service": "DevOps Automation Portal"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
