# scripts/create_manager_with_roles.py
# Used by backend/main_with_auth.py

import os
import yaml
import logging
import pytz
from pathlib import Path
from typing import Union, Dict, Any, List
from datetime import datetime

from src.api.client_async import LyzrAPIClient

logger = logging.getLogger("create-manager-with-roles")

# ---------- Timezone / naming helpers ----------

def _tz() -> pytz.timezone:
    tz_name = os.getenv("APP_TZ", "America/Los_Angeles")
    try:
        return pytz.timezone(tz_name)
    except Exception:
        return pytz.timezone("America/Los_Angeles")

def _timestamp_str() -> str:
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
    base = manager_def.get("agent_instructions", "").strip()
    lines = [base, "", "Manage these attached roles:"]
    for r in created_roles:
        bullets = (r.get("agent_goal") or "").strip().replace("\n", " ").strip()
        if bullets:
            lines.append(f"- Role '{r['name']}': {bullets}")
        else:
            lines.append(f"- Role '{r['name']}': Execute delegated sub-tasks from the manager.")
    return "\n".join([l for l in lines if l]).strip()

# ---------- Main orchestration ----------

async def create_manager_with_roles(
    client: LyzrAPIClient,
    manager_yaml: Union[Path, Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Orchestration:
    1. Create role agents first
    2. Create manager agent
    3. Rename both with suffix + timestamp
    4. Attach roles to manager with usage_description
    5. PUT updates to ensure fields (description, instructions, examples) are preserved
    """
    try:
        logger.info("📥 Starting create_manager_with_roles orchestration")

        if isinstance(manager_yaml, Path):
            logger.info(f"📂 Loading manager YAML from {manager_yaml}")
            with open(manager_yaml, "r") as f:
                manager_yaml = yaml.safe_load(f)

        if not isinstance(manager_yaml, dict):
            raise ValueError("manager_yaml must be a dict or Path")

        manager_def = manager_yaml.get("manager")
        if not manager_def:
            raise ValueError("YAML must contain a top-level 'manager' key")

        # ----- Roles -----
        created_roles: List[Dict[str, Any]] = []
        for role in manager_def.get("managed_agents", []):
            if "yaml" not in role:
                logger.warning(f"⚠️ Skipping role {role.get('name')} (no inline YAML)")
                continue

            role_yaml = yaml.safe_load(role["yaml"])
            role_name = role_yaml.get("name", "ROLE")

            logger.info(f"🎭 Creating role agent → {role_name}")
            role_resp = await client.create_agent(role_yaml)
            if not role_resp.get("ok"):
                logger.error(f"❌ Failed to create role {role_name}: {role_resp}")
                continue

            role_id = (role_resp.get("data") or {}).get("agent_id") or (role_resp.get("data") or {}).get("_id")
            if not role_id:
                logger.error(f"❌ Role {role_name} created but missing agent_id")
                continue

            role_renamed = _rich_role_name(role_name, role_id)
            logger.info(f"✏️ Updating role {role_name} → {role_renamed}")

            role_updates = {
                "name": role_renamed,
                "system_prompt": _compose_system_prompt(role_yaml),
                "agent_role": role_yaml.get("agent_role", ""),
                "agent_goal": role_yaml.get("agent_goal", ""),
                "agent_instructions": role_yaml.get("agent_instructions", ""),
            }
            upd = await client.update_agent(role_id, role_updates)
            if not upd.get("ok"):
                logger.warning(f"⚠️ PUT update failed for role {role_name}: {upd}")

            created_roles.append({
                "id": role_id,
                "name": role_renamed,
                "base_name": role_name,
                "description": role_yaml.get("description", ""),
                "agent_role": role_yaml.get("agent_role", ""),
                "agent_goal": role_yaml.get("agent_goal", ""),
                "agent_instructions": role_yaml.get("agent_instructions", ""),
            })

        # ----- Manager -----
        manager_base_name = manager_def.get("name", "MANAGER")
        logger.info(f"👑 Creating manager agent → {manager_base_name}")
        mgr_resp = await client.create_agent(manager_def)
        if not mgr_resp.get("ok"):
            logger.error(f"❌ Manager creation failed: {mgr_resp}")
            return {"ok": False, "error": "Manager creation failed", "roles": created_roles}

        manager_id = (mgr_resp.get("data") or {}).get("agent_id") or (mgr_resp.get("data") or {}).get("_id")
        if not manager_id:
            logger.error("❌ Manager created but missing agent_id")
            return {"ok": False, "error": "Manager missing id", "roles": created_roles}

        manager_renamed = _rich_manager_name(manager_base_name, manager_id)
        logger.info(f"✏️ Updating manager {manager_base_name} → {manager_renamed}")

        managed_agents_payload = [
            {
                "id": r["id"],
                "name": r["name"],
                "usage_description": f"Manager delegates YAML-subtasks to '{r['name']}'."
            }
            for r in created_roles
        ]

        manager_updates = {
            "name": manager_renamed,
            "agent_role": manager_def.get("agent_role", ""),
            "agent_goal": manager_def.get("agent_goal", ""),
            "agent_instructions": _manager_supervision_instructions(manager_def, created_roles),
            "managed_agents": managed_agents_payload,
            "description": manager_def.get("description", ""),
            "features": manager_def.get("features", []),
            "tools": manager_def.get("tools", []),
            "llm_credential_id": manager_def.get("llm_credential_id", "lyzr_openai"),
            "provider_id": manager_def.get("provider_id", "OpenAI"),
            "model": manager_def.get("model", "gpt-4o-mini"),
            "top_p": manager_def.get("top_p", 0.9),
            "temperature": manager_def.get("temperature", 0.3),
            "response_format": manager_def.get("response_format", {"type": "json"}),
        }
        upd = await client.update_agent(manager_id, manager_updates)
        if not upd.get("ok"):
            logger.warning(f"⚠️ PUT update failed for manager {manager_base_name}: {upd}")

        logger.info("✅ Manager + roles orchestration complete")

        return {
            "ok": True,
            "manager": upd.get("data") if upd.get("ok") else {"id": manager_id, "name": manager_renamed},
            "roles": created_roles,
            "timestamp": _timestamp_str(),
        }

    except Exception as e:
        logger.exception("💥 Exception in create_manager_with_roles")
        return {"ok": False, "error": str(e)}
