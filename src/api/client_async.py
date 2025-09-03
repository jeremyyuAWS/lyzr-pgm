import os
import json
import httpx
import asyncio
import logging
from datetime import datetime
import pytz

from src.utils.payload_normalizer import normalize_payload
from src.utils.normalize_output import canonicalize_name


logger = logging.getLogger("lyzr-client")


# --------------------------------------------------------
# Helpers
# --------------------------------------------------------

def _tz() -> pytz.timezone:
    tz_name = os.getenv("APP_TZ", "America/Los_Angeles")
    try:
        return pytz.timezone(tz_name)
    except Exception:
        return pytz.timezone("America/Los_Angeles")


def _timestamp_str() -> str:
    now = datetime.now(_tz())
    return now.strftime("%d%b%Y-%I:%M%p %Z").upper()


def _suffix_from_id(agent_id: str) -> str:
    return (agent_id or "")[-6:] or "XXXXXX"


def _rich_manager_name(base: str, agent_id: str) -> str:
    return f"{base}_v1.0_{_suffix_from_id(agent_id)}_{_timestamp_str()}"


# --------------------------------------------------------
# Client
# --------------------------------------------------------

class LyzrAPIClient:
    """
    Async client for interacting with the Lyzr Studio API.
    Ensures full payload preservation on updates.
    """

    def __init__(self, base_url=None, api_key=None):
        self.base_url = base_url or os.getenv("STUDIO_API_BASE", "https://agent-prod.studio.lyzr.ai")
        self.api_key = api_key or os.getenv("STUDIO_API_KEY")

    # --------------------------
    # Core HTTP methods
    # --------------------------

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def get(self, path: str):
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{self.base_url}{path}", headers=self._headers())
            return resp.json()

    async def post(self, path: str, payload: dict):
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{self.base_url}{path}", headers=self._headers(), json=payload)
            return resp.json()

    async def put(self, path: str, payload: dict):
        async with httpx.AsyncClient() as client:
            resp = await client.put(f"{self.base_url}{path}", headers=self._headers(), json=payload)
            return resp.json()

    # --------------------------
    # Agent methods
    # --------------------------

    async def create_agent(self, payload: dict):
        logger.info(f"📥 Creating agent: {payload.get('name')}")
        return await self.post("/v3/agents", payload)

    async def update_agent(self, agent_id: str, payload: dict):
        logger.info(f"📤 Updating agent {agent_id} with full payload")
        return await self.put(f"/v3/agents/{agent_id}", payload)

    async def link_agents(
        self,
        manager_id: str,
        role_id: str = None,
        role_name: str = None,
        rename_manager: bool = False,
    ):
        """
        Link a role agent to a manager agent by updating the manager's managed_agents list.
        Always PUT full payload back so no fields are lost.
        """
        logger.info(f"🔗 Linking role {role_id} → manager {manager_id} (rename={rename_manager})")

        # Fetch full manager state
        mgr_resp = await self.get(f"/v3/agents/{manager_id}")
        if not mgr_resp.get("ok"):
            return {"ok": False, "error": f"Failed to fetch manager: {mgr_resp}"}

        manager_data = mgr_resp["data"]
        manager_base_name = manager_data.get("name", "MANAGER")

        # Ensure list
        existing_roles = manager_data.get("managed_agents") or []

        if not rename_manager and role_id:
            # Append new role if not already present
            if not any(r.get("id") == role_id for r in existing_roles):
                existing_roles.append({
                    "id": role_id,
                    "name": role_name or role_id,
                    "usage_description": f"Manager delegates tasks to '{role_name or role_id}'."
                })

        # Compute name
        manager_renamed = manager_base_name
        if rename_manager:
            manager_renamed = _rich_manager_name(manager_base_name, manager_id)

        # Build full update payload (preserve everything)
        update_payload = {**manager_data, "name": manager_renamed, "managed_agents": existing_roles}

        upd_resp = await self.update_agent(manager_id, update_payload)

        if upd_resp.get("ok"):
            return {
                "ok": True,
                "linked": bool(role_id),
                "renamed": manager_renamed if rename_manager else None,
                "manager": upd_resp.get("data"),
                "roles": existing_roles,
                "timestamp": _timestamp_str() if rename_manager else None,
            }
        return {"ok": False, "linked": False, "error": upd_resp.get("error")}

    async def create_manager_with_roles(self, manager_def: dict):
        """
        Create a manager agent and its managed role agents.
        Always PUT full payload back so no fields are lost.
        """
        if not isinstance(manager_def, dict):
            return {"ok": False, "error": "Manager definition must be dict"}

        created_roles = []

        # --- Create roles first ---
        for entry in manager_def.get("managed_agents", []):
            try:
                role_payload = normalize_payload(entry)
                role_resp = await self.create_agent(role_payload)
                if role_resp.get("ok"):
                    role_data = role_resp["data"]
                    created_roles.append(role_data)
                    logger.info(f"✅ Created role: {role_data.get('name')}")
            except Exception as e:
                logger.error(f"❌ Failed to create role: {e}")

        # --- Create manager ---
        try:
            manager_payload = normalize_payload(manager_def)
            mgr_resp = await self.create_agent(manager_payload)
            if not mgr_resp.get("ok"):
                return {"ok": False, "error": mgr_resp.get("error"), "roles": created_roles}

            manager = mgr_resp["data"]

            # --- Link roles if any ---
            if created_roles:
                mgr_fetched = await self.get(f"/v3/agents/{manager.get('id')}")
                if not mgr_fetched.get("ok"):
                    return {"ok": False, "error": f"Failed to fetch created manager: {mgr_fetched}"}

                manager_data = mgr_fetched["data"]
                manager_data["managed_agents"] = (manager_data.get("managed_agents") or []) + created_roles

                # PUT full payload
                upd_resp = await self.update_agent(manager["id"], manager_data)
                if upd_resp.get("ok"):
                    manager = upd_resp["data"]

            return {"ok": True, "manager": manager, "roles": created_roles}

        except Exception as e:
            logger.error(f"❌ Manager creation failed: {e}")
            return {"ok": False, "error": f"Manager creation failed: {e}", "roles": created_roles}
