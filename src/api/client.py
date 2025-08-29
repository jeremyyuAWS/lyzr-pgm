import os
import json
import time
import yaml
import httpx

from src.utils.payload_normalizer import normalize_payload


class LyzrAPIClient:
    def __init__(self, api_key: str = None, debug: bool = None, timeout: int = 60, retries: int = 3):
        self.base_url = os.getenv("LYZR_BASE_URL", "https://agent-prod.studio.lyzr.ai")

        # Use provided key OR fallback to env
        self.api_key = api_key or os.getenv("LYZR_API_KEY")
        if not self.api_key:
            raise ValueError("No API key provided (api_key argument or LYZR_API_KEY env required)")

        self.headers = {"x-api-key": self.api_key, "Content-Type": "application/json"}
        self.timeout = timeout
        self.retries = retries

        # Debug mode via constructor or env
        if debug is None:
            self.debug = os.getenv("LYZR_DEBUG", "0") == "1"
        else:
            self.debug = debug

    def _log(self, *args):
        if self.debug:
            print(*args, flush=True)

    def _request(self, method: str, endpoint: str, payload=None, stream=False):
        """
        Core request handler with retries and debug logging.
        Returns dict: { "ok": bool, "status": int, "data": parsed or text }
        """
        url = f"{self.base_url}{endpoint}"

        for attempt in range(self.retries):
            try:
                if stream:
                    with httpx.stream(method, url, headers=self.headers, json=payload, timeout=self.timeout) as r:
                        r.raise_for_status()
                        return {"ok": True, "status": r.status_code, "data": r.iter_text()}
                else:
                    r = httpx.request(method, url, headers=self.headers, json=payload, timeout=self.timeout)
                    r.raise_for_status()
                    try:
                        return {"ok": True, "status": r.status_code, "data": r.json()}
                    except ValueError:
                        return {"ok": True, "status": r.status_code, "data": r.text}

            except httpx.HTTPStatusError:
                if r.status_code in [429, 500, 502, 503] and attempt < self.retries - 1:
                    wait = 2 ** attempt
                    self._log(f"⚠️ Transient error {r.status_code}, retrying in {wait}s...")
                    time.sleep(wait)
                    continue

                if self.debug:
                    self._log(f"❌ API {method} error", r.status_code)
                    self._log("🔍 Endpoint:", url)
                    if payload:
                        self._log("🔍 Payload sent:\n", json.dumps(payload, indent=2))
                    self._log("🔍 Response text:\n", r.text)
                return {"ok": False, "status": r.status_code, "data": r.text}

            except Exception as e:
                if self.debug:
                    self._log("❌ Unexpected error:", str(e))
                return {"ok": False, "status": -1, "data": str(e)}

        return {"ok": False, "status": -1, "data": "Max retries exceeded"}

    # -----------------
    # Low-level wrappers
    # -----------------
    def get(self, endpoint):
        return self._request("GET", endpoint)

    def post(self, endpoint, payload, stream=False):
        return self._request("POST", endpoint, payload=payload, stream=stream)

    def put(self, endpoint, payload):
        return self._request("PUT", endpoint, payload=payload)

    def delete(self, endpoint):
        return self._request("DELETE", endpoint)

    # -----------------
    # High-level helpers
    # -----------------
    def create_agent(self, payload: dict):
        """Create agent from dict payload (already normalized)."""
        return self.post("/v3/agents/", payload)

    def create_agent_from_yaml(self, yaml_input: str, is_path: bool = True):
        """Create agent directly from a YAML definition."""
        if is_path:
            with open(yaml_input, "r") as f:
                yaml_def = yaml.safe_load(f)
        else:
            yaml_def = yaml.safe_load(yaml_input)

        payload = normalize_payload(yaml_def)
        return self.create_agent(payload)

    def run_inference(self, agent_id: str, message: str, session_id: str = "default-session"):
        """Run inference for a given agent_id"""
        payload = {
            "agent_id": agent_id,
            "user_id": "demo-user",
            "session_id": session_id,
            "message": message,
        }
        return self.post("/v3/inference/chat/", payload)

    def delete_agent(self, agent_id: str):
        """Delete agent by id"""
        return self.delete(f"/v3/agents/{agent_id}")

    def call_agent(self, agent_id_or_name: str, payload: dict):
        """Call an existing Lyzr agent by ID or name."""
        url = f"{self.base_url}/v3/agents/{agent_id_or_name}/invoke"
        r = httpx.post(url, headers=self.headers, json=payload, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def list_agents(self):
        """List all agents (GET /v3/agents/)."""
        return self.get("/v3/agents/")

    def delete_all_agents(self):
        """Delete all agents by iterating over list."""
        agents_resp = self.list_agents()
        if not agents_resp.get("ok"):
            return {"ok": False, "deleted": [], "error": agents_resp.get("data")}

        data = agents_resp.get("data", [])
        deleted = []
        for agent in data:
            agent_id = agent.get("_id") or agent.get("agent_id")
            if agent_id:
                self.delete_agent(agent_id)
                deleted.append(agent_id)

        return {"ok": True, "deleted": deleted}
