import sys
import os
from src.api.client import LyzrAPIClient
from src.services.agent_manager import AgentManager

def main():
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.create_manager_from_yaml <manager_yaml>")
        sys.exit(1)

    manager_yaml_path = sys.argv[1]

    debug = os.getenv("LYZR_DEBUG", "0") == "1"
    client = LyzrAPIClient(debug=debug, timeout=180)
    manager = AgentManager(client)

    result = manager.create_manager_with_roles(manager_yaml_path)

    if result:
        print(f"\n✅ Manager agent created successfully!")
        print(f"   ID   : {result['agent_id']}")
        print(f"   Name : {result['name']}")
    else:
        print("❌ Manager creation failed.")

if __name__ == "__main__":
    main()

# Example usage:
# (.venv) jeremyyu@Lyzr lyzr-pgm % LYZR_DEBUG=1 python -m scripts.create_manager_from_yaml agents/managers/ARCHITECT_MANAGER_v1.yaml

# 🧩 Created role agent YAML_COMPOSER_ROLE_v1.1 [68b0e6356cc0b2432a44fba7 | 2025-08-28 04:28 PM PDT]
# 🤖 Created manager agent ARCHITECT_MANAGER_v1.1 [68b0e6366cc0b2432a44fba8 | 2025-08-28 04:28 PM PDT] with 1 linked roles

# ✅ Manager agent created successfully!
#    ID   : 68b0e6366cc0b2432a44fba8
#    Name : ARCHITECT_MANAGER_v1.1 [68b0e6366cc0b2432a44fba8 | 2025-08-28 04:28 PM PDT]