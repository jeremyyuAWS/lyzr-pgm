# scripts/run_business_flow.py

import os
import yaml
import httpx
import json
from pathlib import Path
from datetime import datetime
import pytz  # pip install pytz


# ---------- Config / Time Helpers ----------

def load_llm_config():
    cfg_path = Path("config/llm_config.yaml")
    with open(cfg_path, "r") as f:
        return yaml.safe_load(f)

def now_in_tz(tz_name: str):
    try:
        tz = pytz.timezone(tz_name)
    except Exception:
        tz = pytz.UTC
    return datetime.now(tz)

def stamp_for_name(dt: datetime) -> str:
    """
    Return '30AUG2025-8:37AM PST' style stamp.
    """
    day = dt.strftime("%d")
    mon = dt.strftime("%b").upper()
    yr = dt.strftime("%Y")
    hr12 = dt.strftime("%I").lstrip("0") or "12"
    minute = dt.strftime("%M")
    ampm = dt.strftime("%p")
    tz = dt.strftime("%Z")
    return f"{day}{mon}{yr}-{hr12}:{minute}{ampm} {tz}"


# ---------- Prompt Builder ----------

def build_system_prompt(agent: dict) -> str:
    """
    Collapse role, goal, instructions into one system_prompt string.
    """
    role = agent.get("role", "")
    goal = agent.get("goal", "")
    instr = agent.get("instructions", "")
    parts = []
    if role:
        parts.append(role)
    if goal:
        parts.append(f"Goal:\n{goal}")
    if instr:
        parts.append(f"Instructions:\n{instr}")
    return "\n\n".join(parts).strip()


# ---------- Name / Version Helpers ----------

def bump_version_in_name(name: str) -> str:
    """
    Look for '_vX.Y' and bump minor version.
    If no version tag, append '_v1.0'.
    """
    if "_v" not in name:
        return name + "_v1.0"
    base, version = name.rsplit("_v", 1)
    parts = version.split(".")
    try:
        parts[-1] = str(int(parts[-1]) + 1)
        new_version = ".".join(parts)
    except ValueError:
        new_version = version + ".1"
    return f"{base}_v{new_version}"

def format_final_name(base_name: str, agent_id: str, tz_name: str) -> str:
    """Return <BaseName>_v<version>_<last6>_30AUG2025-8:37AM PST"""
    short_id = (agent_id or "")[-6:] or "xxxxxx"
    ts = stamp_for_name(now_in_tz(tz_name))
    return f"{base_name}_{short_id}_{ts}"


# ---------- Payload Builder ----------

def enrich_for_api(agent: dict, agent_type: str, config: dict) -> dict:
    base_defaults = {
        "llm_credential_id": config["default_llm_credential_id"],
        "provider_id": config["default_provider_id"],
        "model": config["default_model"],
        "top_p": config["default_top_p"],
        "response_format": {"type": "json"},
    }

    name = agent.get("name", "Unnamed_Agent")
    description = agent.get("description", f"{name} auto-description")

    role = agent.get("role", "")
    goal = agent.get("goal", "")
    instr = agent.get("instructions", "")

    enriched = {
        "name": name,
        "description": description,
        "system_prompt": build_system_prompt(agent),
        "agent_role": role,
        "agent_goal": goal,
        "agent_instructions": instr,
        # 🚫 Force both to empty every time
        "features": [],
        "tools": [],
    }
    enriched.update(base_defaults)
    enriched.update({
        "temperature": config.get("default_temperature", 0.7),
    })
    if "managed_agents" in agent:
        enriched["managed_agents"] = agent["managed_agents"]
    return enriched



# ---------- Studio Calls ----------

def create_then_rename_agent(agent: dict, agent_type: str, config: dict, headers: dict, base_url: str, log_file: Path):
    """
    1) POST /v3/agents/ with base name
    2) PUT /v3/agents/{id} with decorated name + full payload
    3) Log final decorated name + id to logs, YAML untouched
    """
    tz_name = config.get("default_timezone", "UTC")

    # Step 1: POST with base bumped name
    base_name = bump_version_in_name(agent.get("name", "Agent"))
    payload = enrich_for_api({**agent, "name": base_name}, agent_type, config)

    create_resp = httpx.post(base_url, headers=headers, json=payload, timeout=60)
    if create_resp.status_code != 200:
        print(f"❌ Create failed [{agent_type}]: {create_resp.status_code} {create_resp.text}")
        return None

    agent_id = create_resp.json().get("agent_id")
    if not agent_id:
        print("❌ No agent_id returned on create.")
        return None

    # Step 2: build decorated name
    final_name = format_final_name(base_name, agent_id, tz_name)

    # Full payload again, but with decorated name
    update_payload = {**payload, "name": final_name}
    update_url = f"{base_url}{agent_id}"
    update_resp = httpx.put(update_url, headers=headers, json=update_payload, timeout=60)

    if update_resp.status_code not in (200, 204):
        print(f"⚠️ Rename failed: {update_resp.status_code} {update_resp.text}")
    else:
        print(f"✅ Created + renamed {agent_type}: {final_name}")

    # Step 3: append to logs
    log_file.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "type": agent_type,
        "original_name": agent.get("name"),
        "final_name": final_name,
        "agent_id": agent_id,
        "created_at": now_in_tz(config["default_timezone"]).isoformat()
    }

    with open(log_file, "a") as f:
        f.write(json.dumps(entry) + "\n")

    return {"name": final_name, "agent_id": agent_id}


# ---------- Main Flow ----------

def main():
    yaml_path = Path("agents/managers/KYC_Onboarding_Flow.yaml")
    config = load_llm_config()

    with open(yaml_path, "r") as f:
        business_yaml = yaml.safe_load(f)

    api_key = os.getenv("LYZR_API_KEY")
    if not api_key:
        raise RuntimeError("Missing LYZR_API_KEY")

    base_url = os.getenv("LYZR_BASE_URL", "https://agent-prod.studio.lyzr.ai") + "/v3/agents/"
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}

    log_file = Path("logs/created_agents.jsonl")

    # --- Create roles first ---
    role_results = []
    for role in business_yaml.get("roles", []):
        result = create_then_rename_agent(role, "role", config, headers, base_url, log_file)
        if result:
            role_results.append(result)

    # --- Create manager last ---
    manager = business_yaml["manager"]

    # Inject managed_agents with role agent IDs, names, description, usage_description
    if role_results:
        manager["managed_agents"] = []
        for r in role_results:
            # Match with YAML role definition for extra fields
            role_yaml = next(
                (role for role in business_yaml.get("roles", []) if role["name"] in r["name"]),
                {}
            )
            manager["managed_agents"].append({
                "id": r["agent_id"],
                "name": r["name"],
                "description": role_yaml.get("description", ""),
                "usage_description": role_yaml.get("usage_description", f"Delegates to {r['name']}")
            })

    create_then_rename_agent(manager, "manager", config, headers, base_url, log_file)


if __name__ == "__main__":
    main()
