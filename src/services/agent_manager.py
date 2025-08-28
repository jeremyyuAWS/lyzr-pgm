# /src/services/agent_manager.py

import sys
import yaml
from datetime import datetime
import pytz
from tzlocal import get_localzone

from src.api.client import LyzrAPIClient
from src.utils.payload_normalizer import normalize_payload
from src.utils.versioning import generate_new_name  # fully centralized naming
from src.utils.output_saver import save_output
from src.utils.response_parser import classify_and_normalize, save_structured


class AgentManager:
    def __init__(self, client: LyzrAPIClient, base_output_dir: str = "output"):
        self.client = client
        self.base_output_dir = base_output_dir
        try:
            self.local_tz = get_localzone()
        except Exception:
            self.local_tz = pytz.UTC

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def build_system_prompt(self, agent_yaml: dict) -> str:
        """Combine role, goal, and instructions into system_prompt."""
        role = agent_yaml.get("agent_role", "")
        goal = agent_yaml.get("agent_goal", "")
        instr = agent_yaml.get("agent_instructions", "")

        system_prompt = ""
        if role:
            system_prompt += f"{role.strip()}\n\n"
        if goal:
            system_prompt += f"Goal:\n{goal.strip()}\n\n"
        if instr:
            system_prompt += f"Instructions:\n{instr.strip()}"
        return system_prompt.strip()

    def _get_existing_agents(self):
        """Fetch all agents from Lyzr API once for versioning decisions."""
        resp = self.client._request("GET", "/v3/agents/")
        return resp.get("data", []) if isinstance(resp, dict) else []

    def _handle_failure(self, label: str, base_name: str, response: dict):
        """On agent creation failure, attempt structured salvage and save raw."""
        print(f"⚠️ {label.capitalize()} creation failed for {base_name}, salvaging output...")

        try:
            status, payload, diag = classify_and_normalize(response)
        except Exception as e:
            status, payload, diag = "error", None, str(e)

        if status == "success":
            save_structured(self.base_output_dir, f"{label}_fail_{base_name}", payload)
            print(f"📂 Salvaged structured output for {base_name}")
        else:
            save_output(self.base_output_dir, f"{label}_fail_{base_name}", response)
            if diag:
                print(f"ℹ️ Parser diagnostic: {diag}")

    def safe_create_agent(self, payload: dict, label: str, base_name: str):
        """Always attempt to create an agent, salvage on failure."""
        res = self.client.create_agent(payload)
        if not (res.get("ok") and isinstance(res.get("data"), dict)):
            self._handle_failure(label, base_name, res)
            return None
        return res

    # -------------------------------------------------------------------------
    # Role agent workflow
    # -------------------------------------------------------------------------

    def _create_role_agent(self, role_yaml_path: str, existing_agents: list, usage_description: str = "") -> dict:
        """Helper to create a single role agent from YAML."""
        with open(role_yaml_path, "r") as rf:
            role_yaml = yaml.safe_load(rf)

        role_payload = normalize_payload(role_yaml)
        if "system_prompt" not in role_payload:
            role_payload["system_prompt"] = self.build_system_prompt(role_yaml)

        base_name = role_yaml.get("name")
        res = self.safe_create_agent(role_payload, "role", base_name)
        if not res:
            return None

        role_id = res["data"].get("_id") or res["data"].get("agent_id")

        # Centralized stamping: version + ID + timestamp
        stamped_name = generate_new_name(existing_agents, base_name, agent_id=role_id)
        update_payload = role_payload.copy()
        update_payload["name"] = stamped_name
        self.client.put(f"/v3/agents/{role_id}", update_payload)

        print(f"🧩 Created role agent {stamped_name}")
        existing_agents.append({"name": stamped_name})
        return {
            "id": role_id,
            "name": stamped_name,
            "usage_description": usage_description,
        }

    # -------------------------------------------------------------------------
    # Core Workflow
    # -------------------------------------------------------------------------

    def create_manager_with_roles(self, manager_yaml_path: str) -> dict:
        """
        Create all role agents defined in Manager YAML, then the Manager itself,
        then assign roles.
        """
        with open(manager_yaml_path, "r") as f:
            manager_yaml = yaml.safe_load(f)

        resolved_agents = []
        existing_agents = self._get_existing_agents()

        # 1. Create role agents
        for entry in manager_yaml.get("managed_agents", []):
            if "file" in entry:  # Role defined in separate YAML
                role_info = self._create_role_agent(
                    role_yaml_path=entry["file"],
                    existing_agents=existing_agents,
                    usage_description=entry.get("usage_description", "")
                )
                if role_info:
                    resolved_agents.append(role_info)
            else:
                resolved_agents.append(entry)

        # 2. Create manager
        manager_payload = normalize_payload(manager_yaml)
        if "system_prompt" not in manager_payload:
            manager_payload["system_prompt"] = self.build_system_prompt(manager_yaml)

        base_mgr_name = manager_yaml.get("name")
        res = self.safe_create_agent(manager_payload, "manager", base_mgr_name)
        if not res:
            return None

        mgr_id = res["data"].get("_id") or res["data"].get("agent_id")

        # Centralized stamping: version + ID + timestamp
        stamped_mgr_name = generate_new_name(existing_agents, base_mgr_name, agent_id=mgr_id)
        update_payload = manager_payload.copy()
        update_payload["name"] = stamped_mgr_name
        update_payload["managed_agents"] = resolved_agents

        update_res = self.client.put(f"/v3/agents/{mgr_id}", update_payload)
        if update_res.get("ok") or update_res.get("message") == "Agent updated successfully":
            print(f"🤖 Created manager agent {stamped_mgr_name} with {len(resolved_agents)} linked roles")
        else:
            print(f"⚠️ Manager created but failed to link roles → {update_res}")
            self._handle_failure("manager_link", base_mgr_name, update_res)

        ts = datetime.now(self.local_tz).strftime("%Y-%m-%d %H:%M %Z")

        return {
            "agent_id": mgr_id,
            "name": stamped_mgr_name,
            "roles": resolved_agents,
            "timestamp": ts,
        }
