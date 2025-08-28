import json
import yaml
from pathlib import Path

def parse_raw_response(raw_path: str | Path) -> dict:
    """
    Parse a raw.json file into structured dict:
    - Outer JSON
    - Inner 'response' JSON
    - Extracted YAMLs parsed to dicts
    """
    raw = json.loads(Path(raw_path).read_text())
    output = {"outer": raw, "inner": None, "workflow_yaml": None, "agents": []}

    # Step 1: Parse inner response JSON if present
    if "response" in raw:
        try:
            inner = json.loads(raw["response"])
            output["inner"] = inner
        except Exception as e:
            raise ValueError(f"Failed to parse inner response JSON: {e}")

        # Step 2: Parse workflow YAML if available
        if "workflow_yaml" in inner:
            try:
                output["workflow_yaml"] = yaml.safe_load(inner["workflow_yaml"])
            except Exception as e:
                print(f"⚠️ Could not parse workflow_yaml: {e}")

        # Step 3: Parse each agent's YAML
        for agent in inner.get("agents", []):
            parsed_agent = dict(agent)  # shallow copy
            if "yaml" in agent:
                try:
                    parsed_agent["yaml_dict"] = yaml.safe_load(agent["yaml"])
                except Exception as e:
                    print(f"⚠️ Could not parse agent YAML for {agent.get('name')}: {e}")
            output["agents"].append(parsed_agent)

    return output


if __name__ == "__main__":
    # Example usage: python src/utils/raw_parser.py output/CandidateScreening/raw.json
    import sys, pprint
    if len(sys.argv) < 2:
        print("Usage: python src/utils/raw_parser.py <raw.json>")
    else:
        parsed = parse_raw_response(sys.argv[1])
        pprint.pp(parsed, width=120)
