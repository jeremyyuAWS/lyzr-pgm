# scripts/create_manager_with_roles.py
# Used in backend/main_with_auth.py

import sys
import os
import yaml
from pathlib import Path
from datetime import datetime
import pytz
from typing import Union

from src.api.client import LyzrAPIClient
from scripts.create_agent_from_yaml import create_agent_from_yaml


def build_system_prompt(agent_def: dict) -> str:
    """Combine role, goal, and instructions into a single system_prompt string."""
    parts = []
    if agent_def.get("agent_role"):
        parts.append(f"Role: {agent_def['agent_role']}")
    if agent_def.get("agent_goal"):
        parts.append(f"Goal:\n{agent_def['agent_goal']}")
    if agent_def.get("agent_instructions"):
        parts.append(f"Instructions:\n{agent_def['agent_instructions']}")
    return "\n\n".join(parts).strip()


def timestamped_name(base_name: str, tz_name: str = "US/Pacific", prefix: str = "") -> str:
    """Return a rich name with timestamp (default PST)."""
    tz = pytz.timezone(tz_name)
    now_str = datetime.now(tz).strftime("%d%b%Y-%I:%M%p %Z")
    if prefix:
        return f"{prefix}{base_name}_v1.0_{now_str}"
    return f"{base_name}_v1.0_{now_str}"


def create_manager_with_roles(client: LyzrAPIClient, manager_yaml: Union[Path, dict], tz_name: str = "US/Pacific"):
    """Create role agents first, then create a manager agent referencing them."""

    # If a Path is passed, load YAML from disk
    if isinstance(manager_yaml, Path):
        if not manager_yaml.exists():
            raise FileNotFoundError(f"Manager YAML not found: {manager_yaml}")
        with open(manager_yaml, "r") as f:
            manager_yaml = yaml.safe_load(f)

    if not isinstance(manager_yaml, dict):
        raise ValueError("manager_yaml must be a dict or Path")

    manager_def = manager_yaml.get("manager")
    if not manager_def:
        raise ValueError("YAML must contain a top-level 'manager' key")

    # --- Create roles first ---
    created_roles = []
    for role in manager_def.get("managed_agents", []):
        if "yaml" not in role:
            role_name = role.get("name", "UnnamedRole")
            print(f"⚠️ Skipping role {role_name} (no inline YAML)")
            continue

        role_yaml = yaml.safe_load(role["yaml"])
        base_role_name = role_yaml.get("name", "UnnamedRole")

        # Prefix and timestamp role names
        rich_role_name = timestamped_name(base_role_name, tz_name, prefix="(R) ")
        role_yaml["name"] = rich_role_name

        print(f"🎭 Creating role agent: {rich_role_name}")

        # Build system_prompt for role
        role_yaml["system_prompt"] = build_system_prompt(role_yaml)

        role_resp = create_agent_from_yaml(client, role_yaml)

        if role_resp.get("ok"):
            role_id = role_resp["data"].get("agent_id")
            created_roles.append({
                "id": role_id,
                "name": rich_role_name,
                "description": role_yaml.get("description", ""),
                "agent_role": role_yaml.get("agent_role", ""),
                "agent_goal": role_yaml.get("agent_goal", ""),
                "agent_instructions": role_yaml.get("agent_instructions", ""),
                "usage_description": f"Manager delegates tasks to {rich_role_name} for: {role_yaml.get('agent_goal','')}"
            })
        else:
            print(f"❌ Failed to create role {rich_role_name}")
            print(role_resp)

    # --- Attach created roles to manager ---
    role_summaries = [
        f"- Role '{r['name']}': {r['agent_goal'] or r['description']}"
        for r in created_roles
    ]

    # Build manager system prompt
    system_prompt = build_system_prompt(manager_def)
    if role_summaries:
        system_prompt += "\n\nManage these attached roles:\n" + "\n".join(role_summaries)

    manager_def["system_prompt"] = system_prompt

    # Timestamp manager name
    rich_manager_name = timestamped_name(manager_def.get("name"), tz_name)
    manager_def["name"] = rich_manager_name

    # --- Create the manager last ---
    print(f"👑 Creating manager agent: {rich_manager_name}")
    manager_resp = create_agent_from_yaml(client, manager_def)

    if not manager_resp.get("ok"):
        print("❌ Manager creation failed")
        print(manager_resp)
        return None

    manager_id = manager_resp["data"].get("agent_id")

    # --- PUT update to attach roles to manager ---
    if created_roles:
        update_payload = {
            "name": rich_manager_name,
            "system_prompt": system_prompt,
            "description": manager_def.get("description", ""),
            "features": manager_def.get("features", []),
            "tools": manager_def.get("tools", []),
            "llm_credential_id": manager_def.get("llm_credential_id", "lyzr_openai"),
            "provider_id": manager_def.get("provider_id", "OpenAI"),
            "model": manager_def.get("model", "gpt-4o-mini"),
            "top_p": manager_def.get("top_p", 0.9),
            "temperature": manager_def.get("temperature", 0.7),
            "response_format": manager_def.get("response_format", {"type": "json"}),
            "managed_agents": [
                {"id": r["id"], "name": r["name"], "usage_description": r["usage_description"]}
                for r in created_roles
            ],
        }

        print(f"🔄 Updating manager {manager_id} with attached roles…")
        client._request("PUT", f"/v3/agents/{manager_id}", payload=update_payload)

    return {
        "agent_id": manager_id,
        "name": rich_manager_name,
        "roles": created_roles,
        "timestamp": datetime.now(pytz.timezone(tz_name)).strftime("%d%b%Y-%I:%M%p %Z"),
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.create_manager_with_roles <manager_yaml>")
        sys.exit(1)

    yaml_path = Path(sys.argv[1])

    api_key = os.getenv("LYZR_API_KEY")
    if not api_key:
        print("❌ Missing LYZR_API_KEY in environment")
        sys.exit(1)

    debug = os.getenv("LYZR_DEBUG", "0") == "1"
    client = LyzrAPIClient(api_key=api_key, debug=debug, timeout=180)

    result = create_manager_with_roles(client, yaml_path)
    if not result:
        sys.exit(1)

    print(f"\n✅ Manager + Roles created successfully!")
    print(f"   Manager ID   : {result['agent_id']}")
    print(f"   Manager Name : {result['name']}")
    print(f"   Roles        : {[r['name'] for r in result['roles']]}")
    print(f"   Timestamp    : {result['timestamp']}")


if __name__ == "__main__":
    main()
