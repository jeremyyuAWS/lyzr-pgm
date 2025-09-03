# src/api/client_async.py

import os
import json
import httpx
import asyncio
import argparse

from src.utils.payload_normalizer import normalize_payload
from src.utils.normalize_output import canonicalize_name


class LyzrAPIClient:
    """
    Async client for interacting with the Lyzr Studio API.
    Pure JSON version (no YAML parsing).
    """

    def __init__(self, api_key: str = None, debug: bool = None,
                 timeout: int = 300, retries: int = 3):
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
    # Lifecycle methods
    # -----------------
    async def aclose(self):
        if self.client:
            await self.client.aclose()

    def close(self):
        if self.client:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self.aclose())
                else:
                    loop.run_until_complete(self.aclose())
            except RuntimeError:
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
    # Logging
    # -----------------
    def _log(self, *args):
        if self.debug:
            print(*args, flush=True)

    # -----------------
    # Validation helpers
    # -----------------
    def _validate_agent_payload(self, payload: dict) -> dict:
        """Ensure agent payload has required fields (JSON only)."""
        required = ["name", "description", "agent_role", "agent_goal", "agent_instructions"]
        for key in required:
            if key not in payload or not isinstance(payload[key], str):
                raise ValueError(f"Agent payload missing required string field: {key}")

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
                return {"ok": False, "status": status, "error": e.response.text}

            except Exception as e:
                return {"ok": False, "status": -1, "error": str(e)}

        return {"ok": False, "status": -1, "error": "Max retries exceeded"}

    # -----------------
    # Low-level wrappers
    # -----------------
    async def get(self, endpoint): return await self._request("GET", endpoint)
    async def post(self, endpoint, payload, stream=False): return await self._request("POST", endpoint, payload=payload, stream=stream)
    async def put(self, endpoint, payload): return await self._request("PUT", endpoint, payload=payload)
    async def delete(self, endpoint): return await self._request("DELETE", endpoint)

    # -----------------
    # High-level helpers
    # -----------------
    async def call_agent(self, agent_id_or_name: str, payload: dict):
        return await self.post(f"/v3/agents/{agent_id_or_name}/invoke", payload)

    async def create_agent(self, payload: dict):
        payload = normalize_payload(payload)
        payload = self._validate_agent_payload(payload)
        return await self.post("/v3/agents/", payload)

    async def create_manager_with_roles(self, manager_def: dict):
        """
        Create a manager agent and its managed role agents.
        Input must be a dict containing manager + roles definitions.
        """
        if not isinstance(manager_def, dict):
            return {"ok": False, "error": "Manager definition must be dict"}

        # --- Create roles first ---
        created_roles = []
        for entry in manager_def.get("managed_agents", []):
            try:
                role_payload = normalize_payload(entry)
                role_payload = self._validate_agent_payload(role_payload)
                role_resp = await self.create_agent(role_payload)
                if role_resp.get("ok"):
                    rid = role_resp["data"].get("_id") or role_resp["data"].get("agent_id")
                    if rid:
                        created_roles.append({"agent_id": rid, "name": role_payload.get("name")})
            except Exception as e:
                self._log(f"❌ Failed to create role: {e}")

        # --- Create manager ---
        try:
            manager_payload = normalize_payload(manager_def)
            manager_payload = self._validate_agent_payload(manager_payload)
            if created_roles:
                manager_payload["managed_agents"] = created_roles

            mgr_resp = await self.create_agent(manager_payload)
            if mgr_resp.get("ok"):
                return {"ok": True, "manager": mgr_resp["data"], "roles": created_roles}
            return {"ok": False, "error": mgr_resp.get("error"), "roles": created_roles}
        except Exception as e:
            return {"ok": False, "error": f"Manager creation failed: {e}", "roles": created_roles}

    async def link_agents(self, manager_id: str, role_id: str):
        """Link a role agent to a manager agent."""
        payload = {"manager_id": manager_id, "role_id": role_id}
        return await self.post("/v3/agents/link", payload)

    async def run_inference(self, agent_id: str, message: str, session_id: str = "default-session"):
        payload = {"agent_id": agent_id, "user_id": "demo-user", "session_id": session_id, "message": message}
        return await self.post("/v3/inference/chat/", payload)

    async def delete_agent(self, agent_id: str):
        return await self.delete(f"/v3/agents/{agent_id}")

    async def list_agents(self):
        return await self.get("/v3/agents/")

    async def delete_all_agents(self):
        agents_resp = await self.list_agents()
        if not agents_resp.get("ok"):
            return {"ok": False, "deleted": [], "error": agents_resp.get("error")}
        deleted = []
        for agent in agents_resp.get("data", []):
            agent_id = agent.get("_id") or agent.get("agent_id")
            if agent_id:
                await self.delete_agent(agent_id)
                deleted.append(agent_id)
        return {"ok": True, "deleted": deleted}


# -----------------
# __main__ runner
# -----------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Lyzr API Client Runner (JSON only)")
    parser.add_argument("json_file", help="Path to Manager JSON file")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    async def main():
        import json
        with open(args.json_file, "r") as f:
            manager_def = json.load(f)

        async with LyzrAPIClient(debug=args.debug) as client:
            result = await client.create_manager_with_roles(manager_def)
            print(json.dumps(result, indent=2))

    asyncio.run(main())
