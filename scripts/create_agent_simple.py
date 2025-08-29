# scripts/create_agent_simple.py
from src.api.client import LyzrAPIClient


if __name__ == "__main__":
    path = "agents/managers/YAML_COMPOSER_MANAGER_v1.yaml"  # adjust path as needed
    client = LyzrAPIClient(debug=True)
    resp = client.create_agent_from_yaml(path)

    if resp["ok"]:
        print("✅ Agent created successfully")
        print(resp["data"])
    else:
        print("❌ Failed to create agent")
        print(resp)

# Working example of creating an agent from a YAML file.

# (.venv) jeremyyu@Lyzr lyzr-pgm % python -m scripts.create_agent_simple

# ✅ Agent created successfully
# {'agent_id': '68b0e45c3134f53810d09d1e'}