import argparse
import json
from pathlib import Path
from src.utils.parser import json_to_yaml, normalize_response

def main():
    parser = argparse.ArgumentParser(description="Parse Manager JSON response into Role Agent YAMLs")
    parser.add_argument("json_file", help="Path to JSON response from Manager agent")
    parser.add_argument("--output_dir", default="agents/roles", help="Where to save role agent YAMLs")
    args = parser.parse_args()

    # Load JSON (raw or string)
    raw = Path(args.json_file).read_text(encoding="utf-8")
    parsed = normalize_response(raw)

    if not isinstance(parsed, dict) or "role_agents" not in parsed:
        raise ValueError("Manager response must contain a 'role_agents' array")

    Path(args.output_dir).mkdir(parents=True, exist_ok=True)

    for role in parsed["role_agents"]:
        role_name = role.get("name", "unnamed_role")
        file_path = Path(args.output_dir) / f"{role_name}.yaml"
        json_to_yaml(role, output_file=str(file_path))
        print(f"✅ Saved {role_name} → {file_path}")

if __name__ == "__main__":
    main()
