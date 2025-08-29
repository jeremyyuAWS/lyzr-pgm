import yaml
from pathlib import Path

def postprocess_yaml(input_path: Path, output_path: Path):
    """
    Load YAML from input_path, enforce canonical formatting,
    and save to output_path.
    """
    try:
        # Load parsed YAML
        with open(input_path, "r") as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            raise ValueError("YAML is not a dict")

        # Canonical adjustments (examples, extend as needed)
        canonical = {}
        canonical["name"] = data.get("name", "UnnamedAgent")
        canonical["description"] = data.get("description", "").strip()
        canonical["agent_role"] = data.get("agent_role", "").strip()
        canonical["agent_goal"] = data.get("agent_goal", "").strip()
        canonical["agent_instructions"] = data.get("agent_instructions", "").strip()
        if "examples" in data:
            canonical["examples"] = data["examples"]
        if "features" in data:
            canonical["features"] = data["features"]
        if "tools" in data:
            canonical["tools"] = data["tools"]
        if "response_format" in data:
            canonical["response_format"] = data["response_format"]
        canonical["provider_id"] = data.get("provider_id", "OpenAI")
        canonical["model"] = data.get("model", "gpt-4o-mini")
        canonical["temperature"] = data.get("temperature", 0.7)
        canonical["top_p"] = data.get("top_p", 0.9)

        # Save canonical YAML with enforced style
        with open(output_path, "w") as f:
            yaml.dump(
                canonical,
                f,
                sort_keys=False,
                default_flow_style=False,
                allow_unicode=True,
            )

        print(f"✨ Canonicalized YAML → {output_path}")

    except Exception as e:
        print(f"⚠️ Postprocessing failed for {input_path}: {e}")
