import sys
import json
import yaml
from pathlib import Path
from datetime import datetime
import pytz
from tzlocal import get_localzone

from src.api.client import LyzrAPIClient
from src.utils.payload_normalizer import normalize_payload


class AgentManager:
    def __init__(self, client: LyzrAPIClient):
        self.client = client
        # Detect system/local timezone once
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

    def _stamp_name(self, base_name: str, agent_id: str) -> str:
        """Append agent_id and local datetime with timezone in human-readable format."""
        now_local = datetime.now(self.local_tz)
        # Example: 2025-08-26 08:26 PM PST
        timestamp_str = now_local.strftime("%Y-%m-%d %I:%M %p %Z")
        return f"{base_name} [{agent_id} | {timestamp_str}]"

    # -------------------------------------------------------------------------
    # Core Workflow
    # -------------------------------------------------------------------------

    def create_manager_with_roles(self, manager_yaml_path: str) -> dict:
        """
        Create all role agents defined in Manager YAML, then the Manager itself,
        then assign roles.

        Returns:
            {
              "agent_id": <manager_id>,
              "name": <stamped_manager_name>,
              "roles": [ {id, name, usage_description}, ... ],
              "timestamp": <timestamp_str>
            }
        """

        with open(manager_yaml_path, "r") as f:
            manager_yaml = yaml.safe_load(f)

        resolved_agents = []

        # ---------------------------------------------------------------------
        # 1. Create all role agents defined under `managed_agents`
        # ---------------------------------------------------------------------
        for entry in manager_yaml.get("managed_agents", []):
            if "file" in entry:  # Role defined in separate YAML
                role_path = entry["file"]
                with open(role_path, "r") as rf:
                    role_yaml = yaml.safe_load(rf)

                role_payload = normalize_payload(role_yaml)
                if "system_prompt" not in role_payload:
                    role_payload["system_prompt"] = self.build_system_prompt(role_yaml)

                res = self.client.create_agent(role_payload)
                if res.get("ok") and isinstance(res.get("data"), dict):
                    role_id = res["data"].get("_id") or res["data"].get("agent_id")
                    stamped_name = self._stamp_name(role_yaml.get("name"), role_id)

                    # Update role name
                    update_payload = role_payload.copy()
                    update_payload["name"] = stamped_name
                    self.client.put(f"/v3/agents/{role_id}", update_payload)

                    print(f"🧩 Created role agent {stamped_name}")
                    resolved_agents.append({
                        "id": role_id,
                        "name": stamped_name,
                        "usage_description": entry.get("usage_description", "")
                    })
                else:
                    print(f"❌ Failed to create role agent from {role_path}: {res}")
                    sys.exit(1)
            else:
                # Role already provided inline (id or config)
                resolved_agents.append(entry)

        # ---------------------------------------------------------------------
        # 2. Create the Manager agent itself
        # ---------------------------------------------------------------------
        manager_payload = normalize_payload(manager_yaml)
        if "system_prompt" not in manager_payload:
            manager_payload["system_prompt"] = self.build_system_prompt(manager_yaml)

        res = self.client.create_agent(manager_payload)
        if not (res.get("ok") and isinstance(res.get("data"), dict)):
            print(f"❌ Failed to create manager agent {manager_yaml.get('name')}: {res}")
            return None

        mgr_id = res["data"].get("_id") or res["data"].get("agent_id")
        stamped_mgr_name = self._stamp_name(manager_yaml.get("name"), mgr_id)

        # Update manager name + attach roles
        update_payload = manager_payload.copy()
        update_payload["name"] = stamped_mgr_name
        update_payload["managed_agents"] = resolved_agents

        update_res = self.client.put(f"/v3/agents/{mgr_id}", update_payload)
        if update_res.get("ok") or update_res.get("message") == "Agent updated successfully":
            print(f"🤖 Created manager agent {stamped_mgr_name} with {len(resolved_agents)} linked roles")
        else:
            print(f"⚠️ Manager created but failed to link roles → {update_res}")

        # ---------------------------------------------------------------------
        # 3. Return manager metadata
        # ---------------------------------------------------------------------
        ts = datetime.now(self.local_tz).strftime("%Y-%m-%d %I:%M %p %Z")
        return {
            "agent_id": mgr_id,
            "name": stamped_mgr_name,
            "roles": resolved_agents,
            "timestamp": ts,
        }
