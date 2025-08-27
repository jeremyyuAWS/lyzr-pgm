import os
import json
import time
import yaml
import httpx


class LyzrAPIClient:
    def __init__(self, debug: bool = None, timeout: int = 60, retries: int = 3):
        self.base_url = os.getenv("LYZR_BASE_URL", "https://agent-prod.studio.lyzr.ai")
        self.api_key = os.getenv("LYZR_API_KEY")
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

            except httpx.HTTPStatusError as e:
                # Retry on transient errors
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
        """Create agent from dict"""
        return self.post("/v3/agents/", payload)

    def create_agent_from_yaml(self, yaml_path: str):
        """Load YAML agent definition and create agent"""
        with open(yaml_path, "r") as f:
            agent_def = yaml.safe_load(f)
        resp = self.create_agent(agent_def)
        if resp["ok"]:
            agent_id = resp["data"].get("_id")
            self._log(f"✅ Created agent {agent_def['name']} with id {agent_id}")
            return agent_id
        return None

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
        resp = httpx.post(url, headers=self.headers, json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()