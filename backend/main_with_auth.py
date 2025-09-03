from __future__ import annotations

import logging
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from fastapi.security import HTTPBearer
from pydantic import BaseModel, Field

from scripts.create_manager_with_roles import create_manager_with_roles
from src.api.client_async import LyzrAPIClient
from src.utils.auth import get_current_user  # ✅ JWT-based auth

# -----------------------------
# Logging
# -----------------------------
logger = logging.getLogger("agent-api")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [agent-api] %(message)s",
)

# -----------------------------
# FastAPI App
# -----------------------------
app = FastAPI(title="Agent API", version="1.0")

# -----------------------------
# CORS (⚠️ tighten for production)
# -----------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # TODO: restrict to trusted domains in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()

# -----------------------------
# Schemas
# -----------------------------
class RoleSchema(BaseModel):
    name: str = Field(..., description="Unique role agent name")
    agent_role: str
    agent_goal: str
    agent_instructions: str
    description: Optional[str] = None


class ManagerSchema(BaseModel):
    name: str = Field(..., description="Unique manager agent name")
    agent_role: str
    agent_goal: str
    agent_instructions: str
    description: Optional[str] = None


class CreateAgentsRequest(BaseModel):
    manager_json: ManagerSchema
    roles_json: Optional[List[RoleSchema]] = []
    tz_name: Optional[str] = "America/Los_Angeles"


# -----------------------------
# Healthcheck
# -----------------------------
@app.get("/healthz", response_class=JSONResponse)
async def healthcheck():
    return {"status": "ok"}

# -----------------------------
# Routes
# -----------------------------
@app.post("/create-agents/", response_class=JSONResponse)
async def create_agents(
    body: CreateAgentsRequest,
    user: Dict[str, Any] = Depends(get_current_user),  # ✅ Enforce JWT auth
):
    """
    Create Manager + Role agents from JSON definition.
    """
    logger.info(f"📥 Incoming JSON body keys: {list(body.dict().keys())}")

    # Extract payloads
    manager_json = body.manager_json.dict()
    roles_json = [r.dict() for r in (body.roles_json or [])]
    tz_name = body.tz_name or "America/Los_Angeles"

    async with LyzrAPIClient() as client:
        try:
            result = await create_manager_with_roles(client, manager_json, roles_json)
        except Exception as e:
            logger.exception("❌ Failed to create agents")
            raise HTTPException(status_code=500, detail=str(e))

    return JSONResponse(content=jsonable_encoder({
        "status": "success",
        "result": result,
        "tz_used": tz_name
    }))
