import json

def normalize_payload(agent_yaml: dict) -> dict:
    payload = {
        "template_type": agent_yaml.get("template_type", "single_task"),
        "name": agent_yaml.get("name"),
        "description": agent_yaml.get("description", ""),
        "agent_role": agent_yaml.get("agent_role", ""),
        "agent_goal": agent_yaml.get("agent_goal", ""),
        "agent_instructions": agent_yaml.get("agent_instructions", ""),
        "tool_usage_description": agent_yaml.get("tool_usage_description", ""),
        "tools": agent_yaml.get("tools", []),
        "response_format": agent_yaml.get("response_format", {"type": "json"}),
        "provider_id": agent_yaml.get("provider_id", "OpenAI"),
        "model": agent_yaml.get("model", "gpt-4o-mini"),
        "temperature": agent_yaml.get("temperature", 0.7),
        "top_p": agent_yaml.get("top_p", 0.9),
        "llm_credential_id": agent_yaml.get("llm_credential_id", "lyzr_openai"),
    }

    # Only include features if explicitly marked safe
    if agent_yaml.get("features_safe", False):
        payload["features"] = agent_yaml.get("features", [])

    # Handle examples (must be stringified JSON)
    if "examples" in agent_yaml:
        try:
            payload["examples"] = json.dumps(agent_yaml["examples"])
        except Exception:
            payload["examples"] = agent_yaml["examples"]

    # Handle structured_output_examples (also stringified JSON)
    if "structured_output_examples" in agent_yaml:
        try:
            payload["structured_output_examples"] = json.dumps(agent_yaml["structured_output_examples"])
        except Exception:
            payload["structured_output_examples"] = agent_yaml["structured_output_examples"]

    # Handle single tool → tools array
    if "tool" in agent_yaml and not payload["tools"]:
        payload["tools"] = [agent_yaml["tool"]]

    return payload
