# Used by backend/main_with_auth.py

import os
import yaml
from pathlib import Path
from typing import Union, Dict, Any, List
from datetime import datetime
import pytz

from src.api.client import LyzrAPIClient
from scripts.create_agent_from_yaml import create_agent_from_yaml, update_agent

# ---------- Timezone / naming helpers ----------

def _tz() -> pytz.timezone:
    # Default PST; override with APP_TZ (e.g. America/Los_Angeles)
    tz_name = os.getenv("APP_TZ", "America/Los_Angeles")
    try:
        return pytz.timezone(tz_name)
    except Exception:
        return pytz.timezone("America/Los_Angeles")

def _timestamp_str() -> str:
    # Example: 31AUG2025-10:07AM PDT
    now = datetime.now(_tz())
    return now.strftime("%d%b%Y-%I:%M%p %Z").upper()

def _suffix_from_id(agent_id: str) -> str:
    return (agent_id or "")[-6:] or "XXXXXX"

def _rich_manager_name(base: str, agent_id: str) -> str:
    return f"{base}_v1.0_{_suffix_from_id(agent_id)}_{_timestamp_str()}"

def _rich_role_name(base: str, agent_id: str) -> str:
    return f"(R) {base}_v1.0_{_suffix_from_id(agent_id)}_{_timestamp_str()}"

# ---------- Prompt + examples builders ----------

def _compose_system_prompt(agent_def: Dict[str, Any]) -> str:
    role = agent_def.get("agent_role", "").strip()
    goal = agent_def.get("agent_goal", "").strip()
    instr = agent_def.get("agent_instructions", "").strip()

    sections = []
    if role:
        sections.append(f"ROLE:\n{role}")
    if goal:
        sections.append(f"GOAL:\n{goal}")
    if instr:
        sections.append(f"INSTRUCTIONS:\n{instr}")
    return "\n\n".join(sections).strip()

def _manager_supervision_instructions(manager_def: Dict[str, Any], created_roles: List[Dict[str, Any]]) -> str:
    """Extend manager instructions with how to manage each role."""
    base = manager_def.get("agent_instructions", "").strip()
    lines = [base, "", "Manage these attached roles:"]
    for r in created_roles:
        bullets = (r.get("agent_goal") or "").strip().replace("\n", " ").strip()
        if bullets:
            lines.append(f"- Role '{r['name']}': {bullets}")
        else:
            lines.append(f"- Role '{r['name']}': Execute delegated sub-tasks from the manager.")
    return "\n".join([l for l in lines if l]).strip()

def canonical_role_examples(role_name: str) -> str:
    return f"""Expected canonical YAML format for Role agents:

workflow_name: {role_name}_Flow
workflow_yaml: |
  flow_name: {role_name}_Flow
  flow_data:
    tasks:
      - name: {role_name.lower()}_task
        function: call_agent
        agent: {role_name}
agents:
  - name: {role_name}
    type: role
    yaml: |
      name: {role_name}
      description: Example Role description
      agent_role: Example Role
      agent_goal: Example goal
      agent_instructions: Example instructions
      features:
        - type: yaml_role_generation
          config: {{}}
          priority: 0
      tools: []
      response_format:
        type: json
      provider_id: OpenAI
      model: gpt-4o-mini
      temperature: 0.3
      top_p: 0.9
      llm_credential_id: lyzr_openai
"""

def canonical_manager_examples(manager_name: str, role_names: List[str]) -> str:
    roles_block = "\n".join(
        [f"  - name: {r}\n    type: role\n    yaml: |\n      name: {r}\n      description: Example Role description\n      agent_role: Example Role\n      agent_goal: Example goal\n      agent_instructions: Example instructions\n      features:\n        - type: yaml_role_generation\n          config: {{}}\n          priority: 0\n      tools: []\n      response_format:\n        type: json\n      provider_id: OpenAI\n      model: gpt-4o-mini\n      temperature: 0.3\n      top_p: 0.9\n      llm_credential_id: lyzr_openai"
         for r in role_names]
    )

    return f"""Expected canonical YAML format for Manager + Roles:

workflow_name: {manager_name}_Flow
workflow_yaml: |
  flow_name: {manager_name}_Flow
  flow_data:
    tasks:
      - name: {manager_name.lower()}_task
        function: call_agent
        agent: {manager_name}
agents:
  - name: {manager_name}
    type: manager
    yaml: |
      name: {manager_name}
      description: Example Composer Manager description
      agent_role: Composer Manager
      agent_goal: Example manager goal
      agent_instructions: Example instructions
      features:
        - type: proposal_generation
          config: {{}}
          priority: 1
      tools: []
      response_format:
        type: json
      provider_id: OpenAI
      model: gpt-4o-mini
      temperature: 0.3
      top_p: 0.9
      llm_credential_id: lyzr_openai
{roles_block if roles_block else ""}
"""

# ---------- Main orchestration ----------

