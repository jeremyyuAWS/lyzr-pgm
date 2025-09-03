# src/api/client_async.py

import os
import json
import yaml
import httpx
import asyncio
from pathlib import Path

from src.utils.payload_normalizer import normalize_payload
from src.utils.normalize_output import normalize_inference_output, canonicalize_name


class LyzrAPIClient:
    def __init__(self, api_key: str = None, debug: bool = None, timeout: int = 300, retries: int = 3):
        self.base_url = os.getenv("LYZR_BASE_URL", "https://agent-prod.studio.lyzr.ai")

        # Use provided key OR fallback to env
        self.api_key = api_key or os.getenv("LYZR_API_KEY")
        if not self.api_key:
            raise ValueError("No API key provided (api_key argument or LYZR_API_KEY env required)")

        self.headers = {"x-api-key": self.api_key, "Content-Type": "application/json"}
        self.timeout = timeout
        self.retries = retries

        # ✅ Async client (non-blocking)
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(self.timeout))

        # Debug mode
        if debug is None:
            self.debug = os.getenv("LYZR_DEBUG", "0") == "1"
        else:
            self.debug = debug

    # -----------------
    # Logging
    # -----------------
    def _log(self, *args):
        if self.debug:
            print(*args, flush=True)

    # -----------------
    # Lifecycle methods
    # -----------------
    async def aclose(self):
        if self.client:
            await self.client.aclose()

    def close(self):
        """Sync close (for cleanup outside async contexts)."""
        if self.client:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Fire and forget in running loop
                    loop.create_task(self.aclose())
                else:
                    loop.run_until_complete(self.aclose())
            except RuntimeError:
                # No running loop
                asyncio.run(self.aclose())

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.aclose()

    # -----------------
    # Validation helpers
    # -----------------
    def _validate_agent_payload(self, payload: dict):
        """
        Ensures agent payload has required fields.
        Raises ValueError if invalid.
        """
        required = ["name", "description", "agent_role", "agent_goal", "agent_instructions"]
        for key in required:
            if key not in payload or not isinstance(payload[key], str):
                raise ValueError(f"YAML missing required string field: {key}")

        # Optional normalization for name (avoid spaces/specials)
        payload["name"] = canonicalize_name(payload["name"])
        return payload

    # -----------------
    # Core request logic
    # -----------------
    async def _request(self, method: str, endpoint: str, payload=None, stream=False):
        url = f"{self.base_url}{endpoint}"

        for attempt in range(self.retries):
            try:
                if stream:
                    async with self.client.stream(method, url, headers=self.headers, json=payload) as r:
                        r.raise_for_status()
                        return {"ok": True, "status": r.status_code, "data": r.aiter_text()}
                else:
                    r = await self.client.request(method, url, headers=self.headers, json=payload)
                    r.raise_for_status()
                    try:
                        return {"ok": True, "status": r.status_code, "data": r.json()}
                    except ValueError:
                        return {"ok": True, "status": r.status_code, "data": r.text}

            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                if status in [429, 500, 502, 503] and attempt < self.retries - 1:
                    wait = 2 ** attempt
                    self._log(f"⚠️ Transient error {status}, retrying in {wait}s...")
                    await asyncio.sleep(wait)
                    continue

                if self.debug:
                    self._log(f"❌ API {method} error {status} at {url}")
                    if payload:
                        self._log("🔍 Payload sent:\n", json.dumps(payload, indent=2))
                    self._log("🔍 Response text:\n", e.response.text)

                return {"ok": False, "status": status, "data": e.response.text}

            except Exception as e:
                if self.debug:
                    self._log("❌ Unexpected error:", str(e))
                return {"ok": False, "status": -1, "data": str(e)}

        return {"ok": False, "status": -1, "data": "Max retries exceeded"}

    # -----------------
    # Low-level wrappers
    # -----------------
    async def get(self, endpoint):
        return await self._request("GET", endpoint)

    async def post(self, endpoint, payload, stream=False):
        return await self._request("POST", endpoint, payload=payload, stream=stream)

    async def put(self, endpoint, payload):
        return await self._request("PUT", endpoint, payload=payload)

    async def delete(self, endpoint):
        return await self._request("DELETE", endpoint)

    # -----------------
    # High-level helpers
    # -----------------
    async def call_agent(self, agent_id_or_name: str, payload: dict):
        """Invoke a specific agent by ID or name"""
        url = f"/v3/agents/{agent_id_or_name}/invoke"
        return await self.post(url, payload)

    async def create_agent(self, payload: dict):
        payload = self._validate_agent_payload(payload)
        return await self.post("/v3/agents/", payload)

    async def create_agent_from_yaml(self, yaml_input: str, is_path: bool = True):
        if is_path:
            with open(yaml_input, "r") as f:
                yaml_def = yaml.safe_load(f)
        else:
            yaml_def = yaml.safe_load(yaml_input)

        payload = normalize_payload(yaml_def)
        payload = self._validate_agent_payload(payload)
        return await self.create_agent(payload)

    async def create_manager_with_roles(self, yaml_input: str, is_path: bool = True):
        if is_path and Path(yaml_input).exists():
            with open(yaml_input, "r") as f:
                manager_def = yaml.safe_load(f)
        else:
            manager_def = yaml.safe_load(yaml_input)

        created_roles = []

        for entry in manager_def.get("managed_agents", []):
            role_file = entry.get("file")
            role_yaml = None

            if role_file and Path(role_file).exists():
                role_yaml = Path(role_file).read_text()
            elif "yaml" in entry:
                role_yaml = entry["yaml"]

            if role_yaml:
                role_obj = yaml.safe_load(role_yaml)
                role_payload = normalize_payload(role_obj)
                role_payload = self._validate_agent_payload(role_payload)
                role_resp = await self.create_agent(role_payload)

                if role_resp.get("ok") and "data" in role_resp:
                    rid = role_resp["data"].get("_id") or role_resp["data"].get("agent_id")
                    if rid:
                        created_roles.append(role_resp["data"])
                        self._log(f"✅ Created role {role_obj.get('name')} -> {rid}")
                else:
                    self._log(f"❌ Failed to create role: {role_obj.get('name')}")

        manager_payload = normalize_payload(manager_def)
        manager_payload = self._validate_agent_payload(manager_payload)
        if created_roles:
            manager_payload["managed_agents"] = created_roles

        mgr_resp = await self.create_agent(manager_payload)

        if mgr_resp.get("ok") and "data" in mgr_resp:
            return {"ok": True, "data": mgr_resp["data"], "roles": created_roles}
        else:
            return {"ok": False, "error": mgr_resp.get("data"), "roles": created_roles}

    async def run_inference(self, agent_id: str, message: str, session_id: str = "default-session"):
        payload = {
            "agent_id": agent_id,
            "user_id": "demo-user",
            "session_id": session_id,
            "message": message,
        }
        return await self.post("/v3/inference/chat/", payload)

    async def delete_agent(self, agent_id: str):
        return await self.delete(f"/v3/agents/{agent_id}")

    async def list_agents(self):
        return await self.get("/v3/agents/")

    async def delete_all_agents(self):
        agents_resp = await self.list_agents()
        if not agents_resp.get("ok"):
            return {"ok": False, "deleted": [], "error": agents_resp.get("data")}
        data = agents_resp.get("data", [])
        deleted = []
        for agent in data:
            agent_id = agent.get("_id") or agent.get("agent_id")
            if agent_id:
                await self.delete_agent(agent_id)
                deleted.append(agent_id)
        return {"ok": True, "deleted": deleted}
