import os
import json
import time
import yaml
import httpx

from pathlib import Path
from datetime import datetime
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

        # ✅ Reusable client for all requests
        self.client = httpx.Client(timeout=httpx.Timeout(self.timeout))

        # Debug mode
        if debug is None:
            self.debug = os.getenv("LYZR_DEBUG", "0") == "1"
        else:
            self.debug = debug

    def _log(self, *args):
        if self.debug:
            print(*args, flush=True)

    # -----------------
    # Lifecycle methods
    # -----------------
    def close(self):
        """Close the underlying httpx.Client"""
        if self.client:
            self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    # -----------------
    # Core request logic
    # -----------------
    def _request(self, method: str, endpoint: str, payload=None, stream=False):
        url = f"{self.base_url}{endpoint}"

        for attempt in range(self.retries):
            try:
                if stream:
                    with self.client.stream(method, url, headers=self.headers, json=payload) as r:
                        r.raise_for_status()
                        return {"ok": True, "status": r.status_code, "data": r.iter_text()}
                else:
                    r = self.client.request(method, url, headers=self.headers, json=payload)
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
    # Example high-level helper
    # -----------------
    def call_agent(self, agent_id_or_name: str, payload: dict):
        """Invoke a specific agent by ID or name"""
        url = f"/v3/agents/{agent_id_or_name}/invoke"
        return self.post(url, payload)

    def create_agent_from_yaml(self, yaml_input: str, is_path: bool = True):
        """Create agent directly from YAML."""
        if is_path:
            with open(yaml_input, "r") as f:
                yaml_def = yaml.safe_load(f)
        else:
            yaml_def = yaml.safe_load(yaml_input)
        payload = normalize_payload(yaml_def)
        return self.create_agent(payload)

    def create_manager_with_roles(self, yaml_input: str, is_path: bool = True):
        """
        Deploy subordinate role agents first, then the manager agent with references.
        Returns { ok: True, data: <manager_object>, roles: [<role_objects>] }
        """
        if is_path and Path(yaml_input).exists():
            with open(yaml_input, "r") as f:
                manager_def = yaml.safe_load(f)
        else:
            manager_def = yaml.safe_load(yaml_input)

        created_roles = []

        # 1. Create role agents first
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
                role_resp = self.create_agent(role_payload)

                if role_resp.get("ok") and "data" in role_resp:
                    rid = role_resp["data"].get("_id") or role_resp["data"].get("agent_id")
                    if rid:
                        created_roles.append(role_resp["data"])  # ✅ full object
                        self._log(f"✅ Created role {role_obj.get('name')} -> {rid}")
                else:
                    self._log(f"❌ Failed to create role: {role_obj.get('name')}")

        # 2. Create the manager agent with references to roles
        manager_payload = normalize_payload(manager_def)
        if created_roles:
            manager_payload["managed_agents"] = created_roles

        mgr_resp = self.create_agent(manager_payload)

        if mgr_resp.get("ok") and "data" in mgr_resp:
            return {
                "ok": True,
                "data": mgr_resp["data"],   # manager object
                "roles": created_roles      # full role objects
            }
        else:
            return {
                "ok": False,
                "error": mgr_resp.get("data"),
                "roles": created_roles
            }

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
        return self.delete(f"/v3/agents/{agent_id}")

    def list_agents(self):
        return self.get("/v3/agents/")

    def delete_all_agents(self):
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

    # -----------------
    # New: Run Manager with Use Cases (like run_list_iterate.py)
    # -----------------
    def run_manager_with_usecases(self, manager_yaml: str, usecases_yaml: str, save_outputs=True, max_retries=3):
        """
        Deploy a Manager from YAML, then loop over use-cases YAML and run inference.
        Save raw + normalized outputs under ./output/{ManagerName}/{UseCaseName}.
        """
        mgr_resp = self.create_manager_with_roles(manager_yaml, is_path=True)
        if not mgr_resp.get("ok") or "data" not in mgr_resp:
            return {"ok": False, "error": mgr_resp.get("error", "Failed to create manager")}

        manager_id = mgr_resp["data"].get("_id") or mgr_resp["data"].get("agent_id")
        manager_name = mgr_resp["data"].get("name", "Manager")
        out_root = Path("output") / manager_name
        out_root.mkdir(parents=True, exist_ok=True)

        with open(usecases_yaml, "r") as f:
            usecases = yaml.safe_load(f)

        results = []
        for uc in usecases.get("use_cases", []):
            raw_name = uc.get("name", "unnamed_usecase")
            usecase_name = canonicalize_name(raw_name)
            usecase_text = uc.get("description", "")

            out_dir = out_root / usecase_name
            out_dir.mkdir(parents=True, exist_ok=True)

            success = False
            for attempt in range(1, max_retries + 1):
                payload = {
                    "agent_id": manager_id,
                    "user_id": "demo-user",
                    "session_id": f"{manager_id}-{os.urandom(4).hex()}",
                    "message": usecase_text,
                }

                resp = self.post("/v3/inference/chat/", payload)
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")

                if save_outputs:
                    (out_dir / f"inference_raw_{ts}_attempt{attempt}.json").write_text(
                        json.dumps(resp, indent=2)
                    )

                response_data = resp.get("data") if isinstance(resp, dict) else None
                if resp.get("ok") and response_data and "response" in response_data:
                    try:
                        norm = normalize_inference_output(response_data["response"], out_dir)
                        if save_outputs:
                            (out_dir / f"inference_normalized_{ts}_attempt{attempt}.json").write_text(
                                json.dumps(norm, indent=2)
                            )
                        success = True
                        results.append({"usecase": usecase_name, "normalized": norm})
                        break
                    except Exception as e:
                        self._log(f"⚠️ Normalization failed: {e}")

                time.sleep(2 ** (attempt - 1))  # backoff

            if not success:
                results.append({"usecase": usecase_name, "error": "Failed after retries"})

        return {"ok": True, "manager_id": manager_id, "results": results}
