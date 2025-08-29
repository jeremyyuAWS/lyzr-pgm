# scripts/create_agent_from_output.py

import sys
from pathlib import Path
from src.api.client import LyzrAPIClient

def main():
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.create_agent_from_output <yaml_file>")
        sys.exit(1)

    yaml_file = Path(sys.argv[1])
    if not yaml_file.exists():
        print(f"❌ File not found: {yaml_file}")
        sys.exit(1)

    client = LyzrAPIClient(debug=True, timeout=180)

    print(f"📤 Creating agent from {yaml_file} ...")
    res = client.create_agent_from_yaml(str(yaml_file), is_path=True)

    if res.get("ok"):
        agent_id = res["data"].get("_id") or res["data"].get("agent_id")
        print(f"✅ Successfully created agent: {yaml_file.name}")
        print(f"   ID   : {agent_id}")
        print(f"   Name : {res['data'].get('name')}")
    else:
        print(f"⚠️ Failed to create agent from {yaml_file}")
        print(res)

if __name__ == "__main__":
    main()
