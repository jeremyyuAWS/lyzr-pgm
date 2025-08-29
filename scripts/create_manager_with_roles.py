# scripts/create_manager_with_roles.py

import sys
import os
from pathlib import Path
from src.api.client import LyzrAPIClient
from src.services.agent_manager import AgentManager

def main():
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.create_manager_with_roles <manager_yaml>")
        sys.exit(1)

    manager_yaml_path = sys.argv[1]

    debug = os.getenv("LYZR_DEBUG", "0") == "1"
    client = LyzrAPIClient(debug=debug, timeout=180)
    manager = AgentManager(client)

    result = manager.create_manager_with_roles(manager_yaml_path)
    if not result:
        print("❌ Manager creation failed")
        sys.exit(1)

    print(f"\n✅ Manager + Roles created successfully!")
    print(f"   Manager ID   : {result['agent_id']}")
    print(f"   Manager Name : {result['name']}")
    print(f"   Roles        : {[r['name'] for r in result['roles']]}")
    print(f"   Timestamp    : {result['timestamp']}")

if __name__ == "__main__":
    main()
