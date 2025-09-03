# src/api/client_async.py

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

# -----------------------------
# Timezone utilities
# -----------------------------
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


# -----------------------------
# Client
# -----------------------------
class LyzrAPIClient:
    """
    Async client for interacting with the Lyzr Studio API.
    Ensures full payload PUT on update to avoid field loss.
    """

    def __init__(self, base_url: str | None = None, api_key: str | None = None, timeout: int = 30):
        self.base_url = base_url or os.getenv("STUDIO_API_URL", "https://agent-prod.studio.lyzr.ai")
        self.api_key = api_key or os.getenv("STUDIO_API_KEY")
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    # --- Context manager support ---
    async def __aenter__(self):
        # 👇 enable redirect following globally
        self._client = httpx.AsyncClient(timeout=self.timeout, follow_redirects=True)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._client:
            await self._client.aclose()

    # --- Core HTTP helpers ---
    async def get(self, path: str):
        url = self._normalize_url(path)
        try:
            resp = await self._client.get(url, headers=self._headers())
            return self._handle_response(resp)
        except Exception as e:
            logger.error(f"❌ GET {url} failed: {e}")
            return {"ok": False, "error": str(e)}

    async def post(self, path: str, payload: dict):
        url = self._normalize_url(path)
        try:
            resp = await self._client.post(url, headers=self._headers(), json=payload)
            return self._handle_response(resp)
        except Exception as e:
            logger.error(f"❌ POST {url} failed: {e}")
            return {"ok": False, "error": str(e)}

    async def put(self, path: str, payload: dict):
        url = self._normalize_url(path)
        try:
            resp = await self._client.put(url, headers=self._headers(), json=payload)
            return self._handle_response(resp)
        except Exception as e:
            logger.error(f"❌ PUT {url} failed: {e}")
            return {"ok": False, "error": str(e)}

    # --- API Wrappers ---
    async def create_agent(self, payload: dict):
        # 👇 always use trailing slash
        return await self.post("/v3/agents/", payload)

    async def update_agent(self, agent_id: str, payload: dict):
        return await self.put(f"/v3/agents/{agent_id}/", payload)

    # --- Linking + Orchestration ---
    async def link_agents(self, manager_id: str, role_id: str = None, role_name: str = None, rename_manager: bool = False):
        """
        Link a role agent to a manager agent by updating the manager's managed_agents list.
        Always PUT full payload back so no fields are lost.
        """
        mgr_resp = await self.get(f"/v3/agents/{manager_id}/")
        if not mgr_resp.get("ok"):
            return {"ok": False, "error": f"Failed to fetch manager: {mgr_resp}"}

        manager_data = mgr_resp["data"]
        manager_base_name = manager_data.get("name", "MANAGER")
        existing_roles = manager_data.get("managed_agents") or []

        if not rename_manager and role_id:
            if not any(r.get("id") == role_id for r in existing_roles):
                existing_roles.append({
                    "id": role_id,
                    "name": role_name or role_id,
                    "usage_description": f"Manager delegates tasks to '{role_name or role_id}'."
                })

        manager_renamed = manager_base_name
        if rename_manager:
            manager_renamed = _rich_manager_name(manager_base_name, manager_id)

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

        # 1. Create roles
        for entry in manager_def.get("managed_agents", []):
            try:
                role_payload = normalize_payload(entry)
                role_resp = await self.create_agent(role_payload)
                if role_resp.get("ok"):
                    created_roles.append(role_resp["data"])
            except Exception as e:
                logger.error(f"❌ Failed to create role: {e}")

        try:
            # 2. Create manager
            manager_payload = normalize_payload(manager_def)
            mgr_resp = await self.create_agent(manager_payload)
            if not mgr_resp.get("ok"):
                return {"ok": False, "error": mgr_resp.get("error"), "roles": created_roles}

            manager = mgr_resp["data"]

            # 3. Link roles back into manager
            if created_roles:
                mgr_fetched = await self.get(f"/v3/agents/{manager['id']}/")
                if not mgr_fetched.get("ok"):
                    return {"ok": False, "error": f"Failed to fetch created manager: {mgr_fetched}"}

                manager_data = mgr_fetched["data"]
                manager_data["managed_agents"] = (manager_data.get("managed_agents") or []) + created_roles

                upd_resp = await self.update_agent(manager["id"], manager_data)
                if upd_resp.get("ok"):
                    manager = upd_resp["data"]

            return {"ok": True, "manager": manager, "roles": created_roles}
        except Exception as e:
            return {"ok": False, "error": f"Manager creation failed: {e}", "roles": created_roles}

    # --- Helpers ---
    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _normalize_url(self, path: str) -> str:
        """Ensure trailing slash consistency on API paths."""
        if not path.endswith("/"):
            path = path + "/"
        return f"{self.base_url}{path}"

    def _handle_response(self, resp: httpx.Response):
        try:
            resp.raise_for_status()
            return {"ok": True, "data": resp.json()}
        except Exception as e:
            logger.error(f"❌ API error {resp.status_code}: {e}")
            try:
                return {"ok": False, "error": resp.json()}
            except Exception:
                return {"ok": False, "error": str(e)}
