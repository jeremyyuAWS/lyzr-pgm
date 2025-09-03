from __future__ import annotations

import os
import logging
import json
from pathlib import Path
from typing import Dict, Any

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from fastapi.security import HTTPBearer

import asyncio

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
# Routes
# -----------------------------
@app.post("/create-agents/", response_class=JSONResponse)
async def create_agents(
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),  # ✅ Enforce JWT auth
):
    """
    Create Manager + Role agents from JSON definition.

    Request Contract (JSON only):
    {
      "id": "...",                 # Optional: agent_id
      "name": "...",               # Required: base name
      "description": "...",        # Optional
      "agent_role": "...",         # Required
      "agent_goal": "...",         # Required
      "agent_instructions": "...", # Required
      "managed_agents": [          # Optional list of role agents
        {
          "yaml": { ...role_def... }
        }
      ]
    }
    """
    # Enforce JSON-only
    if request.headers.get("content-type") != "application/json":
        raise HTTPException(
            status_code=415, detail="Content-Type must be application/json"
        )

    # Parse JSON body
    try:
        body = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")

    if not isinstance(body, dict):
        raise HTTPException(
            status_code=400, detail="Request body must be a JSON object"
        )

    logger.info(f"📥 Incoming JSON body keys: {list(body.keys())}")

    # Create manager + roles
    async with LyzrAPIClient(debug=True) as client:
        try:
            result = await create_manager_with_roles(client, body)
        except Exception as e:
            logger.exception("❌ Failed to create agents")
            raise HTTPException(status_code=502, detail=str(e))

    return JSONResponse(content=jsonable_encoder(result))
