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


def format_timestamp(tz_str: str = "America/Los_Angeles") -> str:
    """Format timestamp in user timezone (default PST)."""
    tz = pytz.timezone(tz_str)
    now = datetime.now(tz)
    return now.strftime("%d%b%Y-%I:%M%p %Z").upper()


def create_manager_with_roles(client: LyzrAPIClient, manager_yaml: Union[Path, dict], tz_str: str = "America/Los_Angeles"):
    """Create role agents first, then create a manager agent referencing them, update manager metadata."""

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
            print(f"⚠️ Skipping role {role.get('name')} (no inline YAML)")
            continue

        role_yaml = yaml.safe_load(role["yaml"])
        system_prompt = build_system_prompt(role_yaml)

        payload = {
            "name": rich_role_name,
            "description": role_yaml.get("description", ""),
            "system_prompt": system_prompt,
            "features": role_yaml.get("features", []),
            "tools": role_yaml.get("tools", []),
            "llm_credential_id": role_yaml.get("llm_credential_id", "lyzr_openai"),
            "provider_id": role_yaml.get("provider_id", "OpenAI"),
            "model": role_yaml.get("model", "gpt-4o-mini"),
            "top_p": float(role_yaml.get("top_p", 0.9)),
            "temperature": float(role_yaml.get("temperature", 0.7)),
            "response_format": role_yaml.get("response_format", {"type": "json"}),
        }
        client._request("PUT", f"/v3/agents/{role_id}", payload=payload)


        created_roles.append({
            "id": role_id,
            "name": rich_role_name,
            "description": role_yaml.get("description", ""),
            "agent_role": role_yaml.get("agent_role", ""),
            "agent_goal": role_yaml.get("agent_goal", ""),
            "agent_instructions": role_yaml.get("agent_instructions", ""),
            "usage_description": f"Manager delegates tasks related to '{role_yaml.get('name')}'."
        })
    else:
        print(f"❌ Failed to create role {role_yaml.get('name')}")
        print(role_resp)

    # --- Create the manager ---
    print(f"👑 Creating manager agent: {manager_def.get('name')}")
    manager_resp = create_agent_from_yaml(client, manager_def)

    if not manager_resp.get("ok"):
        print("❌ Manager creation failed")
        print(manager_resp)
        return None

    manager_id = manager_resp["data"].get("agent_id")
    timestamp = format_timestamp(tz_str)
    rich_name = f"{manager_def['name']}_v1.0_{manager_id[-6:]}_{timestamp}"

    # Append role summaries into manager instructions
    role_summaries = [
        f"- Role '{r['name']}': {r['agent_goal'] or r['description']}"
        for r in created_roles
    ]
    extra_instructions = "\n\nManage these attached roles:\n" + "\n".join(role_summaries)
    new_instructions = (manager_def.get("agent_instructions") or "").strip() + extra_instructions

    # --- Update manager with PUT ---
    payload = {
        "name": rich_name,
        "description": manager_def.get("description", ""),
        "system_prompt": new_instructions,
        "features": manager_def.get("features", []),
        "tools": manager_def.get("tools", []),
        "llm_credential_id": manager_def.get("llm_credential_id", "lyzr_openai"),
        "provider_id": manager_def.get("provider_id", "OpenAI"),
        "model": manager_def.get("model", "gpt-4o-mini"),
        "top_p": float(manager_def.get("top_p", 0.9)),
        "temperature": float(manager_def.get("temperature", 0.7)),
        "response_format": manager_def.get("response_format", {"type": "json"}),
        "managed_agents": [
            {"id": r["id"], "name": r["name"], "usage_description": r["usage_description"]}
            for r in created_roles
        ]
    }

    print(f"🔄 Updating manager {manager_id} with role associations + rich name")
    client._request("PUT", f"/v3/agents/{manager_id}", payload=payload)

    return {
        "agent_id": manager_id,
        "name": rich_name,
        "roles": created_roles,
        "timestamp": timestamp,
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

    tz_str = os.getenv("LYZR_TZ", "America/Los_Angeles")  # customizable timezone

    debug = os.getenv("LYZR_DEBUG", "0") == "1"
    client = LyzrAPIClient(api_key=api_key, debug=debug, timeout=180)

    result = create_manager_with_roles(client, yaml_path, tz_str=tz_str)
    if not result:
        sys.exit(1)

    print(f"\n✅ Manager + Roles created successfully!")
    print(f"   Manager ID   : {result['agent_id']}")
    print(f"   Manager Name : {result['name']}")
    print(f"   Roles        : {[r['name'] for r in result['roles']]}")
    print(f"   Timestamp    : {result['timestamp']}")


if __name__ == "__main__":
    main()
