def normalize_payload(agent_yaml: dict) -> dict:
    """
    Normalize YAML agent definitions into API-compatible payload.
    Ensures required fields are present for the Lyzr API.
    """

    payload = {
        "template_type": agent_yaml.get("template_type", "single_task"),
        "name": agent_yaml.get("name"),
        "description": agent_yaml.get("description", ""),
        "agent_role": agent_yaml.get("agent_role", ""),
        "agent_goal": agent_yaml.get("agent_goal", ""),
        "agent_instructions": agent_yaml.get("agent_instructions", ""),
        "features": [],
        "tools": agent_yaml.get("tools", []),
        "tool_usage_description": agent_yaml.get("tool_usage_description", ""),
        "response_format": agent_yaml.get("response_format", {"type": "json"}),

        # Required LLM config (defaults if missing)
        "provider_id": agent_yaml.get("provider_id", "OpenAI"),
        "model": agent_yaml.get("model", "gpt-4o-mini"),
        "top_p": agent_yaml.get("top_p", 0.9),
        "temperature": agent_yaml.get("temperature", 0.7),
        "version": agent_yaml.get("version", "3"),
        "llm_credential_id": agent_yaml.get("llm_credential_id", "lyzr_openai"),
    }

    # Normalize features into the correct structure
    for i, feat in enumerate(agent_yaml.get("features", [])):
        if isinstance(feat, dict):
            payload["features"].append({
                "type": feat.get("type") or feat.get("name"),
                "config": feat.get("config", {}),
                "priority": feat.get("priority", i)
            })

    return payload
