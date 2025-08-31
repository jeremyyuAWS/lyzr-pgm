import sys
import os
import yaml
from pathlib import Path
from typing import Dict, Any, Union
from src.api.client import LyzrAPIClient

def _to_system_prompt(agent_def: Dict[str, Any]) -> str:
    """Compose a robust system prompt from role/goal/instructions."""
    bits = []
    if agent_def.get("agent_role"):
        bits.append(f"ROLE:\n{agent_def['agent_role']}\n")
    if agent_def.get("agent_goal"):
        bits.append(f"GOAL:\n{agent_def['agent_goal']}\n")
    if agent_def.get("agent_instructions"):
        bits.append(f"INSTRUCTIONS:\n{agent_def['agent_instructions']}\n")
    return "\n".join(bits).strip()

def create_agent_from_yaml(client: LyzrAPIClient, agent_yaml: Union[Path, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Create an agent using POST /v3/agents/.
    Accepts either a dict or a Path to YAML. Returns the raw API response.
    """
    if isinstance(agent_yaml, Path):
        with open(agent_yaml, "r") as f:
            agent_def = yaml.safe_load(f)
    else:
        agent_def = dict(agent_yaml)

    # Map to creation payload the API accepts.
    payload = {
        "template_type": agent_def.get("template_type", "single_task"),
        "name": agent_def["name"],
        "description": agent_def.get("description", ""),
        # Many Lyzr deployments store prompt in `system_prompt`. We still pass the named fields,
        # but build `system_prompt` so it always survives.
        "system_prompt": _to_system_prompt(agent_def),
        "agent_role": agent_def.get("agent_role", ""),
        "agent_goal": agent_def.get("agent_goal", ""),
        "agent_instructions": agent_def.get("agent_instructions", ""),
        "examples": agent_def.get("examples"),  # Some deployments accept this at creation; if not, we PUT it later.
        "features": agent_def.get("features", []),
        # Some envs use singular "tool", others array "tools"; we’ll pass both if present.
        "tools": agent_def.get("tools", []),
        "tool": agent_def.get("tool"),
        "tool_usage_description": agent_def.get("tool_usage_description", "{}"),
        "response_format": agent_def.get("response_format", {"type": "json"}),
        "provider_id": agent_def.get("provider_id") or agent_def.get("llm_config", {}).get("provider_id", "OpenAI"),
        "model": agent_def.get("model") or agent_def.get("llm_config", {}).get("model", "gpt-4o-mini"),
        "temperature": agent_def.get("temperature", agent_def.get("llm_config", {}).get("temperature", 0.7)),
        "top_p": agent_def.get("top_p", agent_def.get("llm_config", {}).get("top_p", 0.9)),
        "llm_credential_id": agent_def.get("llm_credential_id", agent_def.get("llm_config", {}).get("llm_credential_id", "lyzr_openai")),
        "version": str(agent_def.get("version", "3")),
    }

    print(f"⚙️ Creating agent: {payload['name']}")
    resp = client._request("POST", "/v3/agents/", payload=payload)

    if resp.get("ok"):
        agent_id = (resp.get("data") or {}).get("agent_id", "unknown")
        print(f"✅ Created agent {payload['name']} → {agent_id}")
    else:
        print(f"❌ Failed to create agent: {payload['name']}")
        print(resp)

    return resp

def update_agent(client: LyzrAPIClient, agent_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    """
    PUT /v3/agents/{agent_id}
    Use to rename, attach managed agents, set system_prompt/examples, etc.
    """
    print(f"🛠️ Updating agent {agent_id} with: {list(updates.keys())}")
    return client._request("PUT", f"/v3/agents/{agent_id}", payload=updates)

def main():
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.create_agent_from_yaml <agent_yaml_file>")
        sys.exit(1)

    yaml_file = Path(sys.argv[1])
    if not yaml_file.exists():
        print(f"❌ YAML file not found: {yaml_file}")
        sys.exit(1)

    debug = os.getenv("LYZR_DEBUG", "0") == "1"
    client = LyzrAPIClient(debug=debug, timeout=180)
    create_agent_from_yaml(client, yaml_file)

if __name__ == "__main__":
    main()