def create_manager_with_roles(client: LyzrAPIClient, manager_yaml: Union[Path, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Create role agents first, then manager, then:
      - rename both with PST timestamp and id suffix,
      - attach roles to manager (managed_agents + usage_description),
      - set robust system_prompt & examples via PUT (creation may ignore these fields).
    """
    # Load YAML if a path was received
    if isinstance(manager_yaml, Path):
        with open(manager_yaml, "r") as f:
            manager_yaml = yaml.safe_load(f)

    if not isinstance(manager_yaml, dict):
        raise ValueError("manager_yaml must be a dict or Path")

    manager_def = manager_yaml.get("manager")
    if not manager_def:
        raise ValueError("YAML must contain a top-level 'manager' key")

    # ----- Create roles first -----
    created_roles: List[Dict[str, Any]] = []
    for role in manager_def.get("managed_agents", []):
        if "yaml" not in role:
            print(f"⚠️ Skipping role {role.get('name')} (no inline YAML)")
            continue

        role_yaml = yaml.safe_load(role["yaml"])
        role_name = role_yaml.get("name", "ROLE")

        # inject examples & prepare prompt
        role_yaml["examples"] = canonical_role_examples(role_name)

        print(f"🎭 Creating role agent: {role_name}")
        role_resp = create_agent_from_yaml(client, role_yaml)
        if not role_resp.get("ok"):
            print(f"❌ Failed to create role {role_name}")
            print(role_resp)
            continue

        role_id = (role_resp.get("data") or {}).get("agent_id")
        if not role_id:
            print(f"❌ Role {role_name} created but missing agent_id in response")
            continue

        # Rename + set system_prompt + examples (PUT)
        role_renamed = _rich_role_name(role_name, role_id)
        role_updates = {
            "name": role_renamed,
            "system_prompt": _compose_system_prompt(role_yaml),
            "examples": role_yaml["examples"],
            "description": role_yaml.get("description", ""),
            "features": role_yaml.get("features", []),
            "tools": role_yaml.get("tools", []),
            "llm_credential_id": role_yaml.get("llm_credential_id", "lyzr_openai"),
            "provider_id": role_yaml.get("provider_id", "OpenAI"),
            "model": role_yaml.get("model", "gpt-4o-mini"),
            "top_p": role_yaml.get("top_p", 0.9),
            "temperature": role_yaml.get("temperature", 0.3),
            "response_format": role_yaml.get("response_format", {"type": "json"}),
            # keep backfills
            "agent_role": role_yaml.get("agent_role", ""),
            "agent_goal": role_yaml.get("agent_goal", ""),
            "agent_instructions": role_yaml.get("agent_instructions", ""),
        }
        upd = update_agent(client, role_id, role_updates)
        if not upd.get("ok"):
            print(f"⚠️ PUT update failed for role {role_name}: {upd}")



    # ----- Create manager -----
    manager_base_name = manager_def.get("name", "MANAGER")
    # Build enhanced instructions to include supervision lines
    mgr_instr_with_supervision = _manager_supervision_instructions(manager_def, created_roles)

    # Also set examples (manager + roles)
    mgr_examples = canonical_manager_examples(manager_base_name, [r["base_name"] for r in created_roles])
    manager_def["examples"] = mgr_examples

    print(f"👑 Creating manager agent: {manager_base_name}")
    mgr_resp = create_agent_from_yaml(client, manager_def)
    if not mgr_resp.get("ok"):
        print("❌ Manager creation failed")
        print(mgr_resp)
        return {}

    manager_id = (mgr_resp.get("data") or {}).get("agent_id")
    if not manager_id:
        print("❌ Manager created but missing agent_id in response")
        return {}

        # Rich rename + PUT update for manager
    manager_renamed = _rich_manager_name(manager_def.get("name"), manager_id)

    # Build updated managed_agents from the renamed roles
    managed_agents = [
        {"id": r["id"], "name": r["name"], "usage_description": f"Managed role: {r['agent_goal']}"}
        for r in created_roles
    ]

    # Enrich manager instructions with final role summaries
    role_summaries = "\n".join(
        [f"- Role '{r['name']}': {r['agent_goal']}" for r in created_roles if r.get("agent_goal")]
    )
    manager_instructions = (
        manager_def.get("agent_instructions", "")
        + "\n\nManage these attached roles:\n"
        + role_summaries
    )

    manager_updates = {
        "name": manager_renamed,
        "system_prompt": _compose_system_prompt(manager_def),
        "examples": manager_def.get("examples"),
        "description": manager_def.get("description", ""),
        "features": manager_def.get("features", []),
        "tools": manager_def.get("tools", []),
        "llm_credential_id": manager_def.get("llm_credential_id", "lyzr_openai"),
        "provider_id": manager_def.get("provider_id", "OpenAI"),
        "model": manager_def.get("model", "gpt-4o-mini"),
        "top_p": manager_def.get("top_p", 0.9),
        "temperature": manager_def.get("temperature", 0.3),
        "response_format": manager_def.get("response_format", {"type": "json"}),
        "agent_role": manager_def.get("agent_role", ""),
        "agent_goal": manager_def.get("agent_goal", ""),
        "agent_instructions": manager_instructions,
        "managed_agents": managed_agents,  # <-- updated after roles renamed
    }

    upd = update_agent(client, manager_id, manager_updates)
    if not upd.get("ok"):
        print(f"⚠️ Final PUT update failed for manager: {upd}")


    return {
        "agent_id": manager_id,
        "name": manager_renamed,
        "roles": created_roles,
        "timestamp": _timestamp_str(),
    }
