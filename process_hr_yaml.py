import json
import yaml
import sys
import re
from pathlib import Path
from src.utils.save_utils import save_structured_yaml
from src.utils.postprocess_yaml import postprocess_yaml


def repair_yaml(text: str) -> str:
    """
    Attempt to repair squashed YAML by inserting newlines before known keys.
    """
    if not text:
        return text

    keys = [
        "name:", "description:", "agent_role:", "agent_goal:", "agent_instructions:",
        "examples:", "features:", "tools:", "response_format:", "provider_id:",
        "model:", "temperature:", "top_p:", "structured_output_examples:",
        "managed_agents:", "tool_usage_description:", "tools:"
    ]
    for key in keys:
        text = re.sub(rf"(?<!\n){key}", f"\n{key}", text)
    return text


def main():
    # ✅ Default path or CLI argument
    if len(sys.argv) > 1:
        in_path = Path(sys.argv[1])
    else:
        in_path = Path("output/workflows/use_cases_hr/raw.json")

    if not in_path.exists():
        print(f"❌ raw.json not found at {in_path}")
        return

    try:
        raw = json.loads(in_path.read_text())
    except Exception as e:
        print(f"⚠️ Failed to parse raw.json: {e}")
        return

    data = raw.get("data", {})
    response_str = data.get("response")

    if not response_str:
        print("❌ No 'response' found in raw.json")
        print(f"Top-level keys: {list(raw.keys())}")
        return

    # ✅ Parse embedded JSON from the response
    try:
        response_json = json.loads(response_str)
    except Exception as e:
        print(f"⚠️ Embedded response not clean JSON: {e}")
        fail_dir = in_path.parent / "failed"
        fail_dir.mkdir(exist_ok=True)
        (fail_dir / "response_raw.json").write_text(response_str)
        return

    # Extract workflow and agents
    workflow_yaml_text = response_json.get("workflow_yaml", "")
    agents = response_json.get("agents", [])

    # --- Process workflow YAML ---
    workflow_parsed = None
    if workflow_yaml_text:
        try:
            workflow_yaml_text = repair_yaml(workflow_yaml_text)
            workflow_parsed = yaml.safe_load(workflow_yaml_text)
        except Exception as e:
            print(f"⚠️ Failed to parse workflow_yaml: {e}")
            fail_dir = in_path.parent / "failed"
            fail_dir.mkdir(exist_ok=True)
            (fail_dir / "workflow_raw.yaml").write_text(workflow_yaml_text)

    # --- Process each agent YAML ---
    for agent in agents:
        agent_name = agent.get("name", "UnnamedAgent")
        agent_yaml_text = agent.get("yaml", "")

        if not agent_yaml_text:
            continue

        try:
            agent_yaml_text = repair_yaml(agent_yaml_text)
            parsed = yaml.safe_load(agent_yaml_text)

            if not isinstance(parsed, dict):
                raise ValueError("Top-level agent YAML is not a dict")

            # Run canonical post-processing
            parsed = postprocess_yaml(parsed)

            # Save agent definition
            agent_dir = in_path.parent / agent_name
            agent_dir.mkdir(parents=True, exist_ok=True)
            out_path = agent_dir / "agent_definition.yaml"

            save_structured_yaml(parsed, out_path)
            (agent_dir / "raw.json").write_text(json.dumps(agent, indent=2))

            print(f"✅ Saved structured YAML → {out_path}")

        except Exception as e:
            print(f"⚠️ Failed to parse agent '{agent_name}': {e}")
            fail_dir = in_path.parent / "failed"
            fail_dir.mkdir(exist_ok=True)
            (fail_dir / f"{agent_name}_raw.yaml").write_text(agent_yaml_text)


if __name__ == "__main__":
    main()
