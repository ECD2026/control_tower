from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes.deploy import router as deploy_router
from routes.history import router as history_router
from routes.instances import router as instances_router
from database.db import init_db
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(
    title="DevOps Automation Portal API",
    description="API for provisioning infrastructure and configuring servers automatically",
    version="1.0.0",
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


@app.on_event("startup")
async def startup():
    init_db()


app.include_router(deploy_router, prefix="/api", tags=["deployment"])
app.include_router(history_router, prefix="/api", tags=["history"])
app.include_router(instances_router, prefix="/api", tags=["instances"])


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "DevOps Automation Portal"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
